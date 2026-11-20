"""treg access: row normalization, window and seen filtering, the CLI call and contract rules. No network."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
NOW = 1_800_000_000  # 2027-01-15T08:00:00Z


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


treg = load('treg_source')
run_plan = load('run_plan')
contract_api = treg.contract_api


def example():
    return json.loads((ROOT / 'examples/treg-contract.json').read_text())


def x_answer():
    """A vendor answer shaped like an X search: tweets in a list, Twitter's date format, a wrapper object."""
    return {'result': {'data': {'tweets': [
        {'id_str': '11', 'full_text': 'I built a memory hook; 41 saved preferences, 3 wrong.',
         'created_at': 'Fri Jan 15 07:00:00 +0000 2027', 'favorite_count': 820, 'reply_count': 40,
         'retweet_count': 90, 'user': {'screen_name': 'builder_a'},
         'url': 'https://x.com/builder_a/status/11?s=20'},
        {'id_str': '12', 'full_text': 'Old post', 'created_at': 'Tue Jan 12 07:00:00 +0000 2027',
         'favorite_count': 5, 'user': {'screen_name': 'old'}, 'url': 'https://x.com/old/status/12'},
        {'full_text': 'No id and no link', 'favorite_count': 3},
        {'id_str': '11', 'full_text': 'I built a memory hook; 41 saved preferences, 3 wrong.',
         'created_at': 'Fri Jan 15 07:00:00 +0000 2027', 'favorite_count': 821,
         'user': {'screen_name': 'builder_a'}, 'url': 'https://x.com/builder_a/status/11'},
        {'id_str': '13', 'text': 'Undated but identified', 'likeCount': '1.2K', 'url': 'https://x.com/c/status/13'},
    ]}}, '_treg': {'charged_micro': 2100}}


class NormalizeTests(unittest.TestCase):
    def test_rows_finds_the_largest_list_and_unwraps_each_row(self):
        listing = {'data': {'children': [{'kind': 't3', 'data': {'id': 'a', 'title': 'A'}},
                                         {'kind': 't3', 'data': {'id': 'b', 'title': 'B'}}]}}
        self.assertEqual([r['title'] for r in treg.rows(listing)], ['A', 'B'])
        tiktok = {'videos': [{'aweme_info': {'aweme_id': '7', 'desc': 'clip'}}]}
        self.assertEqual(treg.rows(tiktok)[0]['desc'], 'clip')

    def test_entry_basis_excludes_engagement_and_keeps_absolute_time(self):
        row = x_answer()['result']['data']['tweets'][0]
        item = treg.entry(row, 'X', 'treg.x.search.posts')
        self.assertEqual(item['identifier'], 'https://x.com/builder_a/status/11')  # tracking query dropped
        self.assertEqual(item['basis'], {'sender': '@builder_a', 'text': row['full_text'],
                                         'occurred_at': '2027-01-15T07:00:00+00:00'})
        self.assertEqual(item['engagement'], {'likes': 820, 'comments': 40, 'shares': 90, 'views': 0})
        changed = treg.entry(dict(row, favorite_count=9999), 'X', 'treg.x.search.posts')
        self.assertEqual(changed['basis'], item['basis'])  # a new like count is not a new post

    def test_reddit_identity_is_the_thread_not_the_linked_image(self):
        row = {'id': 'abc', 'title': 'Agent memory benchmark', 'url': 'https://i.redd.it/x.png',
               'permalink': '/r/LocalLLaMA/comments/abc/agent_memory/', 'created_utc': NOW - 600, 'ups': 431}
        item = treg.entry(row, 'Reddit', 'reddit.subreddit.posts')
        self.assertEqual(item['url'], 'https://www.reddit.com/r/LocalLLaMA/comments/abc/agent_memory')
        self.assertEqual(item['engagement']['likes'], 431)

    def test_vendor_id_stands_in_when_there_is_no_link_and_nothing_is_invented(self):
        self.assertEqual(treg.entry({'aweme_id': '7', 'desc': 'clip'}, 'TikTok', 'treg.tiktok.search.videos')['identifier'],
                         'treg.tiktok.search.videos:7')
        self.assertIsNone(treg.entry({'desc': 'nothing to identify'}, 'TikTok', 'treg.tiktok.search.videos'))
        self.assertIsNone(treg.entry({'id': '1', 'url': 'http://insecure.example/p'}, 'S', 'c')['url'])

    def test_counts_and_times(self):
        self.assertEqual([treg.count(v) for v in (12, '1,234', '1.2K', '3M views', None, True)],
                         [12, 1234, 1200, 3000000, 0, 0])
        self.assertEqual(treg.moment(1_700_000_000_000).timestamp(), 1_700_000_000)
        self.assertIsNone(treg.moment('2026-11-20T08:00:00'))  # no zone, no absolute time
        self.assertIsNone(treg.moment('yesterday'))


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract_api.validate(example())
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        return x_answer()

    def test_call_uses_only_the_contract_catalog_id_and_window(self):
        result = treg.fetch(self.contract, 'x-agents', 'agent_posts', 10, runner=self.runner, now=NOW)
        argv = self.calls[0]
        self.assertEqual(argv[:6], ['treg', '--json', 'call', 'treg.x.search.posts', '--method', 'POST'])
        self.assertNotIn('--query', argv)
        body = json.loads(argv[argv.index('--data') + 1])
        self.assertIn('since:2027-01-14 ', body['q'])  # the window's start date, filled into the POST body
        self.assertNotIn('{since_date}', body['q'])
        self.assertEqual([e['identifier'] for e in result['entries']],
                         ['https://x.com/builder_a/status/11', 'https://x.com/c/status/13'])
        self.assertEqual((result['outside_window'], result['undated_entries'], result['unidentified_entries']), (1, 1, 1))
        self.assertEqual(result['charged_micro'], 2100)
        self.assertEqual(result['account_key'], 'treg:public')
        self.assertIsNone(result['more_available'])  # one page; the rest of the service is unknown
        self.assertIsNone(result['exhaustion'])

    def test_seen_identifiers_and_window_limit_bound_the_batch(self):
        result = treg.fetch(self.contract, 'x-agents', 'agent_posts', 1, runner=self.runner, now=NOW)
        self.assertEqual(len(result['entries']), 1)
        self.assertTrue(result['more_available'])
        again = treg.fetch(self.contract, 'x-agents', 'agent_posts', 10, seen=['https://x.com/builder_a/status/11'],
                           runner=self.runner, now=NOW)
        self.assertEqual([e['identifier'] for e in again['entries']], ['https://x.com/c/status/13'])

    def test_rejects_threads_and_surfaces_outside_the_contract(self):
        with self.assertRaises(ValueError):
            treg.fetch(self.contract, 'nope', 'agent_posts', 5, runner=self.runner)
        with self.assertRaises(ValueError):
            treg.fetch(self.contract, 'x-agents', 'home_feed', 5, runner=self.runner)
        with self.assertRaises(ValueError):
            treg.fetch(self.contract, 'x-agents', 'agent_posts', -1, runner=self.runner)

    def test_placeholders_fill_nested_strings_only(self):
        values = treg.window_values(24, NOW)
        self.assertEqual(treg.fill({'q': 'x since_time:{since_unix}', 'n': 5, 'l': ['{since_date}']}, values),
                         {'q': f'x since_time:{NOW - 86400}', 'n': 5, 'l': ['2027-01-14']})

    def test_post_calls_send_the_body(self):
        argv = treg.call_argv('treg', {'catalog_id': 'a.b', 'method': 'POST', 'body': {'k': 'v'}, 'query': {}})
        self.assertEqual(argv, ['treg', '--json', 'call', 'a.b', '--method', 'POST', '--data', '{"k": "v"}'])


class ContractTests(unittest.TestCase):
    def test_example_is_valid_and_plans_the_treg_route(self):
        plan = run_plan.prepare(ROOT / 'examples/treg-contract.json', 'claude')
        route = plan['routes'][0]
        self.assertEqual((route['type'], route['account_key'], route['catalog_ids']),
                         ('treg', 'treg:public', ['treg.x.search.posts']))
        self.assertIn('treg', plan['helpers'])
        self.assertIn('decide', plan['helpers'])
        self.assertTrue(any(p.endswith('integrations/treg.md') for p in plan['read_once']))

    def test_rules(self):
        base = example()
        cases = []
        missing = copy.deepcopy(base)
        missing['coverage_threads'][0]['treg_calls'] = {}
        cases.append(missing)
        private = copy.deepcopy(base)
        private['coverage_threads'][0]['content'] = 'private_communication'
        cases.append(private)
        bad_id = copy.deepcopy(base)
        bad_id['coverage_threads'][0]['treg_calls']['agent_posts']['catalog_id'] = 'Bad Id; rm -rf'
        cases.append(bad_id)
        long_window = copy.deepcopy(base)
        long_window['coverage_threads'][0]['treg_calls']['agent_posts']['window_hours'] = 500
        cases.append(long_window)
        stray = json.loads((ROOT / 'examples/feeds-contract.json').read_text())
        stray['coverage_threads'][0]['treg_calls'] = base['coverage_threads'][0]['treg_calls']
        cases.append(stray)
        for case in cases:
            with self.assertRaises(ValueError):
                contract_api.validate(case)


if __name__ == '__main__':
    unittest.main()
