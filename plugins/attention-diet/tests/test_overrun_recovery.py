"""Recovery and coverage regressions from the September 21 run; fictional data only."""
import copy
from datetime import timedelta
import json
import subprocess
import sys
from pathlib import Path
import unittest

import test_run_plan_windows as windows

runtime, budget = windows.runtime, windows.budget


class RecoveryTests(unittest.TestCase):
    setUp = windows.PlanWindowTests.setUp
    cleanup = windows.PlanWindowTests.cleanup
    frame = windows.PlanWindowTests.frame

    def checkpoint(self, ids):
        ticket = runtime.observation_window(self.state, self.contract, self.request)
        return runtime.capture_window(self.state, self.contract, self.frame(ticket, ids))

    def recovery(self, previous=26, maximum=10):
        for start in range(0, previous, 10):
            self.checkpoint(range(start, min(previous, start + 10)))
        ticket = runtime.observation_window(self.state, self.contract, self.request | {'max_items': maximum})
        frame = self.frame(ticket, range(previous, previous + ticket['limit'] + 3))
        frame['overrun'] = {'cause': 'unbounded_observation', 'evidence': 'The tool returned three extra previews.'}
        frame['next_max_items'] = 10
        return ticket, frame

    def test_26_plus_seven_records_33_but_only_four_candidates_and_stops(self):
        ticket, frame = self.recovery()
        self.assertEqual(ticket['limit'], 4)
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'retain every card'):
            runtime.capture_window(self.state, self.contract, {k: v for k, v in frame.items() if k != 'overrun'})
        self.assertEqual(self.state, before)
        result = runtime.capture_window(self.state, self.contract, frame)
        row = result['coverage'][0]
        self.assertEqual((row['inspected_count'], row['within_allowance_count'], row['overrun_count']), (33, 30, 3))
        self.assertEqual(row['stop_reason'], 'item_ceiling')
        self.assertEqual(row['action'], 'stop')
        self.assertEqual(len(result['references']), 4)
        self.assertIsNone(result['next_window'])
        self.assertEqual(len(self.state['candidates']), 30)
        self.assertNotIn('Exact source text 32', json.dumps(self.state))
        self.assertEqual(runtime.observation_window(self.state, self.contract, self.request)['limit'], 0)

    def test_recovery_below_surface_ceiling_stops_without_claiming_surface_overrun(self):
        _, frame = self.recovery(previous=0, maximum=4)
        result = runtime.capture_window(self.state, self.contract, frame)
        row = result['coverage'][0]
        self.assertEqual((row['inspected_count'], row['within_allowance_count'], row['overrun_count']), (7, 4, 3))
        self.assertEqual(row['stop_reason'], 'window_overrun')
        self.assertFalse(row['notices'])
        self.assertEqual(runtime.observation_window(self.state, self.contract, self.request)['limit'], 0)

    def test_recovery_retry_is_idempotent_and_changed_retry_is_atomic(self):
        _, frame = self.recovery()
        first = runtime.capture_window(self.state, self.contract, frame)
        before = copy.deepcopy(self.state)
        self.assertEqual(runtime.capture_window(self.state, self.contract, frame), first)
        self.assertEqual(self.state, before)
        altered = copy.deepcopy(frame)
        altered['cards'][0]['basis']['text'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'different payload'):
            runtime.capture_window(self.state, self.contract, altered)
        self.assertEqual(self.state, before)
        budget.seal(self.state)
        with self.assertRaisesRegex(ValueError, 'sealed'):
            runtime.capture_window(self.state, self.contract, frame)

    def test_bad_recovery_metadata_duplicate_alias_and_late_bad_card_leave_state_unchanged(self):
        _, frame = self.recovery()
        variants = []
        for overrun in ({}, {'cause': 'atomic_tool_response', 'evidence': ''}, False):
            variants.append(frame | {'overrun': overrun})
        duplicate = copy.deepcopy(frame)
        duplicate['cards'][-1]['identifier'] = 'https://twitter.com/A/status/26'
        variants.append(duplicate)
        bad = copy.deepcopy(frame)
        bad['cards'][-1] = {'identifier': '', 'read_error': 'Missing identity'}
        variants.append(bad)
        before = copy.deepcopy(self.state)
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises((ValueError, TypeError)):
                runtime.capture_window(self.state, self.contract, variant)
            self.assertEqual(self.state, before)

    def test_late_transfer_keeps_true_count_and_time_stop(self):
        _, frame = self.recovery()
        result = runtime.capture_window(self.state, self.contract, frame, budget.now() + timedelta(minutes=20))
        self.assertEqual(result['coverage'][0]['inspected_count'], 33)
        self.assertEqual(result['coverage'][0]['stop_reason'], 'time_ceiling')
        self.assertIsNone(result['next_window'])

    def test_direct_capture_cannot_bypass_ticket_and_overflow_never_becomes_candidate(self):
        _, frame = self.recovery()
        direct = {'account_key': self.request['account_key'], 'items': [], 'surfaces': [{
            'thread_id': 'source-1', 'surface': 'items', 'identifiers': [c['identifier'] for c in frame['cards']],
            'more_available': True}]}
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'outstanding ticket'):
            runtime.collect_batch(self.state, self.contract, direct)
        self.assertEqual(self.state, before)
        runtime.capture_window(self.state, self.contract, frame)
        direct['items'] = [{'ref': 'overflow', 'thread_id': 'source-1', 'surface': 'items',
                            **frame['cards'][-1]}]
        result = runtime.collect_batch(self.state, self.contract, direct)
        self.assertFalse(result['decisions'])
        self.assertNotIn('overflow', self.state['candidates'])
        self.assertEqual(result['coverage'][0]['overrun_count'], 3)

    def test_direct_overrun_is_counted_and_candidates_are_bounded(self):
        self.checkpoint(range(10))
        self.checkpoint(range(10,20))
        self.checkpoint(range(20,26))
        cards = [{'identifier': f'x:post:{i}', 'basis': {'sender': 'A', 'text': f'Post {i}'}} for i in range(26,33)]
        result = runtime.collect_batch(self.state, self.contract, {
            'account_key': self.request['account_key'],
            'items': [{'ref': f'd{i}', 'thread_id': 'source-1', 'surface': 'items', **c} for i,c in enumerate(cards)],
            'surfaces': [{'thread_id': 'source-1', 'surface': 'items', 'identifiers': [c['identifier'] for c in cards],
                          'more_available': True, 'retrieval_limit': 'A tool batch is not a source cap.'}]})
        self.assertEqual(len(result['decisions']), 4)
        self.assertEqual(result['coverage'][0]['overrun_count'], 3)
        self.assertEqual(result['coverage'][0]['stop_reason'], 'item_ceiling')

    def test_overflow_does_not_enter_memory_and_schema_12_round_trips(self):
        _, frame = self.recovery()
        result = runtime.capture_window(self.state, self.contract, frame)
        entry = {'item_refs': [result['references'][0]['ref']], 'title': 'Useful item', 'summary': 'Observed claim.',
                 'why': 'Relevant method.', 'url': None}
        runtime.finalize(self.state, self.contract, {'title': 'Test', 'overview': 'A bounded check.', 'entries': [entry]})
        record = self.state['selection']
        self.assertEqual(record['schema_version'], 'attention-selection/1.2')
        runtime.briefing.validate(self.contract, record)
        saved = runtime.memory.read_json(Path(self.state['workspace']) / 'memory.json')
        memory = runtime.memory.decode(saved['artifacts'][0]['content'])
        self.assertEqual(len(memory['items']), 1)
        self.assertEqual(memory['items'][0]['identifier'], 'x:post:26')
        output = Path(self.state['output_path']).read_text()
        self.assertIn('30 items within the limit, 3 extra observed', output)
        self.assertNotIn('Collection exceeded a configured inspection limit', output)
        for mutate in (lambda r: r['coverage'][0].update(within_allowance_count=33),
                       lambda r: r.update(schema_version='attention-selection/1.1')):
            wrong = copy.deepcopy(record); mutate(wrong)
            with self.assertRaises(ValueError):
                runtime.briefing.validate(self.contract, wrong)

    def test_missing_controls_do_not_establish_exhaustion(self):
        ticket = runtime.observation_window(self.state, self.contract, self.request)
        frame = self.frame(ticket, (1,2))
        frame.update(more_available=False, evidence='Two cards visible; no load-more control.')
        result = runtime.capture_window(self.state, self.contract, frame)
        self.assertIsNone(result['coverage'][0]['more_available'])
        self.assertEqual(result['coverage'][0]['action'], 'inspect_availability')
        self.assertEqual(runtime.selected_coverage(self.state, self.contract)[0]['status'], 'partial')

    def test_structured_exhaustion_and_matched_total(self):
        ticket = runtime.observation_window(self.state, self.contract, self.request)
        frame = self.frame(ticket, (1,2))
        frame.update(more_available=False, evidence='Authoritative total shown.',
                     exhaustion={'kind': 'authoritative_total_matched', 'total': 3, 'evidence': 'Total 3'})
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'total must match'):
            runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(self.state, before)
        frame['exhaustion'].update(total=2, evidence='Total 2')
        runtime.capture_window(self.state, self.contract, frame)
        self.assertEqual(runtime.selected_coverage(self.state, self.contract)[0]['status'], 'checked')

    def test_exact_ceiling_retains_exhaustive_boundary_and_unreadable_content(self):
        self.contract['run_limits']['items_per_surface'] = 2
        ticket = runtime.observation_window(self.state, self.contract, self.request)
        frame = {'ticket': ticket['ticket'], 'cards': [
            {'identifier': 'one', 'read_error': 'Only an attachment placeholder.'},
            {'identifier': 'two', 'read_error': 'Only an attachment placeholder.'}],
            'more_available': False, 'evidence': 'End marker.',
            'exhaustion': {'kind': 'explicit_end_marker', 'evidence': 'End marker.'}}
        runtime.capture_window(self.state, self.contract, frame)
        row = runtime.selected_coverage(self.state, self.contract)[0]
        self.assertEqual((row['stop_reason'], row['boundary'], row['unreadable_count']), ('item_ceiling', 'exhausted_results', 2))
        self.assertTrue(row['has_unreadable_content'])
        self.assertEqual(row['status'], 'partial')

    def test_sample_and_retrieval_stall_are_distinct_from_failure(self):
        self.contract['coverage_threads'][0]['collection']['items'] = {'mode': 'sample', 'max_items': 30}
        self.checkpoint(range(10)); self.checkpoint(range(10,20)); self.checkpoint(range(20,25))
        ticket = runtime.observation_window(self.state, self.contract, self.request)
        result = runtime.capture_window(self.state, self.contract, {'ticket': ticket['ticket'], 'cards': [],
            'more_available': None, 'retrieval_stalled': 'Two settled scroll attempts produced no unseen identities.'})
        self.assertEqual(result['coverage'][0]['stop_reason'], 'retrieval_stalled')
        row = runtime.selected_coverage(self.state, self.contract)[0]
        description = runtime.briefing.coverage_description(self.contract['coverage_threads'][0], row)
        self.assertIn('25 items sampled', description)
        self.assertIn('no new distinct items', description)
        self.assertNotIn('failed', description)

    def test_cli_recovery_receipt_survives_process_restart(self):
        _, frame = self.recovery(previous=0, maximum=4)
        budget.write(budget.state_path(self.state['run_id']), self.state)
        command = [sys.executable, str(windows.ROOT / 'scripts/runtime.py'), 'capture-window',
                   '--run', self.state['run_id'], '--input', '-']
        responses = []
        for _ in range(2):
            proc = subprocess.run(command, input=json.dumps(frame), text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses.append(json.loads(proc.stdout))
        self.assertEqual(responses[0], responses[1])
        persisted = runtime.memory.read_json(budget.state_path(self.state['run_id']))
        self.assertEqual(persisted['surfaces']['source-1/items']['inspected_count'], 7)
        self.assertEqual(len(persisted['candidates']), 4)
        self.assertFalse(persisted['observation_windows'])
        self.assertNotIn('Exact source text 6', json.dumps(persisted))

    def test_six_surface_briefing_explains_samples_caps_stalls_and_uncertain_end(self):
        thread = self.contract['coverage_threads'][0]
        second = copy.deepcopy(thread)
        thread.update(service='linkedin', surfaces=['messages', 'requests', 'notifications'],
                      content='private_communication', collection={})
        thread['entry_urls'] = {s: 'https://example.org/' + s for s in thread['surfaces']}
        second.update(id='source-2', service='x', surfaces=['official', 'creators', 'discovery'], content='public_posts')
        second['entry_urls'] = {s: 'https://example.org/' + s for s in second['surfaces']}
        second['collection'] = {s: {'mode': 'sample', 'max_items': 30} for s in second['surfaces']}
        self.contract['coverage_threads'] = [thread, second]
        self.contract['run_limits']['service_minutes'] = {'linkedin': 5, 'x': 5}
        rows = []
        for t, surface, count, reason in [
            (thread, 'messages', 33, 'item_ceiling'), (thread, 'requests', 2, 'exhausted_results'),
            (thread, 'notifications', 2, 'agent_stopped_early'), (second, 'official', 30, 'sample_ceiling'),
            (second, 'creators', 25, 'retrieval_stalled'), (second, 'discovery', 30, 'sample_ceiling')]:
            row = {'thread_id': t['id'], 'surface': surface, 'inspected_count': count,
                   'status': 'checked' if surface == 'requests' else 'partial', 'stop_reason': reason,
                   'evidence': 'Fixture observation.', 'more_available': False if surface == 'requests' else None,
                   'boundary': 'exhausted_results' if surface == 'requests' else 'unknown',
                   'exhaustion': {'kind': 'authoritative_total_matched', 'total': 2, 'evidence': 'PRIVATE_END_PROOF'}
                       if surface == 'requests' else None,
                   'overrun_count': 3 if surface == 'messages' else 0,
                   'within_allowance_count': 30 if surface == 'messages' else count,
                   'unreadable_count': 2 if surface == 'messages' else 0,
                   'has_unreadable_content': surface == 'messages'}
            rows.append(row)
        record = {'schema_version': 'attention-selection/1.2', 'contract_id': self.contract['id'],
                  'contract_revision': self.contract['revision'], 'run_id': self.state['run_id'],
                  'created_at': budget.now().isoformat(), 'title': 'Useful scan', 'overview': 'Selected scope checked.',
                  'entries': [], 'notices': [], 'coverage': rows}
        for interface in ('agent_summary', 'briefing_html', 'discovery_html'):
            output = runtime.briefing.render(self.contract, record, interface)
            for expected in ('6 of 6 source areas visited', '30 previews within the limit',
                             '3 extra observed', 'end of the list not verified', '30 posts sampled',
                             '25 posts sampled', 'no new distinct items', 'end of the list verified',
                             'some previews lacked enough content'):
                self.assertIn(expected, output)
            self.assertNotIn('PRIVATE_END_PROOF', output)
            self.assertNotIn('Coverage was partial', output)
            self.assertNotIn('checked in full', output)
        malformed = copy.deepcopy(record)
        malformed['coverage'][1]['exhaustion'] = None
        with self.assertRaisesRegex(ValueError, 'structured exhaustion'):
            runtime.briefing.validate(self.contract, malformed)


if __name__ == '__main__':
    unittest.main()
