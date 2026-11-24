"""Real LangGraph/SQLite controls; scripted provider and fixture evidence, no neural calls."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
from agent_lab.research_assistant import LocalModel
import unittest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from agent_lab.research_assistant import EvidenceTools, graph_for, State, validate_answer, final_arguments_message, TOOLS


def reply(name=None, arguments=None, *, text=None):
    message={'role':'assistant','content':text}
    if name:message['tool_calls']=[{'id':'call_'+name,'type':'function','function':{'name':name,'arguments':json.dumps(arguments or {})}}]
    return {'choices':[{'message':message,'finish_reason':'tool_calls' if name else 'stop'}]}


class Provider:
    def __init__(self,values):self.values=iter(values);self.calls=0;self.forced=[]
    async def complete(self,messages,tools,*,force_final=False):self.calls+=1;self.forced.append(force_final);return copy.deepcopy(next(self.values))


class Backend:
    def __init__(self):self.generation='a'*64;self.calls=[]
    @property
    def hit(self):return {'citation_id':'a'*64+':'+'b'*64,'generation':'a'*64,'is_current_generation':True,'source_id':'fixture', 'title':'Owned fixture','source_url':'https://example.com/paper.pdf#page=3','source_sha256':'c'*64,'char_start':0,'char_end':24,'excerpt':'Recover committed state.','pdf':{'sha256':'d'*64,'page_number':3,'page_label':'iii','page_count':4}}
    @property
    def catalog(self):return {'generation':self.generation,'sources':[{'id':'fixture','title':'Owned fixture — PDF page 3','pdf':self.hit['pdf']}],'nodes':1}
    async def call(self,name,args):
        self.calls.append(name)
        if name=='list_sources':return self.catalog
        if name=='search_sources':return {'generation':self.generation,'results':[self.hit]}
        if name=='read_citation':return self.hit
        raise AssertionError(name)


def initial():return {'messages':[{'role':'user','content':'How does recovery work?'}],'refs':{},'read_refs':[],'model_turns':0,'successful_tools':0,'pending':[],'status':'running','final':None,'needs_finalization':False,'finalization_requests':0}


class AssistantControls(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.backend=Backend();self.evidence=EvidenceTools(self.backend.call,self.backend.catalog)
    async def asyncTearDown(self):self.temp.cleanup()
    async def invoke(self,provider,max_turns=6):
        async with AsyncSqliteSaver.from_conn_string(str(self.root/'graph.sqlite')) as saver:
            graph=graph_for(provider,self.evidence,saver,max_turns)
            return await graph.ainvoke(initial(),{'configurable':{'thread_id':'test'},'recursion_limit':20})
    async def test_schema_request_content_arguments_use_same_citation_validator(self):
        final={'status':'supported','answer':'Recover the committed state.','citations':['r1']}
        class HTTP:
            async def post(inner,url,**kwargs):
                body=json.loads(kwargs['content']);self.assertEqual(body['tool_choice'],'none');self.assertFalse(body['parallel_tool_calls']);self.assertEqual(body['response_format']['json_schema']['schema'],TOOLS[-1]['function']['parameters'])
                class Response:
                    def raise_for_status(inner):pass
                    def json(inner):return reply(text=json.dumps(final))
                return Response()
        local=LocalModel(HTTP(),'http://127.0.0.1/v1','test',None,256,1,self.root/'responses')
        scripted=Provider([reply('find_passages',{'query':'recovery'}),reply('read_passage',{'ref':'r1'}),reply(text='Draft')])
        class Combined:
            async def complete(inner,messages,tools,*,force_final=False):
                return await local.complete(messages,tools,force_final=True) if force_final else await scripted.complete(messages,tools)
        result=await self.invoke(Combined(),max_turns=4)
        self.assertEqual(result['status'],'submitted');self.assertEqual(result['final_transport'],'schema_arguments_content');self.assertTrue(result['final']['citation_lineage_checked'])
        saved=json.loads(next((self.root/'responses').glob('*.json')).read_text())
        self.assertNotIn('tool_calls',saved['response']['choices'][0]['message']);self.assertEqual(saved['response']['choices'][0]['message']['content'],json.dumps(final))
    async def test_named_content_cannot_cite_unread_reference(self):
        p=Provider([reply('list_papers'),reply(text='Draft'),reply(text=json.dumps({'status':'supported','answer':'Unsupported claim','citations':['r1']}))])
        result=await self.invoke(p,max_turns=3)
        self.assertIsNone(result['final']);self.assertNotEqual(result['status'],'submitted')
    async def test_argument_object_in_unforced_content_is_not_a_submission(self):
        result=await self.invoke(Provider([reply(text=json.dumps({'status':'insufficient_evidence','answer':'Missing','citations':[]}))]))
        self.assertEqual(result['status'],'unsubmitted');self.assertIsNone(result['final'])
    async def test_named_content_rejects_ambiguous_or_nonexact_objects(self):
        for content in ['[]','```json\n{}\n```','{"status":"supported","status":"insufficient_evidence","answer":"x","citations":[]}',
                        '{"status":"supported","answer":"x","citations":[],"extra":1}', '{"status":"supported","answer":"x","citations":[]} trailing']:
            with self.subTest(content=content):self.assertFalse(final_arguments_message({'role':'assistant','content':content})[1])
    async def test_search_request_keeps_auto_tools_without_response_schema(self):
        bodies=[]
        class HTTP:
            async def post(inner,url,**kwargs):
                bodies.append(json.loads(kwargs['content']))
                class Response:
                    def raise_for_status(inner):pass
                    def json(inner):return reply('find_passages',{'query':'recovery'})
                return Response()
        local=LocalModel(HTTP(),'http://127.0.0.1/v1','test',None,256,1,self.root/'responses')
        await local.complete([{'role':'user','content':'Question'}],TOOLS)
        self.assertEqual(bodies[0]['tool_choice'],'auto');self.assertEqual(bodies[0]['tools'],TOOLS);self.assertNotIn('response_format',bodies[0]);self.assertEqual(bodies[0]['max_tokens'],256)
    async def test_truncated_named_content_is_never_adapted(self):
        value=reply(text=json.dumps({'status':'insufficient_evidence','answer':'Missing','citations':[]}));value['choices'][0]['finish_reason']='length'
        result=await self.invoke(Provider([reply('list_papers'),value]),max_turns=2)
        self.assertEqual(result['status'],'truncated');self.assertIsNone(result['final'])
    async def test_actual_graph_requires_search_read_and_expands_citation(self):
        p=Provider([reply('find_passages',{'query':'recovery'}),reply('read_passage',{'ref':'r1'}),reply('submit_answer',{'status':'supported','answer':'Recover the committed state.','citations':['r1']})]);r=await self.invoke(p)
        self.assertEqual(r['status'],'submitted');self.assertEqual(p.calls,3);self.assertEqual(self.backend.calls,['search_sources','read_citation']);self.assertEqual(r['final']['citations'][0]['pdf']['page_number'],3);self.assertFalse(r['final']['semantic_entailment_checked'])
    async def test_unread_and_unknown_refs_get_tool_feedback_not_acceptance(self):
        p=Provider([reply('find_passages',{'query':'recovery'}),reply('submit_answer',{'status':'supported','answer':'Guess','citations':['r1']}),reply('read_passage',{'ref':'never_seen'})]);r=await self.invoke(p,3)
        self.assertEqual(r['status'],'turn_limit');self.assertIsNone(r['final']);self.assertEqual(p.calls,3);self.assertEqual(self.backend.calls,['search_sources'])
    async def test_insufficient_requires_collection_inspection(self):
        p=Provider([reply('submit_answer',{'status':'insufficient_evidence','answer':'Not available','citations':[]}),reply('list_papers'),reply('submit_answer',{'status':'insufficient_evidence','answer':'Required paper is absent from this collection.','citations':[]})]);r=await self.invoke(p)
        self.assertEqual(r['status'],'submitted');self.assertEqual(r['final']['status'],'insufficient_evidence');self.assertEqual(p.calls,3)
    async def test_free_text_does_not_become_verified_answer(self):
        r=await self.invoke(Provider([reply(text='A plausible but uncited answer.')]));self.assertEqual(r['status'],'unsubmitted');self.assertIsNone(r['final'])
    async def test_generation_change_stops_before_more_model_calls(self):
        self.backend.generation='e'*64;p=Provider([reply('find_passages',{'query':'recovery'})]);r=await self.invoke(p)
        self.assertEqual(r['status'],'source_changed');self.assertEqual(p.calls,1);self.assertIsNone(r['final'])
    async def test_read_draft_requires_one_explicit_final_format_step(self):
        p=Provider([reply('find_passages',{'query':'recovery'}),reply('read_passage',{'ref':'r1'}),reply(text='A draft with r1'),reply('submit_answer',{'status':'supported','answer':'Committed state can be recovered.','citations':['r1']})])
        r=await self.invoke(p,4);self.assertEqual(r['status'],'submitted');self.assertEqual(p.forced,[False,False,False,True]);self.assertEqual(r['finalization_requests'],1);self.assertEqual(self.backend.calls,['search_sources','read_citation'])
    async def test_last_budgeted_turn_requests_final_format_with_same_read_contract(self):
        p=Provider([reply('find_passages',{'query':'recovery'}),reply('read_passage',{'ref':'r1'}),reply('submit_answer',{'status':'supported','answer':'Recovered state.','citations':['r1']})])
        r=await self.invoke(p,3);self.assertEqual(r['status'],'submitted');self.assertEqual(p.forced,[False,False,True]);self.assertEqual(r['model_turns'],3)
    async def test_whole_request_deadline_cancels_wait_and_never_saves_partial_reply(self):
        class SlowHTTP:
            async def post(self,*args,**kwargs):await asyncio.sleep(1)
        path=self.root/'responses';model=LocalModel(SlowHTTP(),'http://127.0.0.1:18890/v1','fixture',None,64,.02,path)
        with self.assertRaises(TimeoutError):await model.complete([{'role':'user','content':'test'}],[])
        self.assertFalse(list(path.glob('*.json')))
    async def test_response_saved_before_checkpoint_is_reused_without_new_transport(self):
        class Response:
            def raise_for_status(self):pass
            def json(self):return reply('list_papers')
        class HTTP:
            def __init__(self):self.calls=0
            async def post(self,*args,**kwargs):self.calls+=1;return Response()
        http=HTTP();cache=self.root/'responses';messages=[{'role':'user','content':'List papers'}]
        first=LocalModel(http,'http://127.0.0.1:18890/v1','fixture',None,64,1,cache)
        one=await first.complete(messages,[])
        restarted=LocalModel(http,'http://127.0.0.1:18890/v1','fixture',None,64,1,cache)
        self.assertEqual(await restarted.complete(messages,[]),one);self.assertEqual(http.calls,1)
        path=next(cache.glob('*.json'));record=json.loads(path.read_text());record['response']['choices'][0]['message']['content']='changed';path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'response changed'):await restarted.complete(messages,[])
        self.assertEqual(http.calls,1)
    async def test_committed_tool_boundary_resumes_in_new_connection_without_repeating_tool(self):
        config={'configurable':{'thread_id':'resume'},'recursion_limit':20};p=Provider([reply('find_passages',{'query':'recovery'})])
        async with AsyncSqliteSaver.from_conn_string(str(self.root/'graph.sqlite')) as saver:
            graph=graph_for(p,self.evidence,saver,6,interrupt_after_tools=True);stopped=await graph.ainvoke(initial(),config);self.assertEqual(stopped['status'],'running');self.assertEqual((await graph.aget_state(config)).next,('model',))
        p2=Provider([reply('read_passage',{'ref':'r1'}),reply('submit_answer',{'status':'supported','answer':'Committed state can be recovered.','citations':['r1']})])
        async with AsyncSqliteSaver.from_conn_string(str(self.root/'graph.sqlite')) as saver:
            graph=graph_for(p2,self.evidence,saver,6);result=await graph.ainvoke(None,config);self.assertEqual(result['status'],'submitted');self.assertFalse((await graph.aget_state(config)).next)
            self.assertEqual((await graph.aget_state(config)).values['final'],result['final'])
        self.assertEqual(self.backend.calls,['search_sources','read_citation']);self.assertEqual(p.calls+p2.calls,3)


if __name__=='__main__':unittest.main()
