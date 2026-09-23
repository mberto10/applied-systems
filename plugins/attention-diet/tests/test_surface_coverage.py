"""A generic source runs through contract, budget, coverage and memory without an adapter."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load('contract')
coverage = load('surface_coverage')
budget = load('run_budget')


class GenericSourceTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'templates/attention-contract.json').read_text())
        self.data['coverage_threads'][0]['collection']['items'] = {'mode': 'sample', 'max_items': 20}
        self.obs = {'thread_id': 'source-1', 'surface': 'items',
                    'inspected_count': 10, 'more_available': True}
        self.report = {'contract_id': self.data['id'], 'over': False,
                       'services': {'example-source': {'active': True, 'over': False}}}

    def test_generic_source_end_to_end_without_service_code(self):
        data = contract.validate(self.data)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_STATE_HOME': folder}):
            data['memory_context']['directory'] = folder + '/history'
            now = datetime(2026, 9, 18, tzinfo=timezone.utc)
            state = budget.start(data, at=now)
            budget.begin_service(state, 'example-source', at=now)
            report = budget.check(state, at=now + timedelta(seconds=64))
            self.assertEqual(report['contract_id'], data['id'])
            self.assertEqual(coverage.assess(data, self.obs, report)['action'], 'load_more')
            result = coverage.assess(data, {**self.obs, 'inspected_count': 20}, report)
            self.assertEqual(result['stop_reason'], 'sample_ceiling')
            memory = contract.memory
            item = {'service': 'example-source', 'identifier': 'https://community.example.org/t/42',
                    **memory.fingerprint_metadata({'sender': 'writer', 'text': 'A useful method.'})}
            history = memory.load_history(data, 'example-source:member')
            self.assertEqual(memory.compare(history, [item])['new_items'], [item])
            record = memory.build_record(data, 'example-source:member', {'version_id': 'v1', 'items': [item],
                'summary': 'A useful method.', 'coverage': result['coverage_note']}, history)
            memory.save_local(data, record)
            self.assertEqual(memory.compare(memory.load_history(data, 'example-source:member'), [item])['new_items'], [])

    def test_scan_does_not_inherit_an_arbitrary_sample_stop(self):
        self.data['coverage_threads'][0].pop('collection')
        self.assertEqual(coverage.assess(self.data, {**self.obs, 'inspected_count': 20}, self.report)['action'], 'load_more')
        self.assertEqual(coverage.assess(self.data, {**self.obs, 'inspected_count': 30}, self.report)['stop_reason'], 'item_ceiling')

    def test_global_ceiling_and_time_take_precedence_over_larger_sample(self):
        self.data['coverage_threads'][0]['collection']['items']['max_items'] = 50
        self.assertEqual(coverage.assess(self.data, {**self.obs, 'inspected_count': 30}, self.report)['stop_reason'], 'item_ceiling')
        self.assertEqual(coverage.assess(self.data, self.obs, {**self.report, 'over': True})['stop_reason'], 'time_ceiling')

    def test_thread_scope_and_budget_are_not_guessed(self):
        for change in ({'thread_id': 'missing'}, {'surface': 'messages'}):
            with self.assertRaises(ValueError):
                coverage.assess(self.data, {**self.obs, **change}, self.report)
        with self.assertRaises(ValueError):
            coverage.assess(self.data, self.obs, {**self.report, 'contract_id': 'other'})
        second = copy.deepcopy(self.data['coverage_threads'][0])
        second.update(id='community-scan', collection={})
        self.data['coverage_threads'].append(second)
        result = coverage.assess(self.data, {**self.obs, 'thread_id': 'community-scan', 'inspected_count': 20}, self.report)
        self.assertEqual(result['action'], 'load_more')

    def test_custom_contract_rejects_incomplete_procedure_scope_and_ceiling(self):
        mutations = [
            lambda t: t['procedure'].pop('read_state'),
            lambda t: t['entry_urls'].clear(),
            lambda t: t['collection'].update(unconfigured={'mode': 'scan'}),
            lambda t: t['collection']['items'].pop('max_items'),
            lambda t: t['collection']['items'].update(max_items=True),
            lambda t: t.update(account_actions='reply'),
            lambda t: t.update(external_session_reuse=True),
        ]
        for mutate in mutations:
            data = copy.deepcopy(self.data)
            mutate(data['coverage_threads'][0])
            with self.assertRaises(ValueError):
                contract.validate(data)
        self.data['composition']['max_items_by_thread'] = {'missing': 3}
        with self.assertRaises(ValueError):
            contract.validate(self.data)

    def test_old_or_source_specific_contracts_require_migration(self):
        data = copy.deepcopy(self.data)
        data['schema_version'] = 'attention-diet-contract/1.0'
        with self.assertRaisesRegex(ValueError, 'schema_version'):
            contract.validate(data)
        data = copy.deepcopy(self.data)
        data['composition']['vendor_max_items'] = 5
        with self.assertRaisesRegex(ValueError, 'composition.*Additional properties'):
            contract.validate(data)
        data = copy.deepcopy(self.data)
        data['coverage_threads'][0].pop('procedure')
        with self.assertRaisesRegex(ValueError, 'procedure.*required'):
            contract.validate(data)



if __name__ == '__main__':
    unittest.main()
