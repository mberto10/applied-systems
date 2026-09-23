"""Source-independent access, migration, retrieval limits and selection continuity."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract_api, briefing, coverage, budget = (load(n) for n in
                                          ('contract', 'briefing', 'surface_coverage', 'run_budget'))
memory = contract_api.memory


def connector(thread):
    thread['access'] = {'type': 'connector', 'tool_namespace': 'fictional_mail',
                        'connection_id': 'connection-1', 'fallback': 'none'}
    thread.pop('entry_urls')
    thread['targets'] = {surface: {'scope': 'Incoming messages in the selected collection.'}
                         for surface in thread['surfaces']}
    thread['procedure'].pop('navigation')
    thread['procedure']['retrieval'] = 'Use the verified list and read operations for this collection.'
    return thread


def legacy(current):
    old = copy.deepcopy(current)
    old['schema_version'] = 'attention-diet-contract/1.2'
    old['browser_context'] = {'provider': 'codex_in_app'}
    for thread in old['coverage_threads']:
        thread['access'] = 'isolated_browser'
        thread['external_session_reuse'] = False
    return old


class SourceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / 'templates/attention-contract.json').read_text())
        self.record = json.loads((ROOT / 'examples/selection.json').read_text())
        self.observation = {'thread_id': 'source-1', 'surface': 'items',
                            'inspected_count': 10, 'more_available': True}
        self.budget = {'over': False, 'services': {'example-source':
                       {'active': True, 'over': False, 'remaining_seconds': 536}}}

    def test_connector_requires_only_its_own_access_and_scope(self):
        thread = connector(self.contract['coverage_threads'][0])
        contract_api.validate(self.contract)
        mutations = [lambda t: t['access'].pop('tool_namespace'),
                     lambda t: t['access'].update(tool_namespace='ambiguous namespace'),
                     lambda t: t['access'].update(provider='host_default'),
                     lambda t: t['access'].update(fallback='browser'),
                     lambda t: t['access'].update(token='not-a-configuration-field'),
                     lambda t: t.update(account_actions='send'),
                     lambda t: t.update(external_session_reuse=False),
                     lambda t: t.update(entry_urls={'items': 'https://example.org'}),
                     lambda t: t['targets'].clear(),
                     lambda t: t['targets'].update(other={'scope': 'Unconfigured collection'}),
                     lambda t: t['targets']['items'].update(scope=''),
                     lambda t: t['procedure'].pop('retrieval'),
                     lambda t: t['procedure'].update(navigation='Open a browser instead.')]
        for mutate in mutations:
            data = copy.deepcopy(self.contract)
            mutate(data['coverage_threads'][0])
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                contract_api.validate(data)
        thread['access'].pop('connection_id')
        contract_api.validate(self.contract)

    def test_browser_cannot_smuggle_connector_fields(self):
        for field, value in [('targets', {'items': {'scope': 'Inbox'}}),
                             ('access', {'type': 'connector', 'provider': 'codex_in_app', 'fallback': 'none'})]:
            data = copy.deepcopy(self.contract)
            data['coverage_threads'][0][field] = value
            with self.assertRaises(ValueError):
                contract_api.validate(data)
        self.contract['coverage_threads'][0]['procedure']['retrieval'] = 'Search mail'
        with self.assertRaises(ValueError):
            contract_api.validate(self.contract)

    def test_mixed_routes_share_service_budget_and_keep_unavailable_coverage(self):
        second = connector(copy.deepcopy(self.contract['coverage_threads'][0]))
        second['id'] = 'second-source'
        self.contract['coverage_threads'].append(second)
        contract_api.validate(self.contract)
        self.record['coverage'].append({'thread_id': 'second-source', 'surface': 'items',
            'status': 'unavailable', 'inspected_count': 0, 'more_available': None,
            'stop_reason': 'access_failure', 'evidence': 'Configured connector connection is unavailable.'})
        self.assertIn('unavailable', briefing.render(self.contract, self.record))
        at = datetime(2026, 9, 19, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_STATE_HOME': folder}):
            state = budget.start(self.contract, at)
            budget.begin_service(state, 'example-source', at)
            budget.begin_service(state, 'example-source', at + timedelta(seconds=64))
            report = budget.check(state, at + timedelta(seconds=100))
        self.assertEqual(report['services']['example-source']['used_seconds'], 100)

    def test_connector_pages_continue_until_a_real_limit(self):
        connector(self.contract['coverage_threads'][0])
        actions = [coverage.assess(self.contract, {**self.observation, 'inspected_count': n}, self.budget)
                   for n in (10, 10, 20, 30)]  # Empty intermediate page still has continuation.
        self.assertEqual([a['action'] for a in actions], ['load_more'] * 3 + ['stop'])
        self.assertEqual(actions[-1]['stop_reason'], 'item_ceiling')
        obs = {**self.observation, 'more_available': None}
        self.assertEqual(coverage.assess(self.contract, obs, self.budget)['action'], 'inspect_availability')

    def test_retrieval_limit_overrides_apparent_exhaustion_and_novelty(self):
        for available in (False, None, True):
            obs = {**self.observation, 'more_available': available,
                   'retrieval_limit': 'Ranked index returns at most ten matches.',
                   'novelty_boundary': {'ordering_verified': True, 'covered_range_verified': True,
                                        'evidence': 'Cannot override the retrieval limit.'}}
            result = coverage.assess(self.contract, obs, self.budget)
            self.assertEqual(result['stop_reason'], 'source_limit')
            row = self.record['coverage'][0]
            row.update({k: result[k] for k in ('inspected_count', 'more_available', 'stop_reason', 'evidence')})
            row['status'] = 'partial'
            self.assertIn('source access limited further checking', briefing.render(self.contract, self.record))
            self.assertNotIn('Ranked index returns', briefing.render(self.contract, self.record))
            self.assertIn('Ranked index returns', briefing.memory_payloads(self.contract, self.record)[0]['payload']['coverage'])
            row['status'] = 'checked'
            with self.assertRaisesRegex(ValueError, 'partial coverage'):
                briefing.validate(self.contract, self.record)
        for bad in ('', ' ', True, {}):
            with self.assertRaises(ValueError):
                coverage.assess(self.contract, {**self.observation, 'retrieval_limit': bad}, self.budget)

    def test_failure_and_measured_time_stop_connector_collection(self):
        connector(self.contract['coverage_threads'][0])
        result = coverage.assess(self.contract, {**self.observation, 'access_failure': 'Rate limit'}, self.budget)
        self.assertEqual(result['stop_reason'], 'access_failure')
        result = coverage.assess(self.contract, self.observation, {**self.budget, 'over': True})
        self.assertEqual(result['stop_reason'], 'time_ceiling')

    def test_no_link_keeps_attribution_and_included_only_memory(self):
        connector(self.contract['coverage_threads'][0])
        self.record['entries'][0]['url'] = None
        before = copy.deepcopy(self.record)
        for interface in ('agent_summary', 'briefing_html', 'discovery_html'):
            output = briefing.render(self.contract, self.record, interface)
            self.assertIn('No direct source link provided', output)
            self.assertIn('example', output)
            self.assertNotIn('https://example.org/items/1', output)
            self.assertNotIn('href="None"', output)
        groups = briefing.memory_payloads(self.contract, self.record)
        self.assertEqual(groups[0]['payload']['items'], self.record['entries'][0]['items'])
        self.assertEqual(self.record, before)
        self.record['entries'] = []
        self.assertEqual(briefing.memory_payloads(self.contract, self.record), [])

    def test_route_change_preserves_output_memory_and_repeat_detection(self):
        first = briefing.memory_payloads(self.contract, self.record)
        rendered = briefing.render(self.contract, self.record)
        connector(self.contract['coverage_threads'][0])
        self.assertEqual(briefing.memory_payloads(self.contract, self.record), first)
        self.assertEqual(briefing.render(self.contract, self.record), rendered)
        old = {'service': 'example-source', 'identifier': 'conversation-1',
               **memory.fingerprint_metadata({'sender': 'A', 'text': 'Earlier preview'})}
        history = {'records': [{'record': {'items': [old], 'created_at': '2026-09-18T00:00:00Z'}}], 'warnings': []}
        self.assertEqual(memory.compare(history, [old])['new_items'], [])
        richer = {'service': old['service'], 'identifier': old['identifier'],
                  **memory.fingerprint_metadata({'incoming_id': 'event-1'})}
        comparison = memory.compare(history, [richer])
        self.assertEqual(comparison['new_items'], [])
        self.assertEqual(comparison['uncertain_items'], [richer])
        later = {**richer, 'source_timestamp': '2026-09-19T00:00:00Z'}
        self.assertEqual(memory.compare(history, [later])['new_items'], [later])

if __name__ == '__main__':
    unittest.main()
