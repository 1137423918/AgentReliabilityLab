"""Actual browser note roundtrips on owned demo; real runs remain unreviewed."""
from pathlib import Path
import copy
import hashlib
import json
import sys

from playwright.sync_api import expect, sync_playwright

from agent_lab.research_review import initial_decisions, validate_decisions


def run(application, demo, output):
    output.mkdir(mode=0o700, exist_ok=False)
    demo_bundle = json.loads((demo / 'source-review.json').read_text())
    real_bundle = json.loads((application / 'real/source-review.json').read_text())
    demo_page = demo / 'source-review.html'
    real_page = application / 'real/source-review.html'
    checks, errors, network = [], [], []

    def wire(context):
        def route(request):
            if request.request.url.startswith('file:'):
                request.continue_()
            else:
                network.append(request.request.url.split(':', 1)[0]); request.abort()
        context.route('**/*', route)
        context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
        return context

    def visible(page):
        return page.locator('.review-item:not([hidden])').count()

    def download(page, name):
        with page.expect_download() as event:
            page.click('#save-notes')
        target = output / name
        event.value.save_as(target)
        return json.loads(target.read_text())

    def upload(page, name, value):
        page.set_input_files('#load-notes', {'name': name, 'mimeType': 'application/json',
                                           'buffer': json.dumps(value, ensure_ascii=False).encode()})
        expect(page.locator('#load-notes')).to_have_value('')

    def no_overflow(page):
        return page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')

    def state(page):
        return page.evaluate('''() => ({reviewer: document.querySelector('#reviewer').value,
          rows: Array.from(document.querySelectorAll('.review-item')).map(item => ({
            decision: item.querySelector('.decision').value, notes: item.querySelector('textarea').value}))})''')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-gpu', '--disable-dev-shm-usage', '--renderer-process-limit=2'])
        try:
            context = wire(browser.new_context(offline=True, viewport={'width': 1320, 'height': 920}, accept_downloads=True))
            page = context.new_page(); page.goto(demo_page.as_uri()); page.locator('html.enhanced').wait_for()
            assert visible(page) == 3 and no_overflow(page)
            assert page.locator('.passage blockquote').all_text_contents() == [demo_bundle['entries'][0]['passages'][0]['excerpt']]
            assert page.locator('.decision').evaluate_all('(elements) => elements.map(element => element.value)') == ['pending', 'unavailable', 'unavailable']
            checks.append('owned_demo_exact_passage_and_pending_states')

            page.fill('#query', 'interruption'); assert visible(page) == 1
            page.select_option('#status', 'needs_changes'); assert visible(page) == 0 and page.locator('#empty').is_visible()
            page.click('#reset'); assert visible(page) == 3
            checks.append('source_text_search_combined_filter_empty_and_reset')

            page.select_option('#decision-1', 'needs_changes')
            notes_text = '🧪' * 998 + '\n中'
            page.fill('#notes-1', notes_text); page.fill('#reviewer', '👩' * 120)
            page.select_option('#status', 'needs_changes'); assert visible(page) == 1
            saved = download(page, 'downloaded-demo-notes.json')
            assert saved['entries'][0]['notes'] == notes_text and saved['reviewer'] == '👩' * 120
            assert len(saved['entries']) == 3 and validate_decisions(demo_bundle, saved) == saved
            checks.append('filtered_download_contains_all_entries_and_backend_accepts_unicode_boundaries')

            page.reload(); page.locator('html.enhanced').wait_for()
            assert page.input_value('#notes-1') == '' and page.input_value('#decision-1') == 'pending'
            assert page.evaluate('localStorage.length') == 0
            page.set_input_files('#load-notes', str(output / 'downloaded-demo-notes.json'))
            expect(page.locator('#notes-1')).to_have_value(notes_text)
            assert page.input_value('#notes-1') == notes_text and page.input_value('#reviewer') == '👩' * 120
            assert page.input_value('#decision-1') == 'needs_changes'
            checks.append('reload_has_no_persistence_and_explicit_import_restores_full_notes')

            before = state(page)
            stale = copy.deepcopy(saved); stale['bundle_sha256'] = '0' * 64
            upload(page, 'stale.json', stale)
            expect(page.locator('#feedback')).to_have_attribute('data-error', 'true')
            assert state(page) == before
            checks.append('different_bundle_refused_without_changing_current_notes')

            mixed = copy.deepcopy(saved); mixed['entries'][0].update(decision='checked', notes='Must not partially apply')
            mixed['entries'][-1]['decision'] = 'checked'
            upload(page, 'mixed.json', mixed)
            assert state(page) == before
            checks.append('whole_file_validated_before_applying_any_entry')

            duplicate = copy.deepcopy(saved); duplicate['entries'][-1] = copy.deepcopy(duplicate['entries'][0])
            upload(page, 'duplicate.json', duplicate)
            assert state(page) == before
            checks.append('duplicate_or_missing_entry_refused')

            for name, bad in [('extra', {**saved, 'extra': True}), ('bool-version', {**saved, 'version': True})]:
                upload(page, name + '.json', bad)
                assert state(page) == before
            too_long = copy.deepcopy(saved); too_long['entries'][0]['notes'] = '😀' * 1001
            upload(page, 'long-notes.json', too_long)
            assert state(page) == before
            checks.append('unknown_fields_boolean_version_and_long_unicode_notes_refused')

            page.set_input_files('#load-notes', {'name': 'large.json', 'mimeType': 'application/json', 'buffer': b' ' * (1024**2 + 1)})
            expect(page.locator('#feedback')).to_contain_text('1MiB')
            assert state(page) == before
            checks.append('oversized_note_file_refused_before_parsing')

            hostile = copy.deepcopy(saved)
            hostile['entries'][0]['notes'] = '</textarea><script>window.attacked=1</script><img src=https://invalid.example/pixel onerror="window.attacked=2">'
            upload(page, 'text-only.json', hostile)
            assert page.evaluate('window.attacked === undefined') and page.locator('img,iframe,object').count() == 0
            assert page.locator('script').count() == 1
            checks.append('imported_markup_remains_inert_note_text')

            page.select_option('#status', 'needs_changes'); page.emulate_media(media='print')
            assert visible(page) == 1 and not page.locator('#notes-1').is_visible()
            assert page.locator('.review-item:not([hidden]) .print-annotation').is_visible()
            assert hostile['entries'][0]['notes'] in page.locator('.review-item:not([hidden]) .print-annotation').inner_text()
            page.emulate_media(media='screen')
            checks.append('printing_keeps_filter_and_complete_text_notes')

            page.goto(real_page.as_uri()); page.locator('html.enhanced').wait_for()
            assert visible(page) == 4 and page.locator('.passage blockquote').count() == 6
            expected_excerpts = [passage['excerpt'] for entry in real_bundle['entries'] for passage in entry['passages']]
            assert page.locator('.passage blockquote').all_text_contents() == expected_excerpts
            assert page.locator('.decision').evaluate_all('(elements) => elements.map(element => element.value)') == ['pending', 'pending', 'unavailable', 'pending']
            real_notes = download(page, 'unchanged-real-pending-notes.json')
            assert real_notes == initial_decisions(real_bundle)
            validate_decisions(real_bundle, real_notes)
            page.select_option('#status', 'unavailable'); assert visible(page) == 1 and 'LS-DETR' in page.locator('.review-item:not([hidden]) h2').inner_text()
            page.click('#reset'); page.fill('#query', 'RECEIPT'); assert visible(page) == 1
            checks.append('four_real_runs_six_exact_excerpts_remain_unreviewed_with_original_failure')
            # Only owned synthetic demonstration material is screenshotted/public.
            page.goto(demo_page.as_uri()); page.locator('html.enhanced').wait_for()
            page.select_option('#decision-1', 'needs_changes'); page.fill('#notes-1', '脚本化界面演示：记录需要补充的边界，不代表真实论文核查结论。')
            page.screenshot(path=str(output / 'desktop.png'), full_page=True)
            context.close()

            mobile = wire(browser.new_context(offline=True, viewport={'width': 390, 'height': 844}, device_scale_factor=1))
            page = mobile.new_page(); page.goto(demo_page.as_uri()); page.locator('html.enhanced').wait_for()
            assert no_overflow(page); page.select_option('#decision-1', 'needs_changes'); page.fill('#notes-1', '脚本化演示备注，可下载后导入继续。')
            page.select_option('#status', 'needs_changes'); assert visible(page) == 1 and no_overflow(page)
            page.click('#reset'); page.screenshot(path=str(output / 'mobile.png'), full_page=True)
            checks.append('390px_mobile_review_controls_no_horizontal_overflow'); mobile.close()

            plain = wire(browser.new_context(offline=True, java_script_enabled=False, viewport={'width': 1320, 'height': 920}))
            page = plain.new_page(); page.goto(demo_page.as_uri())
            assert visible(page) == 3 and page.locator('.passage blockquote').count() == 1
            assert not page.locator('#save-notes').is_visible()
            checks.append('original_answers_and_passages_readable_without_javascript'); plain.close()
            version = browser.version
        finally:
            browser.close()
    assert not errors and not network
    result = {'ready': True, 'checks': checks, 'checks_passed': len(checks), 'browser_version': version,
              'page_errors': errors, 'automatic_network_requests': len(network), 'new_generation_requests': 0,
              'new_embedding_forwards': 0, 'GPU_disabled': True,
              'real_notes_not_changed_or_human_reviewed': True, 'annotations_exercised_only_on_owned_demo': True,
              'public_screenshots_contain_only_owned_demo': True,
              'screenshots': {n: {'sha256': hashlib.sha256((output / n).read_bytes()).hexdigest(), 'bytes': (output / n).stat().st_size}
                              for n in ['desktop.png', 'mobile.png']}}
    (output / 'browser-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    run(*map(Path, sys.argv[1:]))
