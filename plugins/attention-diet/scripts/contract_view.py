#!/usr/bin/env python3
"""Render an attention contract as one readable local page: your algorithm, in plain text.

Read-only: it validates and displays the contract and its changelog, and never collects sources,
reads briefing memory or changes the contract. Changes go through the tune skill.
"""
import argparse
from html import escape
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import contract as contract_api  # noqa: E402

require = contract_api.require
# Internal tokens in `intent.excluded` that are guarantees rather than topics.
TOKENS = {'outbound_account_actions': 'Any action in your accounts: no replies, reactions, follows or messages.'}
CHANGE = re.compile(r'^- (\d{4}-\d{2}-\d{2}) · revision (\d+): (.*?)(?: \(([^()]*)\))?(?: <!--.*-->)?$')

STYLE = """
:root{--bg:#f7f6f2;--ink:#24312a;--muted:#5b6a61;--line:#d9dfd9;--card:#fff;--link:#225d48;--accent:#aa7409;--soft:#eef1ec}
@media (prefers-color-scheme:dark){:root{--bg:#151a17;--ink:#e6ebe7;--muted:#9aa89f;--line:#2c3630;--card:#1c2320;--link:#7fc9a9;--accent:#e0a93a;--soft:#202824}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,sans-serif}
main{max-width:760px;margin:auto;padding:40px 16px 56px}
.kicker{font-size:.75em;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0}
h1{font:600 1.9em/1.2 Georgia,"Times New Roman",serif;margin:.2em 0 .5em}
.success{color:var(--muted);margin:0}
h2{font-size:.8em;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:2.6em 0 .8em;
  border-top:1px solid var(--line);padding-top:1.2em}
h3{font-size:1em;margin:0 0 .3em}
ul{margin:.3em 0 0;padding-left:1.2em}
li{margin:.25em 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:12px 0}
.route{font-size:.85em;color:var(--muted);margin:0 0 .6em;overflow-wrap:anywhere}
.label{font-size:.75em;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:.9em 0 .1em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.stat{background:var(--soft);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-size:1.5em;line-height:1.2}
.stat span{font-size:.85em;color:var(--muted)}
.never li::marker{content:"× ";color:var(--accent)}
.rev{display:flex;gap:12px;border-left:3px solid var(--accent);padding:2px 0 2px 12px;margin:10px 0}
.rev time{color:var(--muted);font-size:.85em;white-space:nowrap}
.rev small{display:block;color:var(--muted);overflow-wrap:anywhere}
details{margin-top:2.4em;font-size:.85em}
summary{cursor:pointer;color:var(--muted)}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto;font-size:.85em}
a{color:var(--link);overflow-wrap:anywhere}
a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
footer{border-top:1px solid var(--line);margin-top:3em;padding-top:1em;font-size:.85em;color:var(--muted)}
"""


def e(value):
    return escape(str(value), quote=True)


def items(values):
    values = [v for v in values if v]
    return '<ul>' + ''.join(f'<li>{e(v)}</li>' for v in values) + '</ul>' if values else ''


def link(url):
    return f'<a href="{e(url)}">{e(url)}</a>'


def minutes(value):
    return f'{value:g} minute' + ('' if value == 1 else 's')


def route(thread):
    access = thread['access']
    if access['type'] == 'browser':
        return 'Isolated browser session you sign into yourself'
    if access['type'] == 'feed':
        return 'Public RSS or Atom feed, read without a browser or sign-in'
    return f'Connector {access["tool_namespace"]}, through access the service offers'


def source_card(thread, contract):
    selection = thread['selection']
    rows = []
    for surface in thread['surfaces']:
        where = (thread.get('feed_urls', {}).get(surface) or thread.get('entry_urls', {}).get(surface))
        scope = thread.get('targets', {}).get(surface, {}).get('scope')
        depth = thread.get('collection', {}).get(surface, {})
        note = f' Looks at up to {depth["max_items"]} items.' if depth.get('max_items') else (
            ' Reads a sample.' if depth.get('mode') == 'sample' else '')
        detail = ' — '.join(x for x in (e(scope) if scope else '', link(where) if where else '') if x)
        rows.append(f'<li><strong>{e(surface)}</strong>{": " + detail if detail else ""}{e(note)}</li>')
    other = {k: v for k, v in selection.items() if k not in {'include', 'exclude'} and isinstance(v, str)}
    ceiling = contract['composition'].get('max_items_by_thread', {}).get(thread['id'])
    parts = [f'<div class="card"><h3>{e(thread["service"])} · {e(thread["id"])}</h3>',
             f'<p class="route">{e(route(thread))}. '
             + ('Public posts.' if thread.get('content') == 'public_posts' else 'Private communication.')
             + (f' Expected sign-in: {e(thread["expected_account"])}.' if thread.get('expected_account') else '')
             + '</p>', '<p class="label">Surfaces</p><ul>' + ''.join(rows) + '</ul>']
    if thread.get('excluded_surfaces'):
        parts.append('<p class="label">Never opened</p>' + items(thread['excluded_surfaces']))
    if selection.get('include'):
        parts.append(f'<p class="label">What counts here</p><p>{e(selection["include"])}</p>')
    if selection.get('exclude'):
        parts.append('<p class="label">Left out here</p>' + items(selection['exclude']))
    if other:
        parts.append('<p class="label">Other rules</p>' + items(f'{k.replace("_", " ").capitalize()}: {v}'
                                                              for k, v in other.items()))
    if ceiling:
        parts.append(f'<p class="label">Reaches you</p><p>At most {ceiling} item{"s" if ceiling != 1 else ""} per briefing.</p>')
    return ''.join(parts) + '</div>'


def revisions(contract, changelog):
    entries = []
    for line in (changelog or '').splitlines():
        match = CHANGE.match(line.strip())
        if match:
            entries.append(match.groups())
    if not entries:
        return f'<p>Revision {contract["revision"]}. No changelog was found beside this contract.</p>'
    rows = []
    for date, revision, reason, paths in reversed(entries):
        changed = f'<small>Changed: {e(paths)}</small>' if paths else ''
        rows.append(f'<div class="rev"><time datetime="{e(date)}">{e(date)}</time>'
                    f'<div>Revision {e(revision)}: {e(reason)}{changed}</div></div>')
    return ''.join(rows)


def render(contract, changelog=None):
    contract = contract_api.validate(contract)
    intent, limits, composition = contract['intent'], contract['run_limits'], contract['composition']
    topics = [x for x in intent.get('excluded', []) if x not in TOKENS]
    guarantees = [TOKENS[x] for x in intent.get('excluded', []) if x in TOKENS]
    counts = [f'<div class="stat"><b>{minutes(limits["elapsed_minutes"])}</b><span>longest a check may run</span></div>']
    if limits.get('items_per_surface'):
        counts.append(f'<div class="stat"><b>{limits["items_per_surface"]} items</b><span>looked at per source area, at most</span></div>')
    if composition.get('target_reading_minutes'):
        counts.append(f'<div class="stat"><b>{minutes(composition["target_reading_minutes"])}</b><span>to read the briefing</span></div>')
    counts.append('<div class="stat"><b>Can be empty</b><span>when nothing qualifies</span></div>')
    services = limits.get('service_minutes', {})
    surprise = contract.get('serendipity', {})
    if surprise.get('enabled') and surprise.get('max_items', 0) > 0:
        surprise_html = (f'<p>Up to {surprise["max_items"]} labelled item{"s" if surprise["max_items"] != 1 else ""} '
                         'from outside your interests, only from ' + e(', '.join(surprise['sources'])) + '.</p>'
                         + items(surprise.get('test', [])))
    else:
        surprise_html = '<p>Off. Nothing outside your stated interests is shown.</p>'
    provider = contract['memory_context']['provider']
    where = 'in local files on this computer' if provider == 'local' else 'in your Supermemory space'
    interface = {'agent_summary': 'in the conversation', 'briefing_html': 'as a local HTML page',
                 'discovery_html': 'as a local HTML page'}[composition['interface']]
    body = [
        f'<p class="kicker">Attention contract · {e(contract["id"])} · revision {contract["revision"]}</p>',
        f'<h1>{e(intent["purpose"])}</h1>', f'<p class="success">{e(intent["success"])}</p>',
        '<h2>What counts</h2>',
        items(i['focus'] for i in intent.get('interests', [])) or '<p>No interests listed; each source says what counts.</p>',
        '<h2>What is left out everywhere</h2>', items(topics) or '<p>Nothing beyond each source’s own rules.</p>',
        '<h2>Where it looks</h2>', ''.join(source_card(t, contract) for t in contract['coverage_threads']),
        '<h2>When it stops</h2>', '<div class="grid">' + ''.join(counts) + '</div>',
        items(f'{service}: up to {minutes(value)}' for service, value in services.items()),
        '<h2>Surprises</h2>', surprise_html,
        '<h2>What it remembers</h2>',
        f'<p>Only which items it has already shown you, stored {where}, so they are not repeated. '
        'Not what you read, clicked or skipped. Your preferences change only when you revise this contract.</p>',
        '<h2>What it never does</h2>',
        '<ul class="never">' + ''.join(f'<li>{e(g)}</li>' for g in guarantees + [
            'Learn from your clicks or change these rules by itself.',
            'Switch to another route when a source is unavailable.',
            'Run on a schedule. A check runs only when you ask.']) + '</ul>',
        '<h2>Revisions</h2>', revisions(contract, changelog),
        '<details><summary>The exact contract</summary><pre>'
        + e(json.dumps(contract, indent=2, ensure_ascii=False)) + '</pre></details>',
        f'<footer><p>Briefings arrive {interface}. To change anything here, ask Attention Diet to tune this '
        'contract, for example: “leave out event announcements”.</p>'
        f'<p>Contract digest {e(contract_api.digest(contract)[:12])}.</p></footer>']
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            f'<title>Your attention contract · {e(contract["id"])}</title><style>{STYLE}</style></head>'
            '<body><main>' + '\n'.join(body) + '</main></body></html>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    show = sub.add_parser('render', help='Write the contract as a local HTML page.')
    show.add_argument('--id')
    show.add_argument('--contract')
    show.add_argument('--out', required=True, help='Absolute path of the HTML file to write.')
    args = parser.parse_args()
    try:
        path = Path(args.contract).expanduser() if args.contract else contract_api.resolve(args.id)
        out = Path(args.out).expanduser()
        require(out.is_absolute() and out.suffix == '.html', 'Output must be an absolute .html path')
        changelog = path.parent / 'changelog.md'
        page = render(contract_api.memory.read_json(path), changelog.read_text() if changelog.is_file() else None)
        out.parent.mkdir(parents=True, exist_ok=True)
        contract_api.write_private(out, page)
        print(json.dumps({'written': str(out), 'contract': str(path)}))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
