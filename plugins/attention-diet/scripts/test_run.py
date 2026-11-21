#!/usr/bin/env python3
"""A test run: collect, curate and render a preview of one contract, with no memory and no runtime.

For trying a contract while it is being written. It reads the feed and treg surfaces the contract
names (browser and connector sources need the agent and are listed as skipped), scores the entries
with the contract's decision model when `curation` is set, and writes two files: `test-run.json`
with every entry, its decision and the costs, and `test-run.html` in the contract's view (the
needs-you list when the view is not an HTML one). Nothing is remembered, so a real check later
still shows what this run found. treg calls and decision-model calls are billed as usual.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import briefing  # noqa: E402
import contract as contract_api  # noqa: E402
import decide  # noqa: E402
import feed  # noqa: E402
import treg_source  # noqa: E402

require = contract_api.require
PREVIEWS = {'needs_you_html', 'front_page_html', 'briefing_html', 'discovery_html'}


def headline(entry):
    """A title for an entry that has none: its first sentence, cut at a word."""
    if entry.get('title'):
        return entry['title']
    text = entry.get('text') or entry['identifier']
    first = text.split('. ')[0].split('\n')[0]
    return first if len(first) <= 110 else first[:110].rsplit(' ', 1)[0] + '…'


def collect(contract, max_items, fetchers):
    """Every feed and treg surface, read once. Returns entries per thread, skipped threads and costs."""
    batches, skipped, errors, charged = [], [], [], 0
    for thread in contract['coverage_threads']:
        kind = thread['access']['type']
        if kind not in fetchers:
            skipped.append(f'{thread["id"]} ({kind} access needs the agent; not part of a test run)')
            continue
        for surface in thread['surfaces']:
            try:
                got = fetchers[kind](contract, thread['id'], surface, max_items)
            except (ValueError, OSError) as error:
                errors.append(f'{thread["id"]}/{surface}: {error}')
                continue
            charged += got.get('charged_micro') or 0
            call = (thread.get('treg_calls') or {}).get(surface) or {}
            source = call.get('label') or briefing.source_label(thread, surface)
            for entry in got['entries']:
                batches.append({**entry, 'thread_id': thread['id'], 'surface': surface, 'source': source})
    return batches, skipped, errors, charged


def curate(contract, entries, transport=None):
    """Decisions by identifier. Without curation every entry stays unjudged: the agent judges in a real check."""
    if 'curation' not in contract:
        return {e['identifier']: {'decision': 'undecided', 'reason': 'No decision model in this contract.'} for e in entries}, [], 0
    decisions, errors, charged = {}, [], 0
    by_list = {}
    for entry in entries:
        by_list.setdefault((entry['thread_id'], entry['surface']), []).append(entry)
    for (thread_id, surface), group in by_list.items():
        result = decide.score(contract, thread_id, group, transport, surface)
        errors += result['errors']
        charged += result['charged_micro'] or 0
        decisions.update({d['identifier']: d for d in result['decisions']})
    return decisions, errors, charged


def held_reason(decision):
    if decision['decision'] == 'undecided':
        return 'Not judged'
    if decision.get('excluded_by'):
        return 'Excluded: ' + decision['excluded_by'][0].rstrip('.')
    if decision['reason'].startswith('Below the top'):
        return 'Below the top share of its list'
    if decision['reason'].startswith('Weak match'):
        return 'Weak match with your interests'
    return 'Below the evidence minimum'


def preview_data(contract, entries, decisions, notices):
    interests = {i['id']: i['focus'] for i in contract['intent'].get('interests', [])}
    passed = sorted((e for e in entries if decisions[e['identifier']]['decision'] == 'include'),
                    key=lambda e: -(decisions[e['identifier']].get('rank') or 0))
    sections = {}
    for e in passed:
        d = decisions[e['identifier']]
        name = e['source'] if d.get('reason') == 'Every post from this list' else briefing.label(d.get('best_interest') or 'selected')
        sections.setdefault(name, []).append({
            'title': headline(e), 'summary': (e.get('text') or '')[:280], 'why': d['reason'], 'caveats': [],
            'url': e.get('url'), 'source': e['source'], 'surprise': False})
    held = Counter(held_reason(decisions[e['identifier']]) for e in entries if decisions[e['identifier']]['decision'] != 'include')
    return {
        'title': contract['id'],
        'overview': '',
        'meta': datetime.now().strftime('%A %d %B · %H:%M'),
        'notices': notices, 'interests': interests,
        'sections': [{'name': name, 'entries': group} for name, group in sections.items()],
        'held_back': [{'reason': reason, 'count': n} for reason, n in held.most_common()],
    }


def render_preview(contract, data):
    interface = contract['composition']['interface']
    interface = interface if interface in PREVIEWS - {'briefing_html', 'discovery_html'} else 'needs_you_html'
    body = briefing.views.needs_you(data) if interface == 'needs_you_html' else briefing.views.front_page(data)
    return interface, briefing.render_template(contract, interface, {
        'title': escape(data['title']), 'overview': escape(data['overview']), 'meta': escape(data['meta']),
        'layout': 'briefing', 'content': body, 'data': '{}',
        'notices': briefing.notices_html(data['notices'])},
        template_path=briefing.ROOT / briefing.DEFAULT_TEMPLATES[interface])


def run(contract, out_dir, max_items=10, fetchers=None, transport=None):
    fetchers = fetchers or {
        'feed': lambda c, t, s, n: feed.fetch(c, t, s, n),
        'treg': lambda c, t, s, n: treg_source.fetch(c, t, s, n),
    }
    entries, skipped, errors, collect_cost = collect(contract, max_items, fetchers)
    decisions, decide_errors, decide_cost = curate(contract, entries, transport)
    notices = ['Not checked: ' + s for s in skipped] + ['Could not read ' + e for e in errors]
    if decide_errors:
        notices.append(f'The decision model did not answer for {len(decide_errors)} entries; they are listed as not judged.')
    data = preview_data(contract, entries, decisions, notices)
    interface, html = render_preview(contract, data)
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'test-run.html').write_text(html)
    summary = {
        'contract_id': contract['id'], 'revision': contract['revision'],
        'ran_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'interface': interface,
        'html': str(out_dir / 'test-run.html'),
        'counts': {'looked_at': len(entries), 'passed': sum(d['decision'] == 'include' for d in decisions.values())},
        'cost_micro': {'collect': collect_cost, 'decide': decide_cost},
        'thresholds': decide.settings(contract) if 'curation' in contract else None,
        'skipped': skipped, 'errors': errors + decide_errors,
        'entries': [{'identifier': e['identifier'], 'source': e['source'], 'title': headline(e), 'url': e.get('url'),
                     'published': e.get('published'), 'engagement': e.get('engagement'),
                     **{k: v for k, v in decisions[e['identifier']].items() if k != 'identifier'}} for e in entries],
    }
    (out_dir / 'test-run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--contract')
    parser.add_argument('--id')
    parser.add_argument('--out', required=True, help='Folder for test-run.json and test-run.html')
    parser.add_argument('--max-items', type=int, default=10, help='Entries per surface, at most 30')
    args = parser.parse_args()
    try:
        require(1 <= args.max_items <= 30, '--max-items must be between 1 and 30')
        path = Path(args.contract).expanduser() if args.contract else contract_api.resolve(args.id)
        contract = contract_api.validate(contract_api.memory.read_json(path))
        summary = run(contract, args.out, args.max_items)
        print(json.dumps({k: summary[k] for k in ('html', 'counts', 'cost_micro', 'skipped', 'errors')}, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
