"""Watched handles, the following import and inbox questions. No network."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
NOW = 1_800_000_000  # 2027-01-15T08:00:00Z


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


treg = load('treg_source')
importer = load('import_following')
decide = load('decide')
contract_api = treg.contract_api


def example():
    return json.loads((ROOT / 'examples/treg-contract.json').read_text())


def post(handle, n, hours_ago=1, text=None):
    return {'id_str': f'{handle}{n}', 'full_text': text or f'{handle} post {n}', 'created_at': NOW - hours_ago * 3600,
            'url': f'https://x.com/{handle}/status/{len(handle)}{n}'}


class HandleTests(unittest.TestCase):
    def watched(self, **extra):
        contract = example()
        thread = contract['coverage_threads'][0]
        thread['surfaces'].append('watched')
        thread['targets']['watched'] = {'scope': 'New posts from the watched accounts.'}
        thread['collection']['watched'] = {'mode': 'sample', 'max_items': 4}
        thread['treg_calls']['watched'] = {'catalog_id': 'treg.x.user.posts', 'label': 'X', 'method': 'POST',
                                           'body': {'username': '{handle}'}, 'window_hours': 24,
                                           'handles': ['busy', 'quiet'], **extra}
        return contract_api.validate(contract)

    def test_one_call_per_handle_interleaved_with_the_handle_as_author(self):
        calls = []

        def runner(argv):
            user = json.loads(argv[argv.index('--data') + 1])['username']
            calls.append(user)
            rows = [post(user, n) for n in range(5)] if user == 'busy' else [post(user, 1), post(user, 2, hours_ago=48)]
            return {'result': {'output': rows}, '_treg': {'charged_micro': 500}}

        got = treg.fetch(self.watched(), 'x-agents', 'watched', 4, runner=runner, now=NOW)
        self.assertEqual(calls, ['busy', 'quiet'])
        self.assertEqual([e['author'] for e in got['entries']], ['busy', 'quiet', 'busy', 'busy'])  # quiet is not cut
        self.assertEqual((got['charged_micro'], got['outside_window'], got['remaining_in_response']), (1000, 1, 2))

    def test_replies_can_be_skipped_and_a_failed_handle_does_not_stop_the_rest(self):
        def runner(argv):
            user = json.loads(argv[argv.index('--data') + 1])['username']
            if user == 'busy':
                raise ValueError('treg call failed: no provider answered')
            return {'result': {'output': [post(user, 1, text='@someone thanks'), post(user, 2)]}}

        got = treg.fetch(self.watched(skip_replies=True), 'x-agents', 'watched', 10, runner=runner, now=NOW)
        self.assertEqual([e['identifier'] for e in got['entries']], ['https://x.com/quiet/status/52'])
        self.assertEqual((got['replies_skipped'], len(got['failed_calls'])), (1, 1))
        with self.assertRaisesRegex(ValueError, 'no provider'):
            treg.fetch(self.watched(handles=['busy']), 'x-agents', 'watched', 10, runner=runner, now=NOW)

    def test_from_handles_groups_handles_into_search_clauses(self):
        contract = example()
        call = contract['coverage_threads'][0]['treg_calls']['agent_posts']
        call.update(body={'q': '{from_handles} since:{since_date} -is:retweet'}, handles=['a', 'b', 'c'], group_size=2)
        queries = []
        treg.fetch(contract_api.validate(contract), 'x-agents', 'agent_posts', 5, now=NOW,
                   runner=lambda argv: queries.append(json.loads(argv[argv.index('--data') + 1])['q']) or {'result': []})
        self.assertEqual(queries, ['(from:a OR from:b) since:2027-01-14 -is:retweet',
                                   '(from:c) since:2027-01-14 -is:retweet'])

    def test_handles_and_placeholders_go_together(self):
        contract = example()
        call = contract['coverage_threads'][0]['treg_calls']['agent_posts']
        broken = copy.deepcopy(contract)
        broken['coverage_threads'][0]['treg_calls']['agent_posts']['handles'] = ['a']
        with self.assertRaisesRegex(ValueError, 'go together'):
            contract_api.validate(broken)
        call.update(body={'q': '{from_handles}'}, handles=['a', 'A'])
        with self.assertRaisesRegex(ValueError, 'listed twice'):
            contract_api.validate(contract)


class ImportTests(unittest.TestCase):
    def test_pages_through_the_following_list_until_the_cursor_ends(self):
        pages = {None: (['a', 'b'], 'c1'), 'c1': (['b', 'c'], '0')}
        seen = []

        def runner(argv):
            cursor = next((a.split('=', 1)[1] for a in argv if a.startswith('cursor=')), None)
            seen.append(cursor)
            names, nxt = pages[cursor]
            return {'result': {'data': {'following': [{'screen_name': n} for n in names], 'next_cursor': nxt}},
                    '_treg': {'charged_micro': 1000}}

        self.assertEqual(importer.following('me', runner=runner), (['a', 'b', 'c'], 2000))
        self.assertEqual(seen, [None, 'c1'])

    def test_patch_leaves_out_handles_another_surface_checks(self):
        contract = example()
        thread = contract['coverage_threads'][0]
        thread['treg_calls']['agent_posts'].update(body={'q': '{from_handles}'}, handles=['old'])
        thread['surfaces'].append('watched')
        thread['targets']['watched'] = {'scope': 'Watched accounts.'}
        thread['treg_calls']['watched'] = {'catalog_id': 'treg.x.user.posts', 'method': 'POST', 'window_hours': 24,
                                           'body': {'username': '{handle}'}, 'handles': ['Karpathy']}
        patch, summary = importer.surface_patch(contract_api.validate(contract), 'x-agents', 'agent_posts',
                                                ['karpathy', 'simonw', 'swyx'])
        self.assertEqual(patch[0]['value'], ['simonw', 'swyx'])
        self.assertEqual((summary['added'], summary['removed'], summary['left_out']), (['simonw', 'swyx'], ['old'], ['karpathy']))
        contract_api.validate(contract_api.apply_patch(contract, patch))


class InboxQuestionTests(unittest.TestCase):
    def test_a_thread_asks_its_own_questions_and_private_mail_skips_the_evidence_rubric(self):
        contract = json.loads((ROOT / 'examples/gmail-contract.json').read_text())
        contract_api.validate(contract)
        thread = contract['coverage_threads'][0]
        asked = decide.questions(contract, thread)
        self.assertEqual([q['ref'] for q in asked if q['kind'] == 'interest'], [i['id'] for i in thread['interests']])
        self.assertNotIn('ev', [q['name'] for q in asked])
        self.assertIn('include', decide.judge({**{q['name']: 0.0 for q in asked}, 'i1': 0.9}, asked,
                                              decide.settings(contract))['decision'])


if __name__ == '__main__':
    unittest.main()
