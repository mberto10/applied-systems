"""Focused deterministic fixtures; never read personal contracts or contact providers."""
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_run_replay as replay

runtime, budget, memory = replay.runtime, replay.budget, replay.memory
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_plan


class PlanWindowTests(unittest.TestCase):
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
        self.addCleanup(self.cleanup)
        budget.begin_service(self.state, 'example-source')
        self.request = {'account_key': 'example-source:account', 'thread_id': 'source-1', 'surface': 'items', 'max_items': 10}

    def cleanup(self):
        workspace = Path(self.state['workspace'])
        if workspace.exists():
            for file in workspace.iterdir():
                file.unlink()
            workspace.rmdir()

    def frame(self, window, numbers):
        return {'ticket': window['ticket'], 'cards': [{'identifier': f'x:post:{i}',
            'basis': {'sender': 'Author', 'text': f'Exact source text {i} 👀'}} for i in numbers], 'more_available': True}

    def test_plan_preserves_all_contract_rules_and_resolves_only_selected_guides(self):
        plan = run_plan.prepare(self.path, 'codex')
        self.assertEqual(plan['contract'], self.contract)
        self.assertEqual(plan['routes'][0]['provider'], 'codex_in_app')
        self.assertTrue(plan['routes'][0]['host_supported'])
        self.assertEqual(len(plan['read_once']), len(set(plan['read_once'])))
        self.assertTrue(all(Path(p).is_file() for p in plan['read_once']))
        self.assertFalse(any('supermemory.md' in p or 'claude.md' in p for p in plan['read_once']))
        self.assertEqual(plan['tools']['memory_names'], [])
        self.assertEqual([Path(p).name for p in plan['read_once']], ['codex.md'])
        self.assertNotIn('host_adapter', plan['helpers'])
        self.assertFalse(run_plan.prepare(self.path, 'other')['routes'][0]['host_supported'])

    def test_plan_offers_one_collector_per_service_only_when_the_contract_permits_it(self):
        contract = json.loads(self.path.read_text())
        self.assertEqual(run_plan.prepare(self.path, 'codex')['execution'], {'mode': 'sequential'})
        contract['execution']['parallelism'] = {'mode': 'when_independent', 'max_workers': 2}
        self.path.write_text(json.dumps(contract))
        self.assertEqual(run_plan.prepare(self.path, 'codex')['execution'], {'mode': 'sequential'})  # One service only.
        extra = copy.deepcopy(contract['coverage_threads'][0])
        extra.update(id='source-2', service='other-source')
        same = copy.deepcopy(contract['coverage_threads'][0])
        same.update(id='source-3')
        contract['coverage_threads'] += [extra, same]
        self.path.write_text(json.dumps(contract))
        execution = run_plan.prepare(self.path, 'claude')['execution']
        self.assertEqual((execution['mode'], execution['max_workers']), ('parallel_permitted', 2))
        self.assertEqual([(c['service'], c['thread_ids']) for c in execution['collectors']],
                         [('example-source', ['source-1', 'source-3']), ('other-source', ['source-2'])])
        guides = execution['collectors'][0]['guides']
        self.assertTrue(all(Path(g).is_file() for g in guides))
        self.assertTrue(guides[0].endswith('SKILL.md') and guides[-1].endswith('browsers/claude.md'))
        self.assertTrue(Path(execution['guide']).is_file())
        self.assertTrue(run_plan.prepare(self.path, 'codex')['execution']['collectors'][0]['guides'][-1].endswith('browsers/codex.md'))

    def test_remote_memory_keeps_its_exact_transfer_adapter(self):
        self.contract['memory_context'] = {'provider': 'supermemory', 'space': 'fixture',
            'purpose': 'avoid_repeating_previously_briefed_items', 'on_unavailable': 'continue_with_notice'}
        self.path.write_text(json.dumps(self.contract))
        plan = run_plan.prepare(self.path, 'codex')
        self.assertIn('host_adapter', plan['helpers'])
        self.assertEqual([Path(p).name for p in plan['read_once']], ['codex.md', 'codex-adapter.md'])
        self.assertNotIn('host_adapter', run_plan.prepare(self.path, 'claude')['helpers'])

    def test_plan_has_no_run_side_effects_and_digest_prevents_stale_start(self):
        before = set(Path(self.tmp.name).rglob('*'))
        plan = run_plan.prepare(self.path, 'codex')
        self.assertEqual(before, set(Path(self.tmp.name).rglob('*')))
        self.assertEqual(plan['contract_digest'], budget.digest(self.contract))
        with self.assertRaisesRegex(ValueError, 'startup plan'):
            runtime.start(self.path, expected_digest='outdated')

    def test_one_digest_serves_plan_start_and_contract_edits_with_non_ascii_text(self):
        contract = json.loads(self.path.read_text())
        contract['intent']['purpose'] = 'Nachrichten für die Woche – kurz und präzise.'
        self.path.write_text(json.dumps(contract, ensure_ascii=False))
        plan = run_plan.prepare(self.path, 'claude')
        self.assertEqual(plan['contract_digest'], runtime.contract_api.digest(contract))
        started = runtime.start(self.path, expected_digest=plan['contract_digest'])
        self.assertEqual(started['contract_path'], str(self.path.resolve()))

    def test_allowance_is_shared_across_profile_batches_and_skips_seen(self):
        for start in (0, 10, 20):
            window = runtime.observation_window(self.state, self.contract, self.request)
            count = 8 if start == 20 else 10
            result = runtime.capture_window(self.state, self.contract, self.frame(window, range(start, start + count)))
        self.assertEqual(result['coverage'][0]['inspected_count'], 28)
        window = runtime.observation_window(self.state, self.contract, self.request)
        self.assertEqual(window['limit'], 2)
        self.assertEqual(len(window['seen_identifiers']), 28)
        result = runtime.capture_window(self.state, self.contract, self.frame(window, (28, 29)))
        self.assertEqual(result['coverage'][0]['inspected_count'], 30)
        self.assertEqual(len(result['references']), 2)
        self.assertEqual(runtime.observation_window(self.state, self.contract, self.request)['limit'], 0)

    def test_stale_duplicate_and_oversize_frames_fail_without_state_change(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        newer = runtime.observation_window(self.state, self.contract, self.request)
        before = copy.deepcopy(self.state)
        for frame in (self.frame(window, (1,)), self.frame(newer, range(11)), self.frame(newer, (1, 1))):
            with self.assertRaises(ValueError):
                runtime.capture_window(self.state, self.contract, frame)
            self.assertEqual(self.state, before)
        runtime.capture_window(self.state, self.contract, self.frame(newer, (1,)))
        with self.assertRaisesRegex(ValueError, 'consumed'):
            runtime.capture_window(self.state, self.contract, self.frame(newer, (1,)))

    def test_loading_empty_is_not_exhaustion_and_counts_rejected_cards(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        result = runtime.capture_window(self.state, self.contract, {'ticket': window['ticket'], 'cards': [],
            'loading': True, 'more_available': False})
        self.assertEqual(result['coverage'][0]['action'], 'inspect_availability')
        window = runtime.observation_window(self.state, self.contract, self.request)
        result = runtime.capture_window(self.state, self.contract, self.frame(window, (1, 2, 3)))
        self.assertEqual(result['coverage'][0]['inspected_count'], 3)
        self.assertEqual(len(result['decisions']), 3)
        self.assertEqual(self.state['candidates'][result['references'][0]['ref']]['item']['change_fingerprint'],
                         memory.fingerprint({'sender': 'Author', 'text': 'Exact source text 1 👀'}))

    def test_window_obeys_time_and_optional_service_ceiling(self):
        self.state['service_minutes'] = {}
        self.assertEqual(runtime.observation_window(self.state, self.contract, self.request)['limit'], 10)
        later = budget.now() + timedelta(minutes=20)
        self.assertEqual(runtime.observation_window(self.state, self.contract, self.request, later)['limit'], 0)

    def test_import_is_exact_once_idempotent_and_account_neutral(self):
        self.contract['memory_context'] = {'provider': 'supermemory', 'space': 'fixture',
            'purpose': 'avoid_repeating_previously_briefed_items', 'on_unavailable': 'continue_with_notice'}
        payload = {'space': 'fixture', 'complete': False, 'documents': [
            {'id': 'one', 'status': 'done', 'contentTruncated': False, 'content': 'Exact original\n“quote” 👀'},
            {'id': 'two', 'status': 'failed', 'contentTruncated': True, 'content': None}]}
        runtime.import_history(self.state, self.contract, payload)
        path = Path(self.state['workspace']) / 'history.json'
        stamp = path.stat().st_mtime_ns
        self.assertEqual(json.loads(path.read_text()), payload)
        runtime.import_history(self.state, self.contract, payload)
        self.assertEqual(stamp, path.stat().st_mtime_ns)
        self.assertIn('incomplete', ' '.join(runtime.history(self.state, self.contract, 'example-source:account')['warnings']))
        for mutation in ({'space': 'wrong'}, {'complete': True}, {'documents': payload['documents'] * 2}):
            with self.assertRaises(ValueError):
                runtime.import_history(self.state, self.contract, {**payload, **mutation})

    def test_cli_plan_is_valid_json(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/run_plan.py'), '--host', 'codex', '--contract', str(self.path)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['contract']['id'], self.contract['id'])

    def test_partial_extraction_counts_known_identity_without_briefing_incomplete_basis(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        frame = self.frame(window, (1,))
        frame['cards'].append({'identifier': 'x:post:2'})
        frame['access_failure'] = 'Second card text missing during extraction.'
        result = runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(result['coverage'][0]['inspected_count'], 2)
        self.assertEqual(len(result['references']), 1)
        self.assertEqual(result['coverage'][0]['stop_reason'], 'access_failure')

    def test_rejected_cards_count_without_text_or_candidate_storage(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        frame = self.frame(window, (1, 2, 3))
        del frame['cards'][0]['basis']
        del frame['cards'][2]['basis']
        result = runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(result['coverage'][0]['inspected_count'], 3)
        self.assertEqual(result['decisions'], {'c1': 'new'})
        self.assertEqual(result['references'], [{'identifier': 'x:post:2', 'ref': 'c1'}])
        self.assertEqual(len(self.state['candidates']), 1)
        self.assertNotIn('Exact source text', json.dumps(self.state))

    def test_capture_renews_allowance_without_resending_scope_or_seen_ids(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        seen = []
        for start in (0, 10, 20):
            frame = self.frame(window, range(start, start + 10))
            result = runtime.capture_window(self.state, self.contract, {**frame, 'next_max_items': 10})
            if start < 20:
                following = result['next_window']
                self.assertEqual(set(following), {'ticket', 'limit', 'deadline_ms'})
                self.assertNotEqual(following['ticket'], window['ticket'])
                seen += [f'x-status:{i}' for i in range(start, start + 10)]
                window = {**window, **following, 'seen_identifiers': seen}
            else:
                self.assertIsNone(result['next_window'])
                self.assertEqual(result['coverage'][0]['action'], 'stop')
        self.assertEqual(len(self.state['candidates']), 30)
        self.assertEqual(len(set(self.state['candidates'])), 30)

    def test_renewal_is_atomic_and_never_reopens_exhausted_or_expired_collection(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        frame = {**self.frame(window, (1,)), 'next_max_items': 0}
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'positive'):
            runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(before, self.state)
        frame.update(next_max_items=10, more_available=False, evidence='Observed explicit end marker.', exhaustion={'kind': 'explicit_end_marker', 'evidence': 'Observed explicit end marker.'})
        result = runtime.capture_window(self.state, self.contract, frame)
        self.assertIsNone(result['next_window'])
        expired = copy.deepcopy(before)
        frame.update(more_available=True)
        result = runtime.capture_window(expired, self.contract, frame, budget.now() + timedelta(minutes=20))
        self.assertTrue(result['stop'])
        self.assertIsNone(result['next_window'])

    def test_unreadable_card_continues_but_partial_coverage_survives_later_exhaustion(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        frame = self.frame(window, (1,))
        frame['cards'].append({'identifier': 'x:post:2', 'read_error': 'A quoted card had ambiguous text.'})
        frame['next_max_items'] = 10
        result = runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(result['coverage'][0]['action'], 'load_more')
        frame = self.frame({**window, **result['next_window']}, (3,))
        frame.update(more_available=False, evidence='Observed explicit end marker.', exhaustion={'kind': 'explicit_end_marker', 'evidence': 'Observed explicit end marker.'})
        runtime.capture_window(self.state, self.contract, frame)
        row = runtime.selected_coverage(self.state, self.contract)[0]
        self.assertEqual((row['inspected_count'], row['status'], row['stop_reason']), (3, 'partial', 'source_limit'))
        self.assertIn('ambiguous text', row['evidence'])
        self.assertEqual(len(self.state['candidates']), 2)

    def test_read_error_cannot_also_supply_selectable_text(self):
        window = runtime.observation_window(self.state, self.contract, self.request)
        frame = self.frame(window, (1,))
        frame['cards'][0]['read_error'] = 'Unreadable'
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'cannot be a candidate'):
            runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(self.state, before)

    def test_observed_x_aliases_preserve_novelty_and_legacy_uncertainty_without_rewrite(self):
        old = {'service': 'x', 'identifier': 'x:post:123', **memory.fingerprint_metadata({'sender': 'A', 'text': 'Exact'})}
        history = {'records': [{'record': {'items': [old], 'created_at': '2026-09-18T00:00:00Z'}}], 'warnings': []}
        before = copy.deepcopy(history)
        url = {**old, 'identifier': 'https://twitter.com/A/status/123/analytics?s=20'}
        self.assertEqual(memory.compare(history, [url])['new_items'], [])
        self.assertEqual(memory.compare(history, [url])['already_briefed_count'], 1)
        changed = {**url, **memory.fingerprint_metadata({'incoming_id': 'different-basis'})}
        self.assertEqual(memory.compare(history, [changed])['uncertain_items'], [changed])
        self.assertEqual(before, history)


if __name__ == '__main__':
    unittest.main()
