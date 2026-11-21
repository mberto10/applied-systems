"""The contract page: readable, escaped, offline and read-only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('contract_view', ROOT / 'scripts/contract_view.py')
view = importlib.util.module_from_spec(spec)
spec.loader.exec_module(view)


def example(name='feeds-contract.json'):
    return json.loads((ROOT / 'examples' / name).read_text())


CHANGELOG = ('- 2026-09-30 · revision 1: Created from the setup conversation (intent, coverage_threads)\n'
             '- 2026-10-02 · revision 2: Leave out <script> trailers (intent/excluded) <!-- proposal:abc -->\n'
             'Not a changelog line.\n')


class ContractViewTests(unittest.TestCase):
    def test_page_states_the_rules_in_plain_language(self):
        page = view.render(example(), CHANGELOG)
        for text in ('Keep up with the writers, channels and podcasts I follow', 'What counts',
                     'Analysis of how publishers and platforms earn money', 'Sponsored posts and product promotion.',
                     'Public RSS or Atom feed', 'https://example.org/podcast/feed.xml', '3 minutes', '30 items',
                     'At most 6 items per briefing.', 'Up to 1 labelled item', 'Not what you read, clicked or skipped.',
                     'Any action in your accounts', 'Revision 2: Leave out', 'The exact contract'):
            self.assertIn(text, page)
        self.assertNotIn('outbound_account_actions</li>', page)
        # Newest revision first, and the proposal marker is not shown.
        self.assertLess(page.index('Revision 2'), page.index('Revision 1'))
        self.assertNotIn('proposal:abc', page)

    def test_every_route_and_a_missing_changelog_render(self):
        inbox = view.render(example('inbox-contract.json'))
        self.assertIn('Connector mail_connector_found_in_setup', inbox)
        self.assertIn('Expected sign-in: you@example.com.', inbox)
        self.assertIn('Off. Nothing outside your stated interests', inbox)
        self.assertIn('No changelog was found', inbox)
        browser = view.render(example('sample-contract.json'))
        self.assertIn('Isolated browser session', browser)

    def test_contract_text_is_escaped_and_the_page_is_offline(self):
        contract = example()
        contract['intent']['purpose'] = '<img src=x onerror=alert(1)> & more'
        page = view.render(contract, CHANGELOG)
        self.assertNotIn('<img', page)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt; &amp; more', page)
        self.assertNotIn('<script', page)
        self.assertIn('&lt;script&gt; trailers', page)
        self.assertIn("default-src 'none'", page)

    def test_invalid_contracts_are_refused(self):
        contract = example()
        del contract['coverage_threads'][0]['feed_urls']
        with self.assertRaises(ValueError):
            view.render(contract)

    def test_cli_writes_the_page_and_reads_the_changelog_beside_the_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'attention_contract.json'
            source.write_text(json.dumps(example()))
            (Path(tmp) / 'changelog.md').write_text(CHANGELOG)
            before = source.read_bytes()
            out = Path(tmp) / 'views' / 'following.html'
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/contract_view.py'), 'render',
                                   '--contract', str(source), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn('Revision 2', out.read_text())
            self.assertEqual(source.read_bytes(), before)
            relative = subprocess.run([sys.executable, str(ROOT / 'scripts/contract_view.py'), 'render',
                                       '--contract', str(source), '--out', 'page.html'], capture_output=True, text=True)
            self.assertEqual(relative.returncode, 1)
            self.assertIn('absolute', json.loads(relative.stderr)['error'])


if __name__ == '__main__':
    unittest.main()
