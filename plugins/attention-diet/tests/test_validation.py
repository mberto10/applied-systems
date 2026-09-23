"""Integration boundaries for schema authority, dependencies and CLI validation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
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


contract = load('contract')
briefing = load('briefing')
memory = load('briefing_memory')


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / 'templates/attention-contract.json').read_text())
        self.selection = json.loads((ROOT / 'examples/selection.json').read_text())
        self.record = json.loads((ROOT / 'integrations/memory/example-record.json').read_text())

    def test_schema_changes_reach_all_runtime_validators(self):
        cases = [
            (contract.memory.schema_validation, 'attention-contract.schema.json', 'id', self.contract,
             contract.validate),
            (briefing.contract_api.memory.schema_validation, 'selection.schema.json', 'title', self.selection,
             lambda data: briefing.validate(self.contract, data)),
            (memory.schema_validation, 'memory-record.schema.json', 'summary', self.record, memory.validate_record),
        ]
        for helper, filename, field, data, validate in cases:
            with self.subTest(schema=filename), tempfile.TemporaryDirectory() as folder:
                validate(data)
                schemas = Path(folder) / 'schemas'
                shutil.copytree(ROOT / 'schemas', schemas)
                path = schemas / filename
                schema = json.loads(path.read_text())
                schema['properties'][field] = {'type': 'string', 'maxLength': 1}
                path.write_text(json.dumps(schema))
                helper.registry.cache_clear()
                helper.validator.cache_clear()
                try:
                    with patch.object(helper, 'SCHEMAS', schemas):
                        with self.assertRaisesRegex(ValueError, field):
                            validate(data)
                finally:
                    helper.registry.cache_clear()
                    helper.validator.cache_clear()

    def test_datetime_formats_are_checked_in_selection_and_memory(self):
        for bad in ('yesterday', '2026-09-19T10:00:00', '2026-02-30T10:00:00Z'):
            selected = copy.deepcopy(self.selection)
            selected['created_at'] = bad
            with self.assertRaisesRegex(ValueError, 'created_at'):
                briefing.validate(self.contract, selected)
            record = copy.deepcopy(self.record)
            record['items'][0]['source_timestamp'] = bad
            with self.assertRaisesRegex(ValueError, 'source_timestamp'):
                memory.validate_record(record)

    def test_memory_configuration_has_one_definition_for_both_backends(self):
        for policy in (
            self.contract['memory_context'],
            {'provider': 'supermemory', 'space': 'test-space',
             'purpose': 'avoid_repeating_previously_briefed_items', 'on_unavailable': 'continue_with_notice'}):
            data = copy.deepcopy(self.contract)
            data['memory_context'] = copy.deepcopy(policy)
            contract.validate(data)
            memory.validate_contract(data)
            extra = 'space' if policy['provider'] == 'local' else 'directory'
            data['memory_context'][extra] = '/unwanted-location'
            for validate in (contract.validate, memory.validate_contract):
                with self.assertRaises(ValueError):
                    validate(data)

    def test_budget_cli_validates_the_complete_contract_before_starting(self):
        with tempfile.TemporaryDirectory() as folder:
            self.contract['coverage_threads'][0]['account_actions'] = 'reply'
            path = Path(folder) / 'invalid.json'
            path.write_text(json.dumps(self.contract))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_budget.py'), 'start',
                                     '--contract', str(path)], capture_output=True, text=True,
                                    env={**os.environ, 'XDG_STATE_HOME': folder})
            self.assertEqual(result.returncode, 1)
            self.assertIn('account_actions', result.stderr)
            self.assertFalse((Path(folder) / 'attention-diet/runs').exists())

    def test_missing_dependencies_report_setup_instead_of_skipping_validation(self):
        result = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts/contract.py'), 'validate',
                                 '--contract', str(ROOT / 'templates/attention-contract.json')],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requirements.txt', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
