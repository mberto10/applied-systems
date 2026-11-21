"""Needs-you and front-page views, and the test run that previews them. No network."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(Path(__file__).parent))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


views = load('views')
briefing = load('briefing')
test_run = load('test_run')
contract_api = briefing.contract_api


def data(entries, held=None):
    return {'title': 'T', 'overview': 'O', 'meta': 'M', 'notices': [],
            'sections': [{'name': 'Agent workflows', 'entries': entries}], 'held_back': held or []}


def entry(title, url, source='treg · agent posts'):
    return {'title': title, 'summary': 'S', 'why': 'W', 'caveats': [], 'url': url, 'source': source, 'surprise': False}


class ViewTests(unittest.TestCase):
    def test_kind_comes_from_the_link(self):
        self.assertEqual([views.kind({'url': u}) for u in ('https://www.youtube.com/watch?v=1', 'https://x.com/a/status/1',
                                                           'https://example.org/post', None)],
                         ['video', 'post', 'article', 'article'])

    def test_needs_you_filters_without_script_and_escapes_text(self):
        html = views.needs_you(data([entry('<b>x</b>', 'https://x.com/a/status/1'), entry('Two', None, 'feeds · writer')],
                                    [{'reason': 'Weak match', 'count': 2}]))
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('id="f-s-agent-workflows"', html)  # one section needs no filter
        self.assertIn('id="f-o-feeds-writer"', html)  # a source filter appears once there are two sources
        self.assertIn('#f-o-feeds-writer:checked~.list article:not(.o-feeds-writer){display:none}', html)
        self.assertIn('<summary>Held back</summary>', html)
        self.assertIn('for="why" class="why-toggle">Reasons<', html)
        self.assertNotIn('passed', html)

    def test_front_page_puts_videos_in_their_own_row(self):
        items = [entry('Lead', 'https://example.org/1'), entry('Second', 'https://example.org/2'),
                 entry('Third', 'https://example.org/3'), entry('Clip', 'https://youtu.be/abc')]
        html = views.front_page(data(items))
        self.assertIn('class="lead article"', html)
        self.assertIn('<h2>Watch</h2>', html)
        self.assertLess(html.index('Lead'), html.index('Clip'))
        self.assertIn('Nothing new worth your time.', views.front_page(data([])))

    def test_both_interfaces_render_a_saved_selection_offline(self):
        contract = contract_api.validate(json.loads((ROOT / 'templates/attention-contract.json').read_text()))
        record = json.loads((ROOT / 'examples/selection.json').read_text())
        for interface in ('needs_you_html', 'front_page_html'):
            html = briefing.render(contract, record, interface)
            self.assertIn("default-src 'none'", html)
            self.assertNotIn('$content', html)

    def test_diagnostics_fold_behind_details_and_alerts_stay_visible(self):
        html = briefing.notices_html(['Gmail was unavailable.', 'X — agent posts: 20 posts sampled.', 'treg cost: $0.01.'])
        self.assertTrue(html.startswith('<p>Gmail was unavailable.</p><details class="diag"><summary>Details</summary>'))
        self.assertIn('treg cost', html.split('<details')[1])
        self.assertEqual(briefing.notices_html([]), '')

    def test_saved_selection_shows_only_the_date_above_the_list(self):
        contract = contract_api.validate(json.loads((ROOT / 'templates/attention-contract.json').read_text()))
        record = json.loads((ROOT / 'examples/selection.json').read_text())
        html = briefing.render(contract, record, 'needs_you_html')
        self.assertNotIn('selected item', html)
        self.assertNotIn('source area', html)

    def test_contract_accepts_the_new_interfaces(self):
        contract = json.loads((ROOT / 'examples/treg-contract.json').read_text())
        contract['composition'].update({'interface': 'front_page_html', 'format': 'html',
                                        'template': './interfaces/front-page/template.html'})
        contract_api.validate(contract)


class TestRunTests(unittest.TestCase):
    def test_collects_curates_and_writes_a_preview_without_memory(self):
        from test_treg_source import NOW, x_answer
        treg_source = test_run.treg_source
        contract = contract_api.validate(json.loads((ROOT / 'examples/treg-contract.json').read_text()))
        fetchers = {'treg': lambda c, t, s, n: treg_source.fetch(c, t, s, n, runner=lambda argv: x_answer(), now=NOW)}

        def treg(argv):
            body = json.loads(argv[argv.index('--data') + 1])
            strong = 'memory' in body['state']['item']['text']
            answers = {q: {'type': 'noul', 'noul': 0.9 if strong and q == 'i1' else 0.05} for q in body['questions'] if q != 'ev'}
            answers['ev'] = {'type': 'score', 'score': 1.6}
            return {'result': {'model': 'typesafe/jev-1.13-20260917', 'answers': answers}, '_treg': {'charged_micro': 20}}

        with tempfile.TemporaryDirectory() as out:
            summary = test_run.run(contract, out, fetchers=fetchers, transport={'treg': treg})
            html = (Path(out) / 'test-run.html').read_text()
            saved = json.loads((Path(out) / 'test-run.json').read_text())
        self.assertEqual(summary['counts'], {'looked_at': 2, 'passed': 1})
        self.assertEqual(summary['cost_micro'], {'collect': 2100, 'decide': 40})
        self.assertEqual(summary['interface'], 'needs_you_html')
        self.assertNotIn('class="src"', html)  # one source and one section need no label
        self.assertIn('Weak match with your interests', html)
        self.assertNotIn('Cost of this test run', html)
        self.assertEqual({e['decision'] for e in saved['entries']}, {'include', 'drop'})

    def test_browser_threads_are_skipped_and_named(self):
        contract = contract_api.validate(json.loads((ROOT / 'templates/attention-contract.json').read_text()))
        with tempfile.TemporaryDirectory() as out:
            summary = test_run.run(contract, out, fetchers={'feed': None, 'treg': None})
        self.assertEqual(summary['counts']['looked_at'], 0)
        self.assertTrue(summary['skipped'][0].startswith('source-1 (browser access'))


if __name__ == '__main__':
    unittest.main()
