"""Offline contract editing: no personal configuration, browser or connector access."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_contract import contract, TEMPLATE, ROOT


class ContractEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'ATTENTION_DIET_HOME': self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.document = json.loads(TEMPLATE.read_text())
        self.reason = 'In future, show at most three items from this source.'
        self.edit = {'reason': self.reason, 'patch': [
            {'op': 'replace', 'path': '/composition/max_items_by_thread/source-1', 'value': 3}]}

    def install(self):
        source = Path(self.tmp.name) / 'fixture.json'
        source.write_text(json.dumps(self.document))
        return Path(contract.install(source)['path'])

    def prepare(self, payload=None):
        return contract.prepare(payload or self.edit, expected_digest=contract.digest(self.document))

    def cli(self, *args, payload=None):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/contract.py'), *args],
                              input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True)

    def test_one_exclusion_has_one_small_diff_instead_of_the_whole_source_list(self):
        edited = copy.deepcopy(self.document)
        edited['revision'] += 1
        edited['coverage_threads'][0]['selection']['exclude'].append('Routine promotional updates.')
        changes = contract.diff(self.document, edited)
        self.assertEqual(changes, [{'path': '/coverage_threads/0/selection/exclude/0', 'op': 'add',
                                    'before': None, 'after': 'Routine promotional updates.'}])
        self.assertLess(len(json.dumps(changes)), 200)

    def test_diff_aligns_removed_and_edited_sources_and_preserves_reordering(self):
        old = copy.deepcopy(self.document)
        other = copy.deepcopy(old['coverage_threads'][0])
        other['id'] = 'source-2'
        old['coverage_threads'].append(other)
        new = copy.deepcopy(old)
        new['revision'] += 1
        new['coverage_threads'].pop(0)
        new['coverage_threads'][0]['selection']['exclude'].append('Promotion')
        changes = contract.diff(old, new)
        self.assertEqual([(c['path'], c['op']) for c in changes], [
            ('/coverage_threads/0', 'remove'), ('/coverage_threads/0/selection/exclude/0', 'add')])
        reordered = {**old, 'revision': 2, 'coverage_threads': list(reversed(old['coverage_threads']))}
        self.assertTrue(contract.diff(old, reordered))

    def test_missing_empty_and_null_values_are_distinct(self):
        self.assertEqual(contract.differences({}, {'a': None})[0]['op'], 'add')
        self.assertEqual(contract.differences({'a': {}}, {})[0]['op'], 'remove')
        self.assertEqual(contract.differences({'a': []}, {'a': {}})[0]['op'], 'replace')

    def test_resolve_returns_contract_once_and_inventory_is_compact(self):
        self.install()
        result = self.cli('resolve')
        self.assertEqual(result.returncode, 0, result.stderr)
        resolved = json.loads(result.stdout)
        self.assertEqual(resolved['contract'], self.document)
        self.assertEqual(resolved['digest'], contract.digest(self.document))
        listing = json.loads(self.cli('list').stdout)
        self.assertEqual(listing['contracts'], [self.document['id']])
        self.assertEqual(listing['summaries'][0]['sources'], [{'service': 'example-source', 'surfaces': ['items']}])
        self.assertNotIn('procedure', json.dumps(listing))

    def test_new_contract_uses_template_defaults_without_manual_files(self):
        prepared = contract.prepare(self.edit, contract_id='fixture', new=True)
        self.assertFalse(contract.contract_path('fixture').exists())
        proposal = contract.proposal_path(prepared['proposal'])
        self.assertEqual(proposal.stat().st_mode & 0o777, 0o600)
        result = contract.apply_proposal(prepared['proposal'], make_default=True)
        document = json.loads(Path(result['path']).read_text())
        self.assertEqual((document['id'], document['revision']), ('fixture', 1))
        self.assertEqual(document['memory_context']['directory'], '~/.local/state/attention-diet/fixture')
        self.assertEqual(contract.resolve(), Path(result['path']))
        self.assertFalse(proposal.exists())
        self.assertIn(self.reason, Path(result['changelog']).read_text())

    def test_apply_archives_records_correction_and_cleans_up_once(self):
        target = self.install()
        prepared = self.prepare()
        self.assertEqual(json.loads(target.read_text()), self.document)
        result = contract.apply_proposal(prepared['proposal'])
        current = json.loads(target.read_text())
        self.assertEqual(current['revision'], 2)
        self.assertEqual(current['composition']['max_items_by_thread']['source-1'], 3)
        self.assertEqual(current['memory_context'], self.document['memory_context'])
        self.assertEqual(json.loads((target.parent / 'revisions/1.json').read_text()), self.document)
        self.assertEqual(Path(result['changelog']).read_text().count(self.reason), 1)
        self.assertFalse(contract.proposal_path(prepared['proposal']).exists())

    def test_declined_proposal_leaves_no_correction_or_revision(self):
        target = self.install()
        prepared = self.prepare()
        contract.discard_proposal(prepared['proposal'])
        self.assertEqual(json.loads(target.read_text()), self.document)
        self.assertFalse((target.parent / 'changelog.md').exists())
        self.assertFalse((target.parent / 'revisions').exists())
        self.assertFalse(contract.proposal_path(prepared['proposal']).exists())

    def test_stale_resolve_and_stale_proposal_cannot_overwrite_intervening_edits(self):
        target = self.install()
        prepared = self.prepare()
        changed = copy.deepcopy(self.document)
        changed['intent']['purpose'] = 'An intervening edit even at the same revision.'
        target.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'resolve again'):
            self.prepare()
        with self.assertRaisesRegex(ValueError, 'changed since preparation'):
            contract.apply_proposal(prepared['proposal'])
        self.assertEqual(json.loads(target.read_text()), changed)
        self.assertFalse((target.parent / 'changelog.md').exists())

    def test_new_proposal_cannot_overwrite_a_contract_that_appeared_meanwhile(self):
        prepared = contract.prepare(self.edit, contract_id='fixture', new=True)
        data = json.loads(contract.proposal_path(prepared['proposal']).read_text())['contract']
        # Even identical content installed by another action is not this proposal's retry.
        target = contract.contract_path('fixture')
        contract.write_private(target, json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'changed since preparation'):
            contract.apply_proposal(prepared['proposal'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            contract.prepare(self.edit, contract_id='fixture', new=True)

    def test_patch_preserves_exact_strings_and_escaped_pointer_keys(self):
        text = 'Literal $(touch nope), `touch nope`, apostrophe\'s and 👀\nSecond line.'
        value = {'a/b': {'~key': ['old']}}
        result = contract.apply_patch(value, [
            {'op': 'add', 'path': '/a~1b/~0key/-', 'value': text},
            {'op': 'remove', 'path': '/a~1b/~0key/0'}])
        self.assertEqual(result['a/b']['~key'], [text])
        self.assertEqual(value['a/b']['~key'], ['old'])

    def test_invalid_or_noop_patches_never_prepare_or_change_contract(self):
        target = self.install()
        for operations in ([], [{'op': 'replace', 'path': '/revision', 'value': 8}],
                           [{'op': 'replace', 'path': '/id', 'value': 'other'}],
                           [{'op': 'replace', 'path': '', 'value': {}}],
                           [{'op': 'replace', 'path': '/missing/field', 'value': 1}],
                           [{'op': 'remove', 'path': '/coverage_threads/-1'}],
                           [{'op': 'replace', 'path': '/coverage_threads/01/id', 'value': 'x'}],
                           [{'op': 'replace', 'path': '/coverage_threads/4/id', 'value': 'x'}],
                           [{'op': 'add', 'path': '/coverage_threads/0/access/fallback', 'value': 'browser'}],
                           [{'op': 'replace', 'path': '/intent/purpose', 'value': self.document['intent']['purpose']}],
                           [{'op': 'copy', 'path': '/intent/purpose', 'value': 'x'}],
                           [{'op': 'remove', 'path': '/intent/purpose', 'value': 'unexpected'}]):
            with self.subTest(operations=operations), self.assertRaises(ValueError):
                self.prepare({'reason': 'Fixture', 'patch': operations})
        self.assertEqual(json.loads(target.read_text()), self.document)
        self.assertFalse((Path(self.tmp.name) / 'proposals').exists())

    def test_modified_prepared_document_cannot_be_applied(self):
        target = self.install()
        prepared = self.prepare()
        path = contract.proposal_path(prepared['proposal'])
        data = json.loads(path.read_text())
        data['contract']['intent']['purpose'] = 'Not the prepared correction'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Prepared contract changed'):
            contract.apply_proposal(prepared['proposal'])
        self.assertEqual(json.loads(target.read_text()), self.document)

    def test_retry_after_bookkeeping_failure_does_not_reapply_or_duplicate_revision(self):
        target = self.install()
        prepared = self.prepare()
        real_write = contract.write_private
        def fail_changelog(path, text):
            if path.name == 'changelog.md':
                raise OSError('Synthetic interrupted bookkeeping')
            return real_write(path, text)
        with patch.object(contract, 'write_private', side_effect=fail_changelog):
            with self.assertRaisesRegex(OSError, 'bookkeeping'):
                contract.apply_proposal(prepared['proposal'])
        self.assertEqual(json.loads(target.read_text())['revision'], 2)
        with self.assertRaisesRegex(ValueError, 'Application started'):
            contract.discard_proposal(prepared['proposal'])
        result = contract.apply_proposal(prepared['proposal'])
        self.assertEqual(json.loads(target.read_text())['revision'], 2)
        self.assertEqual(json.loads((target.parent / 'revisions/1.json').read_text()), self.document)
        self.assertEqual(Path(result['changelog']).read_text().count(self.reason), 1)

    def test_retry_preserves_default_choice_after_interrupted_default_write(self):
        prepared = contract.prepare(self.edit, contract_id='fixture', new=True)
        real_write = contract.write_private
        def fail_default(path, text):
            if path.name == 'default':
                raise OSError('Synthetic default write failure')
            return real_write(path, text)
        with patch.object(contract, 'write_private', side_effect=fail_default):
            with self.assertRaisesRegex(OSError, 'default write'):
                contract.apply_proposal(prepared['proposal'], make_default=True)
        contract.apply_proposal(prepared['proposal'])
        self.assertEqual((Path(self.tmp.name) / 'default').read_text(), 'fixture\n')

    def test_competing_prepared_revisions_only_apply_one(self):
        target = self.install()
        first = self.prepare()
        second = self.prepare({'reason': 'A different correction', 'patch': [
            {'op': 'replace', 'path': '/composition/max_items_by_thread/source-1', 'value': 2}]})
        contract.apply_proposal(first['proposal'])
        with self.assertRaisesRegex(ValueError, 'changed since preparation'):
            contract.apply_proposal(second['proposal'])
        self.assertEqual(json.loads(target.read_text())['composition']['max_items_by_thread']['source-1'], 3)

    def test_another_process_cannot_apply_while_contract_edit_is_locked(self):
        target = self.install()
        prepared = self.prepare()
        with contract.edit_lock():
            result = self.cli('apply', '--proposal', prepared['proposal'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Another contract edit', result.stderr)
        self.assertEqual(json.loads(target.read_text()), self.document)
        self.assertTrue(contract.proposal_path(prepared['proposal']).is_file())

    def test_cli_prepare_apply_round_trip_uses_stdin_without_agent_temp_files(self):
        self.install()
        resolved = json.loads(self.cli('resolve').stdout)
        result = self.cli('prepare', '--id', resolved['id'], '--expected-digest', resolved['digest'], '--input', '-', payload=self.edit)
        self.assertEqual(result.returncode, 0, result.stderr)
        prepared = json.loads(result.stdout)
        result = self.cli('apply', '--proposal', prepared['proposal'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['revision'], 2)
        self.assertEqual(list((Path(self.tmp.name) / 'proposals').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
