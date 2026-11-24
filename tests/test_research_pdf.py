"""PDF provenance/lifecycle integration using real pypdf and LlamaIndex, fixture embeddings."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject
from agent_lab.research_pdf import prepare_pdfs
from agent_lab.research_library import ingest, search, citation, load_sources, open_generation
from test_research_library import FixtureEmbedding


def make_pdf(path, texts, *, encrypted=False):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=400)
        if text:
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            content = DecodedStreamObject(); content.set_data(('BT /F1 12 Tf 30 350 Td ('+text+') Tj ET').encode('ascii'))
            page[NameObject('/Contents')] = writer._add_object(content)
    writer.root_object[NameObject('/PageLabels')] = DictionaryObject({NameObject('/Nums'): ArrayObject([NumberObject(0), DictionaryObject({NameObject('/S'): NameObject('/r')})])})
    if encrypted: writer.encrypt('fixture-password')
    with path.open('wb') as stream: writer.write(stream)


class PDFControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.path = self.root/'paper.pdf'
        self.spec = self.root/'input.json'; self.spec.write_text(json.dumps({'version':1,'pdfs':[{'path':'paper.pdf','url':'https://example.com/paper-v1.pdf','title':'Owned fixture'}]}))
        self.bundle = self.root/'bundle'; self.store = self.root/'store'; self.model = FixtureEmbedding()
    def tearDown(self): self.temp.cleanup()
    def test_physical_page_and_label_and_original_bytes_survive_deleted_intake(self):
        make_pdf(self.path,['Alpha recovery evidence', '', 'Gamma sonar evidence'])
        report = prepare_pdfs(self.spec,self.bundle); self.assertEqual(report['page_sources'],2); self.assertEqual(report['pages_without_text'],1)
        rows = load_sources(self.bundle/'collection.json'); third = list(rows.values())[1]
        self.assertEqual(third['metadata']['pdf']['page_number'],3); self.assertEqual(third['metadata']['pdf']['page_label'],'iii')
        self.assertEqual(third['text'],PdfReader(self.path).pages[2].extract_text())
        original = self.path.read_bytes(); ingest(self.bundle/'collection.json',self.store,self.model)
        result = search(self.store,'sonar',self.model,mode='lexical')['results'][0]
        shutil.rmtree(self.bundle); self.path.unlink()
        replay = citation(self.store,result['citation_id']); self.assertEqual(replay['pdf']['sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(replay['source_url'],'https://example.com/paper-v1.pdf#page=3'); self.assertEqual(replay['excerpt'],result['excerpt'])
        root,_ = open_generation(self.store); self.assertEqual((root/'originals'/(replay['pdf']['sha256']+'.pdf')).read_bytes(),original)
    def test_pdf_replacement_keeps_page_ids_and_historical_original(self):
        make_pdf(self.path,['Alpha old source']); prepare_pdfs(self.spec,self.bundle)
        ingest(self.bundle/'collection.json',self.store,self.model); old = search(self.store,'Alpha',self.model,mode='lexical')['results'][0]
        before = self.model.calls; same = ingest(self.bundle/'collection.json',self.store,self.model); self.assertFalse(same['published']); self.assertEqual(before,self.model.calls)
        make_pdf(self.path,['Alpha new edition']); second=self.root/'second'; prepare_pdfs(self.spec,second)
        changed=ingest(second/'collection.json',self.store,self.model); self.assertEqual(changed['updated'],[old['source_id']])
        new=search(self.store,'Alpha',self.model,mode='lexical')['results'][0]
        replay=citation(self.store,old['citation_id']); self.assertFalse(replay['is_current_generation']); self.assertEqual(replay['excerpt'],old['excerpt']); self.assertNotEqual(new['pdf']['sha256'],replay['pdf']['sha256'])
    def test_original_tampering_before_ingest_and_after_publication_detected(self):
        make_pdf(self.path,['Evidence']); prepare_pdfs(self.spec,self.bundle)
        original=next((self.bundle/'originals').glob('*.pdf')); raw=original.read_bytes(); original.write_bytes(raw+b'tamper')
        with self.assertRaisesRegex(ValueError,'PDF bytes differ'):load_sources(self.bundle/'collection.json')
        original.write_bytes(raw); ingest(self.bundle/'collection.json',self.store,self.model); root,_=open_generation(self.store)
        next((root/'originals').glob('*.pdf')).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):open_generation(self.store)
    def test_blank_and_encrypted_documents_do_not_publish_partial_bundle(self):
        for encrypted,text in [(False,''),(True,'Private')]:
            make_pdf(self.path,[text],encrypted=encrypted)
            with self.assertRaises(ValueError):prepare_pdfs(self.spec,self.bundle)
            self.assertFalse(self.bundle.exists())
    def test_metadata_page_does_not_silently_disagree_with_link(self):
        make_pdf(self.path,['One','Two']); prepare_pdfs(self.spec,self.bundle)
        manifest=self.bundle/'collection.json'; rows=json.loads(manifest.read_text());rows['sources'][0]['pdf']['page_number']=2;manifest.write_text(json.dumps(rows))
        with self.assertRaisesRegex(ValueError,'disagrees with page'):load_sources(manifest)


if __name__=='__main__':unittest.main()
