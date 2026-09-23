"""Capture drift must not turn a known post into a new source event."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_run_replay as replay

memory, runtime = replay.memory, replay.runtime


class NoveltyRegressionTests(unittest.TestCase):
    def item(self, basis, identifier='post-1'):
        return {'service': 'public-source', 'identifier': identifier,
                **memory.fingerprint_metadata(basis)}

    def history(self, old):
        return {'records': [
            {'record': {'items': [old], 'created_at': '2026-09-19T15:09:11Z'}},
            {'record': {'items': [], 'created_at': '2026-09-20T15:00:00Z'}},
        ], 'warnings': []}

    def test_recorded_september_19_and_21_hashes_are_not_new(self):
        old = {'service': 'x', 'identifier': 'x:post:2101039819870937247',
               'fingerprint_method': 'sender-text/v1',
               'change_fingerprint': 'sha256:aecda57fc1fb5e2ba3e72fae765af7a97de05afa10f1d7a8498f9b56a5215d30'}
        current = {**old, 'change_fingerprint': 'sha256:1cdaf6a7ce734b44929fb6fcba505086a0a4d324cb7b97a6d903ceddf011ac7b'}
        history = self.history(old)
        before = copy.deepcopy(history)
        result = memory.compare(history, [current])
        self.assertEqual(result['new_items'], [])
        self.assertEqual(result['uncertain_items'], [current])
        self.assertEqual(result['continuity'], 'limited')
        self.assertEqual(history, before)

    def test_same_method_sender_components_and_preview_drift_are_uncertain(self):
        old = self.item({'sender': '@Example', 'text': 'An announcement. Link title.'})
        for basis in [
            {'sender': 'Example (@Example)', 'text': 'An announcement. Link title.'},
            {'sender': '@Example', 'text': 'An announcement.'},
            {'sender': '@Example', 'text': 'An announcement. Link title. Expanded details.'},
        ]:
            with self.subTest(basis=basis):
                current = self.item(basis)
                result = memory.compare(self.history(old), [current])
                self.assertEqual(result['new_items'], [])
                self.assertEqual(result['uncertain_items'], [current])

    def test_exact_legacy_aliases_suppress_but_unseen_posts_qualify(self):
        old = self.item({'sender': '@Example', 'text': 'An announcement.'}, 'x:post:123')
        old.pop('fingerprint_method')
        for identifier in ['x:post:123', 'https://twitter.com/Example/status/123/analytics?s=20']:
            current = self.item({'sender': ' @Example ', 'text': 'An\nannouncement.'}, identifier)
            result = memory.compare(self.history(old), [current], public_posts=True)
            self.assertEqual(result['already_briefed_count'], 1)
            self.assertEqual(result['new_items'], [])
        unseen = self.item({'sender': '@Example', 'text': 'An announcement.'}, 'x:post:456')
        self.assertEqual(memory.compare(self.history(old), [unseen], public_posts=True)['new_items'], [unseen])

    def test_public_post_cannot_use_message_id_or_later_time_as_edit_evidence(self):
        for old_basis, current_basis in [
            ({'incoming_id': 'm1'}, {'incoming_id': 'm2'}),
            ({'sender': '@Example', 'text': 'Preview'},
             {'sender': '@Example', 'text': 'Expanded', 'occurred_at': '2026-09-21T12:00:00Z'}),
        ]:
            old, current = self.item(old_basis), self.item(current_basis)
            with self.subTest(basis=current_basis):
                result = memory.compare(self.history(old), [current], public_posts=True)
                self.assertEqual(result['new_items'], [])
                self.assertEqual(result['uncertain_items'], [current])
                # The same evidence still denotes an incoming event in a private conversation.
                self.assertEqual(memory.compare(self.history(old), [current])['new_items'], [current])


class RuntimeNoveltyRegressionTests(unittest.TestCase):
    # Reuse the isolated fixture, without inheriting and rerunning its test suite.
    setUp = replay.ReplayTests.setUp
    clean_workspace = replay.ReplayTests.clean_workspace

    def save_old(self, basis):
        old = {'service': 'example-source', 'identifier': self.url, **memory.fingerprint_metadata(basis)}
        record = memory.build_record(self.contract, 'example-source:account', {
            'version_id': 'old-post', 'items': [old], 'coverage': 'partial', 'summary': 'Previously briefed.'},
            {'records': [], 'warnings': []})
        memory.save_local(self.contract, record)
        return old

    def test_window_drift_cannot_be_finalized_but_unseen_item_can(self):
        self.contract['coverage_threads'][0]['content'] = 'public_posts'
        self.save_old(self.basis)
        window = runtime.observation_window(self.state, self.contract, {
            'account_key': 'example-source:account', 'thread_id': 'source-1', 'surface': 'items', 'max_items': 2})
        drift = {**self.basis, 'sender': 'Example (@Example)'}
        result = runtime.capture_window(self.state, self.contract, {'ticket': window['ticket'], 'cards': [
            {'identifier': self.url, 'basis': drift},
            {'identifier': 'https://x.com/Example/status/456', 'basis': self.basis},
        ], 'more_available': False, 'evidence': 'Explicit end marker.'})
        self.assertEqual(result['decisions'], {'c1': 'uncertain', 'c2': 'new'})
        draft = copy.deepcopy(self.draft)
        draft['entries'][0]['item_refs'] = ['c1']
        with self.assertRaisesRegex(ValueError, 'Only compared new items'):
            runtime.finalize(copy.deepcopy(self.state), self.contract, draft)
        draft['entries'][0].update(item_refs=['c2'], url='https://x.com/Example/status/456')
        runtime.finalize(self.state, self.contract, draft)
        saved = memory.load_history(self.contract, 'example-source:account')
        self.assertEqual(len(saved['records']), 2)
        self.assertEqual(saved['records'][-1]['record']['items'][0]['identifier'], 'https://x.com/Example/status/456')

    def test_public_and_private_threads_in_same_service_keep_distinct_event_rules(self):
        self.save_old({'incoming_id': 'm1'})
        public = copy.deepcopy(self.contract['coverage_threads'][0])
        public.update(id='public', content='public_posts')
        self.contract['coverage_threads'].append(public)
        batch = copy.deepcopy(self.capture)
        batch['items'][0]['basis'] = {'incoming_id': 'm2'}
        batch['items'].append({**batch['items'][0], 'thread_id': 'public', 'ref': 'public'})
        batch['surfaces'].append({**batch['surfaces'][0], 'thread_id': 'public'})
        result = runtime.collect_batch(self.state, self.contract, batch)
        self.assertEqual(result['decisions'], {'one': 'new', 'public': 'uncertain'})

    def test_diagnostic_cli_applies_contract_public_post_policy(self):
        self.contract['coverage_threads'][0]['content'] = 'public_posts'
        self.path.write_text(json.dumps(self.contract))
        self.save_old({'incoming_id': 'm1'})
        current = {'service': 'example-source', 'identifier': self.url,
                   **memory.fingerprint_metadata({'incoming_id': 'm2'})}
        result = subprocess.run([sys.executable, str(Path(runtime.__file__).with_name('briefing_memory.py')),
            'compare', '--contract', str(self.path), '--account', 'example-source:account', '--input', '-'],
            input=json.dumps([current]), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['uncertain_items'], [current])


if __name__ == '__main__':
    unittest.main()
