"""Synthetic replay of the September 19 inefficiencies; no accounts or private source text."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('runtime', ROOT / 'scripts/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
memory, briefing, budget = runtime.memory, runtime.briefing, runtime.budget


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'XDG_STATE_HOME': self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.contract = json.loads((ROOT / 'templates/attention-contract.json').read_text())
        self.contract['memory_context']['directory'] = self.tmp.name + '/memory'
        self.path = Path(self.tmp.name) / 'contract.json'
        self.path.write_text(json.dumps(self.contract))
        opened = runtime.start(self.path)
        self.state = memory.read_json(budget.state_path(opened['run_id']))
        self.workspace = Path(self.state['workspace'])
        self.addCleanup(self.clean_workspace)
        budget.begin_service(self.state, 'example-source')
        self.url = 'https://x.com/Example/status/123'
        self.basis = {'sender': 'Example', 'text': 'Exact punctuation! A “quote”, and an emoji 👀.'}
        self.capture = {'account_key': 'example-source:account', 'items': [
            {'ref': 'one', 'thread_id': 'source-1', 'surface': 'items', 'identifier': self.url, 'basis': self.basis}],
            'surfaces': [{'thread_id': 'source-1', 'surface': 'items', 'identifiers': [self.url],
                          'more_available': False, 'evidence': 'Explicit end-of-list marker observed.', 'exhaustion': {'kind': 'explicit_end_marker', 'evidence': 'Explicit end-of-list marker observed.'}}]}
        example = json.loads((ROOT / 'examples/selection.json').read_text())
        entry = example['entries'][0]
        entry.pop('items')
        entry.update(item_refs=['one'], url=self.url)
        self.draft = {'title': 'Test briefing', 'overview': 'One selected source report.', 'entries': [entry], 'notices': []}

    def clean_workspace(self):
        if self.workspace.exists():
            for path in self.workspace.iterdir():
                path.unlink()
            self.workspace.rmdir()

    def remote(self, contents):
        contract = copy.deepcopy(self.contract)
        contract['memory_context'].pop('directory')
        contract['memory_context'].update(provider='supermemory', space='test-space')
        export = {'space': 'test-space', 'complete': True, 'documents': [
            {'id': str(i), 'status': 'done', 'contentTruncated': False, 'content': text}
            for i, text in enumerate(contents)]}
        return contract, export

    def test_unrelated_note_is_not_corrupt_history_but_broken_envelope_is(self):
        contract, export = self.remote(['An ordinary unrelated project note.'])
        self.assertEqual(memory.load_history(contract, 'account', export), {'records': [], 'warnings': []})
        export['documents'].append({'id': 'broken', 'status': 'done', 'contentTruncated': False,
                                     'content': '---\n{"schema_version":"attention-summary/1.0"}\n---\nBroken'})
        self.assertTrue(memory.load_history(contract, 'account', export)['warnings'])
        export['documents'][0]['contentTruncated'] = True
        self.assertIn('A provider document is not fully available', memory.load_history(contract, 'account', export)['warnings'])

    def test_loading_then_repeated_feed_cards_count_28_not_30(self):
        batch = {'account_key': self.capture['account_key'], 'items': [], 'surfaces': [
            {'thread_id': 'source-1', 'surface': 'items', 'identifiers': [], 'more_available': False, 'loading': True}]}
        result = runtime.collect_batch(self.state, self.contract, batch)
        self.assertEqual(result['coverage'][0]['action'], 'inspect_availability')
        self.assertIsNone(result['coverage'][0]['stop_reason'])
        ids = [f'https://x.com/Example/status/{i}' for i in range(28)]
        batch['surfaces'][0] = {'thread_id': 'source-1', 'surface': 'items', 'identifiers': ids +
            [ids[0] + '/analytics', ids[1] + '/analytics?s=20'], 'more_available': True}
        result = runtime.collect_batch(self.state, self.contract, batch)
        self.assertEqual(result['coverage'][0]['inspected_count'], 28)
        self.assertEqual(result['coverage'][0]['action'], 'load_more')
        # Re-reading the whole page is idempotent, not another 28 inspections.
        result = runtime.collect_batch(self.state, self.contract, batch)
        self.assertEqual(result['coverage'][0]['inspected_count'], 28)

    def test_no_manual_count_or_budget_copy_and_no_fabricated_exhaustion(self):
        for mutation in ({'inspected_count': 99}, {'evidence': ''}):
            batch = copy.deepcopy(self.capture)
            batch['surfaces'][0].update(mutation)
            with self.assertRaises(ValueError):
                runtime.collect_batch(copy.deepcopy(self.state), self.contract, batch)
        report = runtime.collect_batch(self.state, self.contract, self.capture)
        self.assertEqual(report['budget']['run_id'], self.state['run_id'])

    def test_fingerprints_preserve_raw_text_and_are_not_editorial_fields(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        actual = self.state['candidates']['one']['item']
        self.assertEqual(actual['change_fingerprint'], memory.fingerprint(self.basis))
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            changed = copy.deepcopy(self.capture)
            changed['items'][0]['basis']['text'] = 'A rewritten version.'
            runtime.collect_batch(self.state, self.contract, changed)
        budget.seal(self.state)
        draft = copy.deepcopy(self.draft)
        draft['entries'][0]['items'] = []
        with self.assertRaisesRegex(ValueError, 'item_refs'):
            runtime.finalize(self.state, self.contract, draft)

    def test_unknown_read_state_survives_checked_coverage_and_later_pages(self):
        self.capture['surfaces'][0]['automatic_selection'] = True
        runtime.collect_batch(self.state, self.contract, self.capture)
        self.capture['surfaces'][0].pop('automatic_selection')
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        self.assertEqual(self.state['selection']['coverage'][0]['status'], 'checked')
        self.assertIn('read state is unknown', Path(self.state['output_path']).read_text())
        artifacts = memory.read_json(self.workspace / 'memory.json')['artifacts']
        self.assertIn('read state is unknown', memory.decode(artifacts[0]['content'])['coverage'])

    def test_minimal_draft_recovers_scope_and_saves_the_same_included_version(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        entry = self.draft['entries'][0]
        expected = {k: entry.pop(k) for k in ('account_key', 'thread_id', 'surface', 'section', 'id')}
        runtime.finalize(self.state, self.contract, self.draft)
        actual = self.state['selection']['entries'][0]
        for key in ('account_key', 'thread_id', 'surface', 'section'):
            self.assertEqual(actual[key], expected[key])
        self.assertEqual(actual['id'], 'e1')
        saved = memory.decode(memory.read_json(self.workspace / 'memory.json')['artifacts'][0]['content'])
        self.assertEqual(saved['items'], actual['items'])

    def test_minimal_draft_cannot_override_captured_scope_or_guess_ambiguous_section(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        for key in ('account_key', 'thread_id', 'surface'):
            draft = copy.deepcopy(self.draft)
            draft['entries'][0][key] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'preserve the captured'):
                runtime.finalize(copy.deepcopy(self.state), self.contract, draft)
        draft = copy.deepcopy(self.draft)
        draft['entries'][0].pop('section')
        contract = copy.deepcopy(self.contract)
        contract['composition']['sections'].append('another-section')
        with self.assertRaisesRegex(ValueError, 'Choose a configured section'):
            runtime.finalize(copy.deepcopy(self.state), contract, draft)

    def test_caveats_survive_both_interfaces_and_memory_without_truncation(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        self.draft['entries'][0].update(why='A source claim, not independently verified.', caveats=['Only its preview was inspected.'])
        runtime.finalize(self.state, self.contract, self.draft)
        for interface in ('agent_summary', 'briefing_html'):
            text = briefing.render(self.contract, self.state['selection'], interface)
            self.assertIn('not independently verified', text)
            self.assertIn('Only its preview was inspected', text)
        saved = memory.decode(memory.read_json(self.workspace / 'memory.json')['artifacts'][0]['content'])
        self.assertIn('not independently verified', saved['summary'])
        self.assertIn('Only its preview was inspected', saved['summary'])

    def test_short_history_keeps_context_and_topics_without_item_hashes(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        saved = memory.decode(memory.read_json(self.workspace / 'memory.json')['artifacts'][0]['content'])
        memory.save_local(self.contract, saved)
        loaded = memory.load_history(self.contract, self.capture['account_key'])
        self.assertNotIn('items', memory.context(loaded, self.contract)['latest']['record'])
        self.assertIn('items', memory.context(loaded, self.contract, full=True)['latest']['record'])
        state = copy.deepcopy(self.state)
        state['phase'] = 'collecting'
        budget.begin_service(state, 'example-source')
        result = runtime.collect_batch(state, self.contract, self.capture)
        self.assertEqual(result['decisions'], {'one': 'already_briefed'})
        budget.seal(state)
        state['finalized'] = False
        with self.assertRaisesRegex(ValueError, 'compared new'):
            runtime.finalize(state, self.contract, self.draft)

    def test_collection_seal_reserve_and_finish_cover_finalization_time(self):
        start = budget.now()
        self.state['started_at'] = start.isoformat()
        with self.assertRaisesRegex(ValueError, 'Seal'):
            budget.finish(self.state)
        report = budget.check(self.state, start + timedelta(seconds=550))
        self.assertFalse(report['over'])
        self.assertTrue(report['collection_over'])
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state, start + timedelta(seconds=550))
        with self.assertRaisesRegex(ValueError, 'sealed'):
            runtime.collect_batch(self.state, self.contract, self.capture)
        runtime.finalize(self.state, self.contract, self.draft)
        report = budget.finish(self.state, start + timedelta(seconds=580))
        self.assertEqual(report['used_seconds'], 580)
        self.assertEqual(report['phase'], 'complete')

    def test_one_private_workspace_and_automatic_cleanup(self):
        self.assertEqual(stat.S_IMODE(self.workspace.stat().st_mode), 0o700)
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        files = list(self.workspace.iterdir())
        self.assertEqual(len(files), 4)
        for path in files:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        result = runtime.finish(self.state, self.contract, notices=['Storage verification is pending.'])
        self.assertIn('Storage verification is pending', result['rendered'])
        self.assertFalse(self.workspace.exists())

    def test_finalized_selection_cannot_be_rewritten(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        with self.assertRaisesRegex(ValueError, 'already finalized'):
            runtime.finalize(self.state, self.contract, self.draft)

    def test_exhausted_sample_is_not_checked(self):
        self.contract['coverage_threads'][0]['collection']['items'] = {'mode': 'sample', 'max_items': 30}
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        self.assertEqual(self.state['selection']['coverage'][0]['status'], 'partial')

    def test_batch_cli_uses_one_process_and_stdin(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/briefing_memory.py'),
                                 'fingerprint-batch', '--input', '-'], input=json.dumps([self.basis] * 19),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [memory.fingerprint_metadata(self.basis)] * 19)

    def test_canonical_link_and_contract_post_id_count_as_one_item(self):
        self.assertEqual(runtime.coverage.identity.distinct_identifiers([
            self.url, self.url + '/analytics', 'https://twitter.com/Example/status/123?s=20', 'x:post:123']), ['x-status:123'])

    def test_live_overrun_cannot_be_disguised_as_source_limit(self):
        self.capture['items'] = []
        self.capture['surfaces'][0].update(identifiers=[str(i) for i in range(32)], more_available=True,
            retrieval_limit='Final profile batch rendered two extra cards.')
        result = runtime.collect_batch(self.state, self.contract, self.capture)['coverage'][0]
        self.assertEqual(result['stop_reason'], 'item_ceiling')
        self.assertEqual(result['remaining_items'], 0)
        self.assertIn('overrun', result['notices'][0])
        self.assertIn('by 2', result['notices'][0])

    def test_memory_file_matches_transfer_shape_and_refuses_error_text(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        bundle = memory.read_json(self.workspace / 'memory.json')
        self.assertEqual(bundle, runtime.prepared_memory(self.state))
        self.assertEqual(bundle['artifacts'][0]['version_id'], memory.decode(bundle['artifacts'][0]['content'])['version_id'])
        bundle['artifacts'][0]['content'] = 'Traceback (most recent call last): TypeError'
        memory_path = self.workspace / 'memory.json'
        memory_path.write_text(json.dumps(bundle))
        with self.assertRaisesRegex(ValueError, 'front matter'):
            runtime.prepared_memory(self.state)

    def test_remote_verification_checks_content_not_only_processing_status(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        artifact = runtime.prepared_memory(self.state)['artifacts'][0]
        request = {'account_key': artifact['account_key'], 'document': {
            'status': 'done', 'contentTruncated': False, 'content': 'Traceback: TypeError'}}
        self.assertEqual(runtime.verify_memory(self.state, request)['status'], 'failed')
        rendered = runtime.finish(self.state, self.contract, retain=True)['rendered']
        self.assertIn('not saved correctly', rendered)
        request['document']['status'] = 'queued'
        self.assertEqual(runtime.verify_memory(self.state, request)['status'], 'pending')
        request['document'].update(status='done', content=artifact['content'].rstrip())
        self.assertEqual(runtime.verify_memory(self.state, request)['status'], 'verified')
        saved = memory.decode(artifact['content'])
        saved['summary'] = 'Changed content'
        request['document']['content'] = memory.encode(saved)
        self.assertEqual(runtime.verify_memory(self.state, request)['status'], 'failed')

    def test_finish_reports_missing_remote_verification_without_agent_notice(self):
        contract, _ = self.remote([])
        runtime.collect_batch(self.state, contract, self.capture)
        result = runtime.finalize(self.state, contract, self.draft)
        self.assertNotIn('memory', result)  # Remote artifacts are transferred by the agent, never saved here.
        rendered = runtime.finish(self.state, contract)['rendered']
        self.assertIn('storage has not been verified', rendered)

    def test_capture_starts_and_switches_source_clocks_without_a_separate_call(self):
        second = copy.deepcopy(self.contract['coverage_threads'][0])
        second.update(id='source-2', service='other-source')
        self.contract['coverage_threads'].append(second)
        self.contract['run_limits'].update(elapsed_minutes=20, service_minutes={'example-source': 10, 'other-source': 10})
        self.contract['composition']['max_items_by_thread']['source-2'] = 5
        self.state['services'] = {}  # No explicit `service` call was made.
        self.state['service_minutes'] = self.contract['run_limits']['service_minutes']
        self.state['allowed_services'] = ['example-source', 'other-source']
        runtime.collect_batch(self.state, self.contract, self.capture)
        self.assertIn('open_since', self.state['services']['example-source'])
        other = {'account_key': 'other-source:account', 'items': [], 'surfaces': [
            {'thread_id': 'source-2', 'surface': 'items', 'identifiers': [], 'more_available': None}]}
        runtime.collect_batch(self.state, self.contract, other)
        self.assertNotIn('open_since', self.state['services']['example-source'])
        self.assertIn('open_since', self.state['services']['other-source'])
        mixed = copy.deepcopy(other)
        mixed['surfaces'].append(self.capture['surfaces'][0])
        with self.assertRaisesRegex(ValueError, 'one source service'):
            runtime.collect_batch(self.state, self.contract, mixed)
        window = runtime.observation_window(self.state, self.contract, {
            'account_key': self.capture['account_key'], 'thread_id': 'source-1', 'surface': 'items', 'max_items': 5})
        self.assertGreater(window['limit'], 0)
        self.assertIn('open_since', self.state['services']['example-source'])

    def test_finalize_seals_collection_and_saves_local_memory_once(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        result = runtime.finalize(self.state, self.contract, self.draft)  # No separate seal or memory call.
        self.assertEqual(self.state['phase'], 'finalizing')
        self.assertEqual(result['memory']['storage'], {'example-source:account': 'verified'})
        saved = Path(result['memory']['saved'][0])
        self.assertTrue(saved.is_file())
        with self.assertRaisesRegex(ValueError, 'sealed'):
            runtime.collect_batch(self.state, self.contract, self.capture)
        again = runtime.save_local_memory(self.state, self.contract, runtime.prepared_memory(self.state))
        self.assertEqual(again['saved'], [str(saved)])
        self.assertEqual(len(list(saved.parent.iterdir())), 1)
        self.assertNotIn('memory', runtime.finish(self.state, self.contract, retain=True)['rendered'].lower())

    def test_failed_local_save_still_delivers_the_briefing_with_a_continuity_notice(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        with patch.object(memory, 'save_local', side_effect=OSError('disk full')):
            result = runtime.finalize(self.state, self.contract, self.draft)
        self.assertEqual(result['memory'], {'saved': [], 'storage': {'example-source:account': 'failed'}})
        rendered = runtime.finish(self.state, self.contract, retain=True)['rendered']
        self.assertIn('A practical method', rendered)
        self.assertIn('could not be saved', rendered)
        self.assertNotIn('disk full', rendered)
        self.assertIn('disk full', self.state['storage']['example-source:account']['notice'])

    def test_transfer_rejects_changed_target_missing_account_or_valid_rewritten_record(self):
        runtime.collect_batch(self.state, self.contract, self.capture)
        budget.seal(self.state)
        runtime.finalize(self.state, self.contract, self.draft)
        bundle = runtime.prepared_memory(self.state)
        for mutation in ('target', 'account', 'body'):
            changed = copy.deepcopy(bundle)
            if mutation == 'target':
                changed['provider'] = 'supermemory'
                changed['space'] = 'another-space'
            elif mutation == 'account':
                changed['artifacts'] = []
            else:
                record = memory.decode(changed['artifacts'][0]['content'])
                record['summary'] = 'A valid but different summary.'
                changed['artifacts'][0]['content'] = memory.encode(record)
            (self.workspace / 'memory.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'changed after finalization'):
                runtime.prepared_memory(self.state)

    def test_cli_round_trip_stdin_state_and_cleanup(self):
        def cli(script, *args, data=None, good=True):
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args],
                input=json.dumps(data) if data is not None else None, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0 if good else 1, proc.stderr)
            return json.loads(proc.stdout if good else proc.stderr)
        # The whole local run: plan, start, capture, finalize, finish.
        plan = cli('runtime.py', 'plan', '--host', 'other', '--contract', str(self.path))
        self.assertEqual(plan['execution'], {'mode': 'sequential'})
        opened = cli('runtime.py', 'start', '--contract', str(self.path), '--expected-digest', plan['contract_digest'])
        run, workspace = opened['run_id'], Path(opened['workspace'])
        cli('runtime.py', 'capture', '--run', run, '--input', '-', data=self.capture)
        cli('runtime.py', 'finish', '--run', run, good=False)
        result = cli('runtime.py', 'finalize', '--run', run, '--input', '-', data=self.draft)
        self.assertEqual(len(result['memory']['saved']), 1)
        self.assertEqual(cli('runtime.py', 'memory', '--run', run)['saved'], result['memory']['saved'])
        done = cli('runtime.py', 'finish', '--run', run)
        self.assertEqual(done['entries'], 1)
        self.assertIn('A practical method', done['rendered'])
        self.assertNotIn('storage', done['rendered'])
        self.assertFalse(budget.state_path(run).exists())
        self.assertFalse(workspace.exists())

    def parallel_run(self, minutes=None):
        """A two-service contract that permits parallel collection, with its run started in parallel."""
        second = copy.deepcopy(self.contract['coverage_threads'][0])
        second.update(id='source-2', service='other-source')
        self.contract['coverage_threads'].append(second)
        self.contract['execution']['parallelism'] = {'mode': 'when_independent', 'max_workers': 2}
        self.contract['run_limits'].update(elapsed_minutes=20, service_minutes=minutes or {'example-source': 15, 'other-source': 15})
        self.contract['composition']['max_items_by_thread']['source-2'] = 5
        self.path.write_text(json.dumps(self.contract))
        opened = runtime.start(self.path, parallel=True)
        self.state = memory.read_json(budget.state_path(opened['run_id']))
        self.addCleanup(lambda: [f.unlink() for f in Path(opened['workspace']).glob('*')] and None)
        other = {'account_key': 'other-source:account', 'items': [
            {'ref': 'other-source-1', 'thread_id': 'source-2', 'surface': 'items', 'identifier': 'other:1',
             'basis': {'sender': 'Other', 'text': 'A second source item.'}}],
            'surfaces': [{'thread_id': 'source-2', 'surface': 'items', 'identifiers': ['other:1'],
                          'more_available': False, 'evidence': 'End marker observed.', 'exhaustion': {'kind': 'explicit_end_marker', 'evidence': 'End marker observed.'}}]}
        return opened, other

    def test_parallel_start_needs_the_contracts_permission(self):
        with self.assertRaisesRegex(ValueError, 'does not permit parallel'):
            runtime.start(self.path, parallel=True)

    def test_parallel_clocks_overlap_and_one_sources_ceiling_stops_only_its_collector(self):
        opened, other = self.parallel_run({'example-source': 1, 'other-source': 15})
        begun = budget.now()
        first = runtime.collect_batch(self.state, self.contract, self.capture, begun)
        second = runtime.collect_batch(self.state, self.contract, other, begun + timedelta(seconds=10))
        self.assertFalse(first['stop'] or second['stop'])
        self.assertTrue(all('open_since' in e for e in self.state['services'].values()))  # Side by side.
        late = begun + timedelta(seconds=90)  # The first source is past its one-minute allowance.
        self.assertTrue(runtime.collect_batch(self.state, self.contract, self.capture, late)['stop'])
        still = runtime.collect_batch(self.state, self.contract, other, late)
        self.assertFalse(still['stop'])
        self.assertFalse(still['budget']['stop'])
        self.assertEqual(still['budget']['stop_services'], ['example-source'])
        # Sealing long after a collector finished charges it only up to its last capture.
        budget.seal(self.state, begun + timedelta(seconds=600))
        used = {name: round(entry['used_seconds']) for name, entry in self.state['services'].items()}
        self.assertEqual(used, {'example-source': 90, 'other-source': 80})

    def test_each_source_keeps_its_own_window_in_a_parallel_run(self):
        opened, other = self.parallel_run()
        mine = runtime.observation_window(self.state, self.contract, {
            'account_key': self.capture['account_key'], 'thread_id': 'source-1', 'surface': 'items', 'max_items': 3})
        theirs = runtime.observation_window(self.state, self.contract, {
            'account_key': other['account_key'], 'thread_id': 'source-2', 'surface': 'items', 'max_items': 3})
        card = {'identifier': self.url, 'basis': self.basis}
        result = runtime.capture_window(self.state, self.contract, {'ticket': mine['ticket'], 'cards': [card], 'more_available': None})
        self.assertEqual(list(result['decisions'].values()), ['new'])
        self.assertEqual(list(self.state['observation_windows']), ['other-source'])
        with self.assertRaisesRegex(ValueError, 'stale'):
            runtime.capture_window(self.state, self.contract, {'ticket': mine['ticket'], 'cards': [], 'more_available': None})
        runtime.capture_window(self.state, self.contract, {'ticket': theirs['ticket'], 'cards': [], 'more_available': None})

    def test_collectors_capture_concurrently_into_one_run_and_the_coordinator_finalizes_once(self):
        opened, other = self.parallel_run()
        run = opened['run_id']

        def cli(*args, data=None):
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/runtime.py'), *args, '--run', run],
                input=json.dumps(data) if data is not None else None, capture_output=True, text=True)
            return proc.returncode, proc.stdout, proc.stderr

        def collector(batch, count):
            results = []
            for number in range(count):  # Repeated captures keep the lock busy from both sides.
                page = copy.deepcopy(batch)
                page['surfaces'][0]['identifiers'] = [batch['surfaces'][0]['identifiers'][0], batch['account_key'] + ':extra:' + str(number)]
                page['surfaces'][0]['more_available'] = None
                results.append(cli('capture', '--input', '-', data=page))
            results.append(cli('capture', '--input', '-', data=batch))
            return results

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [f.result() for f in [pool.submit(collector, self.capture, 6), pool.submit(collector, other, 6)]]
        for code, out, err in [r for outcome in outcomes for r in outcome]:
            self.assertEqual(code, 0, err)
        state = memory.read_json(budget.state_path(run))
        self.assertEqual(sorted(state['candidates']), ['one', 'other-source-1'])
        self.assertEqual({k: len(v['identifiers']) for k, v in state['surfaces'].items()},
                         {'source-1/items': 7, 'source-2/items': 7})
        second = copy.deepcopy(self.draft['entries'][0])
        second.update(id='entry-2', thread_id='source-2', account_key=other['account_key'], item_refs=['other-source-1'], url=None)
        draft = {**self.draft, 'entries': [self.draft['entries'][0], second]}
        code, out, err = cli('finalize', '--input', '-', data=draft)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)['memory']['storage'],
                         {'example-source:account': 'verified', 'other-source:account': 'verified'})
        code, out, err = cli('capture', '--input', '-', data=other)  # A late collector cannot add to a sealed run.
        self.assertEqual(code, 1)
        self.assertIn('sealed', err)
        done = json.loads(cli('finish')[1])
        self.assertEqual(done['entries'], 2)
        self.assertEqual({row['status'] for row in done['coverage']}, {'checked'})

    def test_an_interrupted_collector_keeps_its_captures_and_honest_coverage(self):
        opened, other = self.parallel_run()
        runtime.collect_batch(self.state, self.contract, self.capture)
        partial = copy.deepcopy(other)
        partial['items'] = []
        partial['surfaces'][0].update(more_available=True, evidence='First page only.')
        runtime.collect_batch(self.state, self.contract, partial)  # ...and then this collector dies.
        runtime.finalize(self.state, self.contract, self.draft)
        rows = {row['thread_id']: row for row in self.state['selection']['coverage']}
        self.assertEqual((rows['source-2']['status'], rows['source-2']['stop_reason']), ('partial', 'agent_stopped_early'))
        self.assertEqual(rows['source-1']['status'], 'checked')

    def test_lower_level_clock_commands_remain_available(self):
        def cli(*args):
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/run_budget.py'), *args], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        run = self.state['run_id']
        self.assertTrue(cli('service', '--run', run, '--service', 'example-source')['services']['example-source']['active'])
        self.assertFalse(cli('service-end', '--run', run, '--service', 'example-source')['services']['example-source']['active'])
        self.assertEqual(cli('seal', '--run', run)['phase'], 'finalizing')


if __name__ == '__main__':
    unittest.main()
