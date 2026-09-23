import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('briefing', ROOT / 'scripts/briefing.py')
briefing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(briefing)


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / 'templates/attention-contract.json').read_text())
        self.record = json.loads((ROOT / 'examples/selection.json').read_text())

    def test_same_selection_renders_all_interfaces_without_mutation(self):
        before = copy.deepcopy(self.record)
        for interface in ('agent_summary', 'briefing_html', 'discovery_html'):
            result = briefing.render(self.contract, self.record, interface)
            self.assertIn('A practical method', result)
            self.assertIn('https://example.org/items/1', result)
            self.assertIn('inspection limit reached', result)
            self.assertIn('1 of 1 source area visited', result)
            self.assertIn('ask Attention Diet to tune your contract', result)  # The way to change what reaches you.
        self.assertEqual(before, self.record)

    def test_configured_templates_are_loaded_for_each_interface_and_base(self):
        before = copy.deepcopy(self.record)
        for interface in ('agent_summary', 'briefing_html', 'discovery_html'):
            for base in ('plugin_root', 'contract_dir'):
                with self.subTest(interface=interface, base=base), tempfile.TemporaryDirectory() as folder:
                    path = Path(folder)
                    offline = ('' if interface == 'agent_summary' else
                               '\n<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">')
                    (path / 'custom.template').write_text('Custom $$ layout\n$title\n$overview\n$content\n$notices' + offline)
                    contract = copy.deepcopy(self.contract)
                    contract['composition'].update(interface=interface,
                        format='markdown' if interface == 'agent_summary' else 'html',
                        template='custom.template', template_path_base=base)
                    with patch.object(briefing, 'ROOT', path):
                        rendered = briefing.render(contract, self.record, contract_dir=path)
                    self.assertTrue(rendered.startswith('Custom $ layout'))
                    self.assertIn('A practical method', rendered)
                    self.assertIn('inspection limit reached', rendered)
        self.assertEqual(before, self.record)

    def test_partial_surfaces_are_grouped_without_changing_coverage_or_memory(self):
        thread = self.contract['coverage_threads'][0]
        for surface in ('messages', 'notifications'):
            thread['surfaces'].append(surface)
            thread['entry_urls'][surface] = 'https://example.org/' + surface
            self.record['coverage'].append({**self.record['coverage'][0], 'surface': surface})
        self.record['coverage'][0].update(
            read_state_effect='unknown', evidence='PRIVATE_DIAGNOSTIC: extraction failed at ticket abc',
            notices=['One identified card had incomplete text and was withheld from selection.'])
        before = copy.deepcopy(self.record)
        payloads = briefing.memory_payloads(self.contract, self.record)
        for interface in ('agent_summary', 'briefing_html', 'discovery_html'):
            rendered = briefing.render(self.contract, self.record, interface)
            self.assertEqual(rendered.count('inspection limit reached'), 3)
            self.assertIn('effect on read state is unknown', rendered)
            for diagnostic in ('PRIVATE_DIAGNOSTIC', 'source-1/', 'item_ceiling', 'more=true',
                               '30 inspected', 'One identified card'):
                self.assertNotIn(diagnostic, rendered)
        self.assertEqual(self.record, before)
        self.assertEqual(briefing.memory_payloads(self.contract, self.record), payloads)
        self.assertIn('PRIVATE_DIAGNOSTIC', payloads[0]['payload']['coverage'])
        self.assertIn('partial; 30 inspected; more=true; item_ceiling', payloads[0]['payload']['coverage'])

    def test_consequential_warnings_survive_and_known_diagnostics_are_translated(self):
        self.record['coverage'][0].update(status='checked', more_available=False,
            stop_reason='exhausted_results', read_state_effect='unknown')
        self.record['notices'] = [
            'Some known items have incompatible or undocumented fingerprint methods; novelty is uncertain',
            'Some known items have changed captures without reliable evidence of a new event; novelty is uncertain',
            'Some items could not be reliably compared with earlier briefings and were withheld.',
            'Provider history was not retrieved', 'A history document could not be validated',
            'Briefing memory could not be saved (PRIVATE_PATH: disk full); continuity is limited.',
            'Sign in as expected@example.org; observed other@example.org.',
        ]
        self.record['coverage'][0]['notices'] = ['An unfamiliar warning requiring user action.']
        for interface in ('agent_summary', 'briefing_html', 'discovery_html'):
            rendered = briefing.render(self.contract, self.record, interface)
            self.assertEqual(rendered.count('Some items could not be reliably compared'), 1)
            self.assertEqual(rendered.count('Earlier briefings were not fully available'), 1)
            self.assertIn('effect on read state is unknown', rendered)
            self.assertIn('Briefing memory could not be saved', rendered)
            self.assertIn('Sign in as expected@example', rendered)
            self.assertIn('An unfamiliar warning requiring user action', rendered)
            for diagnostic in ('fingerprint', 'PRIVATE_PATH', 'Provider history', 'history document'):
                self.assertNotIn(diagnostic, rendered)

    def test_unavailable_unchecked_and_quiet_results_do_not_claim_full_coverage(self):
        self.record['entries'] = []
        for status, reason, expected in (
            ('unavailable', 'access_failure', 'Example-source was unavailable.'),
            ('not_checked', 'not_checked', 'Example-source was not checked.'),
        ):
            self.record['coverage'][0].update(status=status, stop_reason=reason,
                inspected_count=0, more_available=None, evidence='INTERNAL_ERROR')
            self.assertEqual(briefing.briefing_notices(self.contract, self.record)[0], expected)
            self.assertNotIn('INTERNAL_ERROR', briefing.render(self.contract, self.record))
        self.record['coverage'][0].update(status='checked', stop_reason='exhausted_results', more_available=False)
        self.record['notices'] = []
        self.assertEqual(briefing.briefing_notices(self.contract, self.record), [])

    def test_notice_already_in_overview_is_not_repeated(self):
        self.record['overview'] = 'No new items. inspection limit reached Example-source.'
        self.assertNotIn('inspection limit reached Example-source.',
                         briefing.briefing_notices(self.contract, self.record))

    def test_html_layouts_share_markup_and_differ_by_layout_class(self):
        pages = {name: briefing.render(self.contract, self.record, name) for name in ('briefing_html', 'discovery_html')}
        self.assertIn('<body class="briefing">', pages['briefing_html'])
        self.assertIn('<body class="discovery">', pages['discovery_html'])
        for page in pages.values():
            self.assertIn('<p class="why">', page)
            self.assertIn('<span>example-source · items</span>', page)
            self.assertIn("default-src 'none'", page)
            self.assertNotIn('<script', page)

    def test_data_view_receives_inert_json_and_must_stay_offline(self):
        self.record['entries'][0]['summary'] = 'Breaks out </script><img src=x onerror=alert(1)> & more\u2028.'
        self.contract['composition'].update(interface='briefing_html', format='html', template='view.html',
                                            template_path_base='contract_dir')
        csp = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'">'
        island = '<script type="application/json" id="attention-data">$data</script>'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'view.html').write_text('<title>$title</title>' + island + '<footer>$notices</footer>')
            with self.assertRaisesRegex(ValueError, 'Content-Security-Policy'):
                briefing.render(self.contract, self.record, contract_dir=path)
            (path / 'view.html').write_text(csp + '<title>$title</title>' + island)
            with self.assertRaisesRegex(ValueError, 'notices'):
                briefing.render(self.contract, self.record, contract_dir=path)
            (path / 'view.html').write_text(csp + '<title>$title</title>' + island + '<footer>$notices</footer>')
            page = briefing.render(self.contract, self.record, contract_dir=path)
        payload = page.split(' id="attention-data">', 1)[1].split('</script>', 1)[0]
        for unsafe in ('<', '>', '&', '\u2028'):
            self.assertNotIn(unsafe, payload)
        data = json.loads(payload)
        self.assertEqual(data['sections'][0]['entries'][0]['summary'], self.record['entries'][0]['summary'])
        self.assertEqual(data['sections'][0]['name'], 'Updates')
        self.assertEqual(data['coverage'][0], {'source': 'example-source · items', 'status': 'partial',
                                               'inspected_count': 30, 'more_available': True, 'stop_reason': 'item_ceiling'})
        self.assertIn('inspection limit reached', ' '.join(data['notices']))

    def test_plain_html_view_must_also_stay_offline(self):
        self.contract['composition'].update(interface='briefing_html', format='html', template='plain.html',
                                            template_path_base='contract_dir')
        body = '<title>$title</title><p>$overview</p>$content<img src="https://example.org/t.gif"><footer>$notices</footer>'
        csp = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'plain.html').write_text(body)
            with self.assertRaisesRegex(ValueError, 'Content-Security-Policy'):
                briefing.render(self.contract, self.record, contract_dir=path)
            (path / 'plain.html').write_text(csp + body)
            self.assertIn("default-src 'none'", briefing.render(self.contract, self.record, contract_dir=path))

    def test_bundled_example_view_renders_as_a_preview_and_follows_its_own_rules(self):
        path = ROOT / 'interfaces/html/example-view.html'
        source = path.read_text()
        for forbidden in ('innerHTML', 'insertAdjacentHTML', 'document.write', 'http://', 'https://'):
            self.assertNotIn(forbidden, source.replace("/^https?:\\/\\//", ''))
        page = briefing.render(self.contract, self.record, 'briefing_html', template_path=path)
        self.assertIn("default-src 'none'", page)
        self.assertIn('inspection limit reached', page)  # Notices stay visible outside the script.
        self.assertEqual(json.loads(page.split(' id="attention-data">', 1)[1].split('</script>', 1)[0])['title'],
                         self.record['title'])
        # A preview never changes which template the contract delivers.
        self.assertNotIn('attention-data', briefing.render(self.contract, self.record, 'briefing_html'))

    def test_missing_invalid_and_incomplete_templates_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.contract['composition'].update(template='custom.md', template_path_base='contract_dir')
            with self.assertRaisesRegex(ValueError, 'Cannot read output template'):
                briefing.render(self.contract, self.record, contract_dir=path)
            for text, message in (
                ('$title $overview $notices', 'content'),
                ('$title $overview $content $notices $unknown', 'Unknown output template'),
                ('$title $overview $content $notices $', 'Invalid template placeholder')):
                (path / 'custom.md').write_text(text)
                with self.assertRaisesRegex(ValueError, message):
                    briefing.render(self.contract, self.record, contract_dir=path)

    def test_markdown_preview_of_html_contract_uses_builtin_markdown(self):
        self.contract['composition'].update(interface='briefing_html', format='html', template='missing.html')
        rendered = briefing.render(self.contract, self.record, 'agent_summary')
        self.assertTrue(rendered.startswith('**Attention overview**'))
        self.assertIn('A practical method', rendered)

    def test_template_substitution_does_not_interpret_source_placeholders(self):
        self.record['entries'][0]['summary'] = 'Literal $content and ${notices} from the source.'
        rendered = briefing.render(self.contract, self.record)
        self.assertIn('$content', rendered)
        self.assertIn('$\\{notices\\}', rendered)

    def test_new_services_need_configuration_only(self):
        for service in ('calendar', 'support-desk', 'reading-room'):
            contract = copy.deepcopy(self.contract)
            record = copy.deepcopy(self.record)
            contract['coverage_threads'][0]['service'] = service
            contract['run_limits']['service_minutes'] = {service: 5}
            record['entries'][0]['items'][0]['service'] = service
            record['entries'][0]['account_key'] = service + ':account'
            briefing.validate(contract, record)
            self.assertIn('A practical method', briefing.render(contract, record))
            self.assertEqual(briefing.memory_payloads(contract, record)[0]['service'], service)

    def test_browser_choice_does_not_change_selected_output_or_memory(self):
        rendered = briefing.render(self.contract, self.record)
        payloads = briefing.memory_payloads(self.contract, self.record)
        for provider in ('host_default', 'codex_in_app', 'claude_browser', 'agent_browser'):
            with self.subTest(provider=provider):
                contract = copy.deepcopy(self.contract)
                contract['coverage_threads'][0]['access']['provider'] = provider
                self.assertEqual(briefing.render(contract, self.record), rendered)
                self.assertEqual(briefing.memory_payloads(contract, self.record), payloads)

    def test_unknown_scope_identity_and_overflow_rejected(self):
        mutations = [lambda r: r.update(contract_id='other'),
                     lambda r: r.update(contract_revision=2),
                     lambda r: r['coverage'].clear(),
                     lambda r: r['entries'][0].update(surface='unconfigured'),
                     lambda r: r['entries'][0].update(section='unconfigured'),
                     lambda r: r['entries'][0]['items'][0].update(service='another-service'),
                     lambda r: r['entries'].append(copy.deepcopy(r['entries'][0])),
                     lambda r: r['entries'][0].update(url='javascript:alert(1)'),
                     lambda r: r['coverage'][0].update(status='checked'),
                     lambda r: r['coverage'][0].update(inspected_count=0)]
        for change in mutations:
            record = copy.deepcopy(self.record)
            change(record)
            with self.assertRaises(ValueError):
                briefing.validate(self.contract, record)
        self.contract['composition']['max_items_by_thread']['source-1'] = 1
        second = copy.deepcopy(self.record['entries'][0])
        second.update(id='second');second['items'][0]['identifier'] = 'topic-2'
        self.record['entries'].append(second)
        with self.assertRaisesRegex(ValueError, 'ceiling'):
            briefing.validate(self.contract, self.record)

    def test_memory_uses_only_selected_versions_and_no_render_side_effects(self):
        memory = briefing.contract_api.memory
        with tempfile.TemporaryDirectory() as folder:
            self.contract['memory_context']['directory'] = folder
            briefing.render(self.contract, self.record)
            self.assertEqual(list(Path(folder).iterdir()), [])
            group = briefing.memory_payloads(self.contract, self.record)[0]
            self.assertEqual(group['payload']['items'], self.record['entries'][0]['items'])
            history = memory.load_history(self.contract, group['account_key'])
            saved = memory.build_record(self.contract, group['account_key'], group['payload'], history)
            memory.save_local(self.contract, saved)
            comparison = memory.compare(memory.load_history(self.contract, group['account_key']), group['payload']['items'])
            self.assertEqual(comparison['new_items'], [])

    def test_memory_stays_separate_for_services_and_accounts(self):
        contract = copy.deepcopy(self.contract)
        second = copy.deepcopy(contract['coverage_threads'][0])
        second.update(id='second-source', service='second-service')
        contract['coverage_threads'].append(second)
        self.record['coverage'].append({'thread_id':'second-source','surface':'items','status':'checked',
            'inspected_count':1,'more_available':False,'stop_reason':'exhausted_results','evidence':'End of list observed.'})
        private = copy.deepcopy(self.record['entries'][0])
        private.update(id='message-1',thread_id='second-source',account_key='second-service:account')
        private['items'][0]['service'] = 'second-service'
        self.record['entries'].append(private)
        groups = briefing.memory_payloads(contract, self.record)
        self.assertEqual(len(groups), 2)
        for group in groups:
            self.assertEqual({i['service'] for i in group['payload']['items']}, {group['service']})
        private['account_key'] = self.record['entries'][0]['account_key']
        with self.assertRaisesRegex(ValueError, 'scoped to one service'):
            briefing.validate(contract, self.record)
        private['account_key'] = None
        with self.assertRaisesRegex(ValueError, 'Private entries'):
            briefing.validate(contract, self.record)

    def test_unknown_public_account_does_not_invent_memory(self):
        self.contract['coverage_threads'][0]['content'] = 'public_posts'
        self.record['entries'][0]['account_key'] = None
        self.assertEqual(briefing.memory_payloads(self.contract, self.record), [])
        self.assertIn('cannot be saved', briefing.render(self.contract, self.record))

    def test_html_and_markdown_escape_source_text(self):
        self.record['entries'][0]['title'] = '<script>alert(1)</script> [click](javascript:alert(1))'
        for interface in ('agent_summary', 'briefing_html'):
            rendered = briefing.render(self.contract, self.record, interface)
            self.assertNotIn('<script>', rendered)
            self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('\\[click\\]', briefing.render(self.contract, self.record))

    def test_empty_partial_and_surprise_results(self):
        empty = copy.deepcopy(self.record)
        empty['entries'] = []
        self.assertEqual(briefing.memory_payloads(self.contract, empty), [])
        self.assertIn('inspection limit reached', briefing.render(self.contract, empty))
        self.record['entries'][0].update(slot='serendipity', topic='tidal energy')
        with self.assertRaisesRegex(ValueError, 'not authorized'):
            briefing.validate(self.contract, self.record)
        self.contract['serendipity'].update(enabled=True, sources=['source-1/items'])
        briefing.validate(self.contract, self.record)
        self.assertIn('Outside your interests', briefing.render(self.contract, self.record))
        item = briefing.memory_payloads(self.contract, self.record)[0]['payload']['items'][0]
        self.assertEqual(item['topic'], 'tidal energy')

    def test_schema_agrees_on_example_and_missing_fields(self):
        validator = briefing.contract_api.memory.schema_validation.validator('selection.schema.json')
        validator.validate(self.record)
        for extra in ({'fingerprint_method': 'unknown/v1'}, {'source_timestamp': 'yesterday'},
                      {'slot': 'serendipity', 'topic': 'tidal energy'}, {'unknown': True}):
            changed = copy.deepcopy(self.record)
            changed['entries'][0]['items'][0].update(extra)
            self.assertTrue(list(validator.iter_errors(changed)))
            with self.assertRaises(ValueError):
                briefing.validate(self.contract, changed)
        del self.record['entries'][0]['items']
        self.assertTrue(list(validator.iter_errors(self.record)))


if __name__ == '__main__':
    unittest.main()
