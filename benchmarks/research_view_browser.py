"""CPU browser interaction checks for exported real reports and a separate fixture."""
from pathlib import Path
import hashlib,json,sys
from playwright.sync_api import sync_playwright


def run(application, output):
    output.mkdir(mode=0o700, exist_ok=False)
    real = application/'first/reading-report.html'; control = application/'control-only/reading-report.html'
    original = (application/'first/reading-report.json').read_bytes()
    network=[]; errors=[]; checks=[]
    def wire(context):
        def route(request):
            if request.request.url.startswith('file:'): request.continue_()
            else: network.append(request.request.url.split(':',1)[0]); request.abort()
        context.route('**/*', route)
        context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
        return context
    def visible(page): return page.locator('.card:not([hidden])').count()
    def no_overflow(page): return page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, args=['--disable-gpu','--disable-dev-shm-usage','--renderer-process-limit=2'])
        try:
            context=wire(browser.new_context(offline=True,viewport={'width':1280,'height':900},accept_downloads=True))
            page=context.new_page(); page.goto(real.as_uri()); page.locator('html.enhanced').wait_for()
            assert visible(page)==4 and no_overflow(page); checks.append('four_real_records_visible')
            page.select_option('#status','unfinished'); assert visible(page)==1
            assert 'LS-DETR' in page.locator('.card:not([hidden]) h2').inner_text(); checks.append('unfinished_filter_preserves_original_failure')
            page.fill('#query','RECEIPT'); assert visible(page)==0 and page.locator('#empty').is_visible()
            page.click('#reset'); assert visible(page)==4 and page.input_value('#query')=='' and page.input_value('#status')=='all'; checks.append('combined_filters_empty_state_and_reset')
            page.fill('#query','ＲＥＣＥＩＰＴ'); assert visible(page)==1; checks.append('unicode_normalized_question_search')
            links=page.locator('.card:not([hidden]) .refs a')
            assert links.count()==2 and all('2611.01930v1#page=' in links.nth(i).get_attribute('href') for i in range(2)); checks.append('new_paper_actual_page_links')
            with page.expect_download() as event: page.click('#download')
            downloaded=output/'downloaded-reading-report.json'; event.value.save_as(downloaded)
            assert downloaded.read_bytes()==original and json.loads(downloaded.read_text())['summary']['runs']==4; checks.append('download_keeps_all_records_and_exact_original_json')
            page.emulate_media(media='print'); assert not page.locator('.toolbar').is_visible() and visible(page)==1
            page.emulate_media(media='screen'); checks.append('print_layout_keeps_current_filter')
            page.click('#reset'); page.screenshot(path=str(output/'desktop.png'),full_page=True)
            page.fill('#query','MiniRAG'); assert visible(page)>=1; checks.append('source_and_answer_text_search')
            page.goto(control.as_uri()); page.locator('html.enhanced').wait_for()
            assert visible(page)==5 and page.evaluate('window.attacked === undefined') and page.locator('img,iframe,object').count()==0
            assert page.locator('script').count()==1; checks.append('markup_fixture_remains_inert_text')
            page.select_option('#status','error'); assert visible(page)==1 and '无法核对' in page.locator('.card:not([hidden])').inner_text(); checks.append('artifact_error_filter_distinct_from_unfinished')
            context.close()
            mobile=wire(browser.new_context(offline=True,viewport={'width':390,'height':844},device_scale_factor=1))
            page=mobile.new_page(); page.goto(real.as_uri()); page.locator('html.enhanced').wait_for(); assert no_overflow(page)
            page.fill('#query','RECEIPT'); assert visible(page)==1 and no_overflow(page)
            page.screenshot(path=str(output/'mobile.png'),full_page=True); checks.append('390px_mobile_controls_and_content_without_horizontal_overflow'); mobile.close()
            plain=wire(browser.new_context(offline=True,java_script_enabled=False,viewport={'width':1280,'height':900}))
            page=plain.new_page();page.goto(real.as_uri());assert visible(page)==4 and not page.locator('.toolbar').is_visible()
            assert page.locator('.card.submitted .answer').count()==3; checks.append('all_records_readable_without_javascript');plain.close()
            version=browser.version
        finally: browser.close()
    assert not errors and not network
    result={'ready':True,'browser_version':version,'checks':checks,'checks_passed':len(checks),'page_errors':errors,
            'automatic_network_requests':len(network),'offline_file_navigation':True,'new_generation_requests':0,
            'new_embedding_forwards':0,'GPU_disabled':True,'real_closed_runs':4,'extra_record_only_in_control_fixture':True,
            'screenshots':{n:{'sha256':hashlib.sha256((output/n).read_bytes()).hexdigest(),'bytes':(output/n).stat().st_size} for n in ['desktop.png','mobile.png']}}
    (output/'browser-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':run(*map(Path,sys.argv[1:]))
