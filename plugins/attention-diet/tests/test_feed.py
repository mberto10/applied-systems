"""Feed access: parsing, bounded reads, contract rules and a two-run replay. No network."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / 'fixtures'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feed = load('feed')
runtime = load('runtime')
run_plan = load('run_plan')
contract_api = feed.contract_api
memory, budget = runtime.memory, runtime.budget


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeOpener:
    def __init__(self, body):
        self.body, self.requests = body, []

    def open(self, request, timeout=None):
        self.requests.append((request.full_url, request.get_header('User-agent'), timeout))
        return FakeResponse(self.body)


def example():
    return json.loads((ROOT / 'examples/feeds-contract.json').read_text())


class ParseTests(unittest.TestCase):
    def test_rss_entries_are_plain_text_with_stable_identity_and_basis(self):
        parsed = feed.parse((FIXTURES / 'feed-rss.xml').read_bytes())
        self.assertEqual(parsed['format'], 'rss')
        self.assertEqual(parsed['feed'], {'title': 'An Example Writer', 'link': 'https://writer.example.org/'})
        first = parsed['entries'][0]
        self.assertEqual(first['identifier'], 'writer-post-3')
        self.assertEqual(first['text'], 'First paragraph with markup. Second paragraph.')
        self.assertEqual(first['published'], '2026-09-29T05:30:00+00:00')
        self.assertEqual(first['basis'], {'sender': 'Alex Example',
                                          'text': 'A repeatable method, with its limits\nFirst paragraph with markup. Second paragraph.',
                                          'occurred_at': '2026-09-29T05:30:00+00:00'})
        # No author: the feed title stands in, so the basis is still deterministic.
        self.assertEqual(parsed['entries'][1]['basis']['sender'], 'An Example Writer')
        old = parsed['entries'][3]
        self.assertEqual(old['identifier'], 'http://writer.example.org/p/old')  # identity, not a link to follow
        self.assertIsNone(old['url'])
        self.assertIsNone(old['published'])
        self.assertNotIn('occurred_at', old['basis'])
        self.assertEqual(parsed['unidentified_entries'], 1)

    def test_atom_uses_media_description_and_feed_author(self):
        parsed = feed.parse((FIXTURES / 'feed-atom.xml').read_bytes())
        self.assertEqual(parsed['format'], 'atom')
        first, second = parsed['entries']
        self.assertEqual((first['identifier'], first['url']), ('video:abc123', 'https://video.example.org/watch?v=abc123'))
        self.assertEqual(first['author'], 'Example Channel')
        self.assertEqual(first['text'], 'A walk-through of the method.')
        self.assertEqual(second['author'], 'Guest Author')
        self.assertEqual(second['text'], 'Summary text.')
        self.assertEqual(second['published'], '2026-09-20T08:00:00+00:00')

    def test_rdf_feeds_parse(self):
        parsed = feed.parse((FIXTURES / 'feed-rdf.xml').read_bytes())
        self.assertEqual(parsed['format'], 'rss1')
        self.assertEqual(parsed['entries'][0]['identifier'], 'https://papers.example.org/abs/2609.00001')
        self.assertEqual(parsed['entries'][0]['author'], 'A. Author, B. Author')

    def test_long_text_is_clipped_to_a_fixed_length(self):
        body = ('<rss><channel><title>T</title><item><guid>g</guid><title>x</title><description>'
                + 'word ' * 600 + '</description></item></channel></rss>').encode()
        entry = feed.parse(body)['entries'][0]
        self.assertTrue(entry['text_truncated'])
        self.assertLessEqual(len(entry['text']), feed.TEXT_LIMIT + 1)
        self.assertEqual(entry, feed.parse(body)['entries'][0])

    def test_entities_non_feeds_and_broken_documents_are_refused(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><title>&a;</title></channel></rss>'
        for document, message in ((bomb, 'DOCTYPE'), (b'<html><body/></html>', 'Not an RSS'), (b'<rss><channel>', 'well-formed')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                feed.parse(document)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract_api.validate(example())
        self.body = (FIXTURES / 'feed-rss.xml').read_bytes()

    def test_reads_only_the_contract_url_within_the_window_and_skips_seen_entries(self):
        opener = FakeOpener(self.body)
        first = feed.fetch(self.contract, 'following', 'writer', 2, opener=opener)
        self.assertEqual(opener.requests[0][0], self.contract['coverage_threads'][0]['feed_urls']['writer'])
        self.assertIn('AttentionDiet', opener.requests[0][1])
        self.assertEqual([e['identifier'] for e in first['entries']], ['writer-post-3', 'writer-post-2'])
        # The duplicate listing counts once: three distinct identified entries remain in total.
        self.assertEqual((first['remaining_in_document'], first['more_available'], first['exhaustion']), (1, True, None))
        self.assertEqual(first['account_key'], 'feed:public')
        rest = feed.fetch(self.contract, 'following', 'writer', 10,
                          seen=[e['identifier'] for e in first['entries']], opener=FakeOpener(self.body))
        self.assertEqual([e['identifier'] for e in rest['entries']], ['http://writer.example.org/p/old'])
        self.assertFalse(rest['more_available'])
        self.assertEqual(rest['exhaustion']['kind'], 'documented_connector_end')
        empty = feed.fetch(self.contract, 'following', 'writer', 0, opener=FakeOpener(self.body))
        self.assertEqual(empty['entries'], [])

    def test_only_configured_feed_surfaces_and_plain_https(self):
        with self.assertRaisesRegex(ValueError, 'not configured'):
            feed.fetch(self.contract, 'following', 'elsewhere', 5, opener=FakeOpener(self.body))
        with self.assertRaisesRegex(ValueError, 'not a configured feed'):
            feed.fetch(self.contract, 'missing', 'writer', 5, opener=FakeOpener(self.body))
        with self.assertRaisesRegex(ValueError, 'plain https'):
            feed.download('http://writer.example.org/feed', FakeOpener(self.body))
        handler = feed._HttpsOnly()
        with self.assertRaisesRegex(ValueError, 'redirected'):
            handler.redirect_request(None, None, 302, 'Found', {}, 'http://writer.example.org/feed')

    def test_oversized_documents_are_not_read(self):
        with patch.object(feed, 'MAX_BYTES', 100), self.assertRaisesRegex(ValueError, 'exceeds'):
            feed.download('https://writer.example.org/feed', FakeOpener(self.body))

    def test_cli_reports_errors_as_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'c.json'
            path.write_text(json.dumps(example()))
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/feed.py'), 'fetch', '--contract', str(path),
                                   '--input', '-'], input='{"thread_id":"following","surface":"nope","max_items":1}',
                                  capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn('not configured', json.loads(done.stderr)['error'])


class ContractTests(unittest.TestCase):
    def test_feed_threads_need_urls_for_every_surface_public_content_and_https(self):
        contract_api.validate(example())
        broken = example()
        del broken['coverage_threads'][0]['feed_urls']['podcast']
        with self.assertRaisesRegex(ValueError, 'feed_urls must cover'):
            contract_api.validate(broken)
        private = example()
        private['coverage_threads'][0]['content'] = 'private_communication'
        with self.assertRaisesRegex(ValueError, 'public_posts'):
            contract_api.validate(private)
        plain = example()
        plain['coverage_threads'][0]['feed_urls']['writer'] = 'https://user:pw@writer.example.org/feed'
        with self.assertRaisesRegex(ValueError, 'plain https'):
            contract_api.validate(plain)
        missing = example()
        del missing['coverage_threads'][0]['feed_urls']
        with self.assertRaises(ValueError):
            contract_api.validate(missing)

    def test_other_routes_cannot_carry_feed_urls(self):
        inbox = json.loads((ROOT / 'examples/inbox-contract.json').read_text())
        inbox['coverage_threads'][0]['feed_urls'] = {'newsletters': 'https://a.example.org/feed',
                                                     'alerts': 'https://b.example.org/feed'}
        with self.assertRaises(ValueError):
            contract_api.validate(inbox)

    def test_plan_routes_feeds_to_the_helper_and_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'c.json'
            path.write_text(json.dumps(example()))
            plan = run_plan.prepare(path, 'claude')
        self.assertEqual(plan['routes'], [{'thread_id': 'following', 'type': 'feed', 'fallback': 'none',
                                           'account_key': 'feed:public', 'availability': 'fetch_on_run'}])
        self.assertTrue(plan['helpers']['feed'].endswith('scripts/feed.py'))
        self.assertEqual([Path(p).name for p in plan['read_once']], ['feeds.md'])
        self.assertEqual(plan['tools']['source_namespaces'], [])


class FeedRunTests(unittest.TestCase):
    """Two runs over the same feed: the second brings nothing already briefed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'XDG_STATE_HOME': self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.contract = example()
        self.contract['memory_context']['directory'] = self.tmp.name + '/memory'
        self.path = Path(self.tmp.name) / 'contract.json'
        self.path.write_text(json.dumps(self.contract))
        self.body = (FIXTURES / 'feed-rss.xml').read_bytes()

    def run_once(self):
        opened = runtime.start(self.path)
        state = memory.read_json(budget.state_path(opened['run_id']))
        window = runtime.observation_window(state, self.contract, {
            'account_key': 'feed:public', 'thread_id': 'following', 'surface': 'writer', 'max_items': 10})
        read = feed.fetch(self.contract, 'following', 'writer', window['limit'],
                          window['seen_identifiers'], opener=FakeOpener(self.body))
        cards = [{'identifier': e['identifier'], **({'basis': e['basis']} if e['identifier'] == 'writer-post-3' else {})}
                 for e in read['entries']]
        payload = {'ticket': window['ticket'], 'cards': cards, 'more_available': read['more_available'],
                   'evidence': read['evidence']}
        if read['exhaustion']:
            payload['exhaustion'] = read['exhaustion']
        result = runtime.capture_window(state, self.contract, payload)
        return state, result

    def test_capture_counts_every_entry_and_memory_suppresses_the_repeat(self):
        state, result = self.run_once()
        self.assertEqual(result['coverage'][0]['inspected_count'], 3)
        self.assertEqual(result['coverage'][0]['stop_reason'], 'exhausted_results')
        ref = result['references'][0]['ref']
        self.assertEqual(state['candidates'][ref]['novelty'], 'new')
        selection = json.loads((ROOT / 'examples/selection.json').read_text())
        entry = {k: selection['entries'][0][k] for k in ('title', 'summary', 'why')}
        entry.update(item_refs=[ref], url='https://writer.example.org/p/method', caveats=[])
        runtime.finalize(state, self.contract, {'title': 'Feeds', 'overview': 'One new post.',
                                                'entries': [entry], 'notices': []})
        runtime.finish(state, self.contract)
        again, second = self.run_once()
        ref = second['references'][0]['ref']
        self.assertEqual(again['candidates'][ref]['novelty'], 'already_briefed')


if __name__ == '__main__':
    unittest.main()
