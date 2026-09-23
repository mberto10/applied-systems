#!/usr/bin/env python3
"""Validate a selected-content record, render it, or derive scoped memory payloads."""
import argparse
from html import escape
import hashlib
import json
from pathlib import Path
import re
from string import Template
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import contract as contract_api  # noqa: E402
import surface_coverage  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
require, nonempty = contract_api.require, contract_api.nonempty
INTERFACES = {'agent_summary', 'briefing_html', 'discovery_html'}


def plain_url(value):
    require(nonempty(value), 'A source URL is required')
    url = urlsplit(value)
    require(url.scheme in {'http', 'https'} and url.hostname and not url.username and not url.password
            and not any(c.isspace() or ord(c) < 32 for c in value), 'Unsafe source URL')


def validate(contract, record):
    contract_api.validate(contract)
    contract_api.memory.schema_validation.validate(record, 'selection.schema.json')
    return validate_content(contract, record)


def validate_content(contract, record):
    require(record['contract_id'] == contract['id'] and record['contract_revision'] == contract['revision'],
            'Selection belongs to another contract or revision')
    threads = {t['id']: t for t in contract['coverage_threads']}
    expected = {(t['id'], s) for t in threads.values() for s in t['surfaces']}
    coverage = {}
    for row in record['coverage']:
        key = (row['thread_id'], row['surface'])
        require(key in expected and key not in coverage, 'Unknown or duplicate coverage surface')
        modern = record['schema_version'] == 'attention-selection/1.2'
        extra = {'boundary', 'exhaustion', 'overrun_count', 'within_allowance_count',
                 'unreadable_count', 'has_unreadable_content'}
        if not modern:
            require(not extra.intersection(row) and row['stop_reason'] not in {'retrieval_stalled', 'window_overrun'},
                    'New coverage fields require attention-selection/1.2')
        else:
            require(extra <= set(row), 'Structured coverage fields are required for attention-selection/1.2')
            require(row['within_allowance_count'] + row['overrun_count'] == row['inspected_count'],
                    'Coverage accounting must include every inspected identity')
            require(row['unreadable_count'] <= row['inspected_count'], 'Unreadable count exceeds inspections')
            if row['boundary'] == 'exhausted_results':
                require(row['more_available'] is False and row['exhaustion'] is not None,
                        'An exhaustive boundary needs structured exhaustion evidence')
                surface_coverage.exhaustion_evidence(row, row['inspected_count'])
            if row['status'] == 'checked':
                require(not row['has_unreadable_content'] and not row['overrun_count']
                        and row['boundary'] in {'exhausted_results', 'verified_prior_range'},
                        'Checked coverage needs a verified boundary without unreadable content or overrun')
            if row['stop_reason'] == 'exhausted_results':
                require(row['boundary'] == 'exhausted_results', 'Exhaustion needs a verified boundary')
        if row['status'] == 'checked':
            require(row['stop_reason'] in {'exhausted_results', 'novelty_boundary'}, 'A ceiling or sample is partial coverage')
            require(threads[row['thread_id']].get('collection', {}).get(row['surface'], {}).get('mode') != 'sample',
                    'An exhausted sample is still partial coverage')
        if row['stop_reason'] == 'exhausted_results':
            require(row['more_available'] is False, 'Exhausted results cannot have more available')
        if row['status'] in {'unavailable', 'not_checked'}:
            require(row['inspected_count'] == 0, 'Inspected items need checked or partial coverage')
        if row['status'] == 'unavailable':
            require(row['stop_reason'] == 'access_failure', 'Unavailable coverage needs an access failure')
        if row['status'] == 'not_checked':
            require(row['stop_reason'] == 'not_checked', 'Unchecked coverage needs a not_checked reason')
        coverage[key] = row
    require(set(coverage) == expected, 'Every configured surface needs coverage, including unchecked surfaces')
    ids, versions, counts, surprise_count = set(), set(), {}, 0
    account_services = {}
    for entry in record['entries']:
        require(entry['id'] not in ids, 'Duplicate entry id')
        ids.add(entry['id'])
        key = (entry['thread_id'], entry['surface'])
        require(key in coverage and coverage[key]['status'] in {'checked', 'partial'}, 'Entry has no inspected source surface')
        require(coverage[key]['inspected_count'] > 0, 'Entry has no inspected items')
        thread = threads[entry['thread_id']]
        require(entry['section'] in contract['composition']['sections'] and entry['section'] != 'overview', 'Unknown entry section')
        require(entry['account_key'] is not None or thread.get('content') == 'public_posts', 'Private entries require an identified account')
        if entry['account_key'] is not None:
            prior = account_services.setdefault(entry['account_key'], thread['service'])
            require(prior == thread['service'], 'Account keys must be scoped to one service')
        if entry['url'] is not None:
            plain_url(entry['url'])
        if 'slot' in entry or 'topic' in entry:
            block = contract.get('serendipity', {})
            require(block.get('enabled') and '/'.join(key) in block['sources'], 'Surprise slot not authorized for this surface')
            surprise_count += 1
        else:
            counts[thread['id']] = counts.get(thread['id'], 0) + 1
        for item in entry['items']:
            require(item['service'] == thread['service'], 'Item belongs to another service')
            version = (entry['account_key'], contract_api.memory.item_key(item))
            require(version not in versions, 'An item version appears in multiple entries')
            versions.add(version)
    for thread_id, ceiling in contract['composition'].get('max_items_by_thread', {}).items():
        require(counts.get(thread_id, 0) <= ceiling, 'Output exceeds thread ceiling')
    require(surprise_count <= contract.get('serendipity', {}).get('max_items', 0), 'Output exceeds surprise ceiling')
    return record


def coverage_lines(contract, record):
    """Compact scope record kept in briefing memory; the reader gets `briefing_notices` instead."""
    threads = {t['id']: t for t in contract['coverage_threads']}
    lines = []
    for row in record['coverage']:
        policy = threads[row['thread_id']].get('collection', {}).get(row['surface'], {})
        sampled = 'sampled; ' if policy.get('mode') == 'sample' else ''
        more = 'unknown' if row['more_available'] is None else str(row['more_available']).lower()
        lines.append(f"{row['thread_id']}/{row['surface']}: {sampled}{row['status']}; "
                     f"{row['inspected_count']} inspected; more={more}; {row['stop_reason']}: {row['evidence']}")
        warnings = coverage_notices(row)
        if warnings:
            lines[-1] += ' ' + ' '.join(warnings)
    return lines


def coverage_notices(row):
    notices = list(row.get('notices', []))
    if row.get('read_state_effect') == 'unknown':
        notices.append(f"{row['thread_id']}/{row['surface']}: automatic selection occurred; its effect on read state is unknown.")
    return list(dict.fromkeys(notices))


def label(value):
    text = value.replace('_', ' ')
    return text[:1].upper() + text[1:]


def source_label(thread, surface):
    return thread['service'] + ' · ' + surface.replace('_', ' ')


HISTORY_WARNINGS = {
    'Could not read a local summary', 'Local history is unavailable',
    'Provider history was not retrieved', 'Provider history retrieval is incomplete',
    'A provider document is not fully available', 'A history document could not be validated',
    'An earlier referenced summary is missing',
}


def reader_warning(text):
    """Translate known diagnostics; preserve unfamiliar notices that may require action."""
    text = ' '.join(text.split())
    if text.rstrip('.') in HISTORY_WARNINGS:
        return 'Earlier briefings were not fully available, so repeat filtering may be incomplete.'
    if text.rstrip('.') in {
        'Some known items have incompatible or undocumented fingerprint methods; novelty is uncertain',
        'Some known items have changed captures without reliable evidence of a new event; novelty is uncertain',
    }:
        return 'Some items could not be reliably compared with earlier briefings and were withheld.'
    if text.startswith('Briefing memory could not be saved ('):
        return 'Briefing memory could not be saved; later checks may repeat these items.'
    if text in {
        'The stored document is not the prepared briefing artifact; briefing memory was not saved correctly.',
        'Stored briefing fields differ from the prepared artifact; briefing memory was not saved correctly.',
    }:
        return 'Briefing memory was not saved correctly; later checks may repeat these items.'
    if text in {
        'One identified card had incomplete text and was withheld from selection.',
        'A card could not be identified; reported identity counts are a lower bound.',
    }:
        return None  # The affected source's partial coverage is disclosed below.
    if text.startswith('Inspection exceeded the configured ') and 'ceiling by ' in text:
        return 'Collection exceeded a configured inspection limit.'
    return text


def coverage_description(thread, row):
    name = row['surface'].replace('_', ' ')
    count = row['inspected_count']
    sample = thread.get('collection', {}).get(row['surface'], {}).get('mode') == 'sample'
    unit = 'posts' if thread.get('content') == 'public_posts' else 'previews' if row['surface'] == 'messages' else 'items'
    reason = row['stop_reason']
    if row['status'] == 'unavailable':
        return name + ' unavailable'
    if row['status'] == 'not_checked':
        return name + ' not checked'
    if row.get('overrun_count', 0):
        detail = (f"{row['within_allowance_count']} {unit} within the limit, "
                  f"{row['overrun_count']} extra observed and excluded from selection")
    elif sample:
        detail = f'{count} {unit} sampled'
    else:
        detail = f'{count} {unit} checked'
    if reason == 'retrieval_stalled':
        detail += '; further retrieval produced no new distinct items'
    elif reason == 'source_limit' and not row.get('has_unreadable_content'):
        detail += '; source access limited further checking'
    elif reason == 'access_failure':
        detail += '; access failed before checking finished'
    elif reason == 'time_ceiling':
        detail += '; time limit reached'
    elif reason == 'item_ceiling' and not row.get('overrun_count', 0):
        detail += '; inspection limit reached'
    elif reason == 'agent_stopped_early':
        detail += '; end of the list not verified'
    elif row.get('boundary') == 'exhausted_results' or reason == 'exhausted_results':
        detail += '; end of the list verified'
    elif reason == 'novelty_boundary':
        detail += '; previously covered range reached'
    if row.get('has_unreadable_content'):
        detail += '; some previews lacked enough content to assess'
    return name + ': ' + detail


def briefing_notices(contract, record):
    """Reader-facing limits only; never render coverage evidence or diagnostic rows."""
    threads = {t['id']: t for t in contract['coverage_threads']}
    services = {}
    for row in record['coverage']:
        services.setdefault(threads[row['thread_id']]['service'], []).append(row)
    notices = []
    for service, rows in services.items():
        name = {'linkedin': 'LinkedIn', 'x': 'X'}.get(service, label(service))
        if all(r['status'] == 'unavailable' for r in rows):
            notices.append(f'{name} was unavailable.')
        elif all(r['status'] == 'not_checked' for r in rows):
            notices.append(f'{name} was not checked.')
        else:
            descriptions = [coverage_description(threads[r['thread_id']], r) for r in rows
                            if r['status'] != 'checked' or record['schema_version'] == 'attention-selection/1.2']
            if descriptions:
                notices.append(name + ' — ' + '; '.join(descriptions) + '.')
        if any(r.get('read_state_effect') == 'unknown' or re.search(
                r'(read[ -]?state.*unknown|unknown.*read[ -]?state)', r['evidence'], re.I) for r in rows):
            notices.append(f'{name} automatically opened an item; its effect on read state is unknown.')
    # Surface notices must be reader-facing too. Unknown warnings survive: do not
    # suppress an account mismatch or sign-in instruction by guessing its meaning.
    raw = record['notices'] + [n for row in record['coverage'] for n in row.get('notices', [])
        if not (row.get('overrun_count', 0) and n.startswith('Inspection exceeded the configured '))]
    notices.extend(reader_warning(n) for n in raw)
    if any(e['account_key'] is None for e in record['entries']):
        notices.append('Some public items have no identified account; their briefing history cannot be saved.')
    result, seen = [], set()
    overview = ' '.join(record['overview'].split()).casefold()
    for notice in notices:
        if not notice:
            continue
        notice = ' '.join(notice.split())
        if notice[-1] not in '.!?':
            notice += '.'
        key = notice.casefold()
        if key not in seen and key not in overview:
            result.append(notice)
            seen.add(key)
    return result


def md(value):
    # Source text is data, never Markdown/HTML supplied by a page.
    text = escape(' '.join(value.split()), quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', text)


def data_island(value):
    """JSON for a `<script type="application/json">` block: no sequence can close the element."""
    text = json.dumps(value, ensure_ascii=False)
    for char in '&<>  ':
        text = text.replace(char, '\\u%04x' % ord(char))
    return text


CSP = re.compile(r"<meta[^>]+Content-Security-Policy[^>]+default-src 'none'", re.I)


def render_template(contract, interface, values, contract_dir=None, template_path=None):
    if template_path is not None:
        path = Path(template_path).expanduser()  # Preview of a custom view before it enters a contract.
    elif interface == contract['composition']['interface']:
        base = ROOT if contract['composition']['template_path_base'] == 'plugin_root' else contract_dir
        require(base is not None, 'Contract directory is needed to resolve template')
        path = Path(base) / contract['composition']['template']
    else:
        path = ROOT / ('interfaces/agent-summary/template.md' if interface == 'agent_summary'
                       else 'interfaces/html/template.html')
    try:
        template = Template(path.read_text())
    except OSError as error:
        raise ValueError(f'Cannot read output template {path}: {error.strerror}') from None
    names = set()
    for match in Template.pattern.finditer(template.template):
        require(match.group('invalid') is None, 'Invalid template placeholder; use $$ for a literal dollar sign')
        name = match.group('named') or match.group('braced')
        if name:
            names.add(name)
    # A view built from $data draws its own entries, but it may never drop the notices.
    required = {'title', 'notices'} | ({'data'} if 'data' in names else {'overview', 'content'})
    require(required <= names, 'Output template must include: ' + ', '.join(sorted(required - names)))
    require(names <= set(values), 'Unknown output template placeholders: ' + ', '.join(sorted(names - set(values))))
    if interface != 'agent_summary' or 'data' in names:
        # Every HTML view stays local and offline: even a template bug cannot send source content anywhere.
        require(CSP.search(template.template),
                "An HTML template needs a Content-Security-Policy meta tag with default-src 'none'")
    return template.substitute(values).strip() + '\n'


def render(contract, record, interface=None, contract_dir=None, *, template_path=None, _validated=False):
    if not _validated:
        validate(contract, record)
    interface = interface or contract['composition']['interface']
    require(interface in INTERFACES, 'Unsupported output interface')
    threads = {t['id']: t for t in contract['coverage_threads']}
    groups = [(section, [e for e in record['entries'] if e['section'] == section and 'slot' not in e])
              for section in contract['composition']['sections'] if section != 'overview']
    surprise = [e for e in record['entries'] if e.get('slot') == 'serendipity']
    if surprise:
        groups.append(('Outside your interests', surprise))
    groups = [(label(section), entries) for section, entries in groups if entries]
    notices = briefing_notices(contract, record)
    count = len(record['entries'])
    scope = record['coverage']
    visited = sum(row['status'] in {'checked', 'partial'} for row in scope)
    meta = (f"{count} selected {'item' if count == 1 else 'items'} · {visited} of {len(scope)} "
            f"source {'area' if len(scope) == 1 else 'areas'} visited")

    def missing_link(e):
        return 'Source: ' + source_label(threads[e['thread_id']], e['surface']) + '. No direct source link provided.'

    if interface == 'agent_summary':
        parts = []
        for section, entries in groups:
            parts.append('**' + md(section) + '**')
            for e in entries:
                if e['url'] is not None:
                    url = e['url'].replace('<', '%3C').replace('>', '%3E')
                    source = f'[Source](<{url}>)'
                else:
                    source = md(missing_link(e))
                body = ' '.join(md(text) for text in [e['summary'], e['why'], *e.get('caveats', [])])
                parts.append(f"- **{md(e['title'])}:** {body} {source}")
        return render_template(contract, interface, {
            'title': md(record['title']), 'overview': md(record['overview']), 'meta': md(meta),
            'content': '\n\n'.join(parts), 'notices': ' '.join(md(v) for v in notices)}, contract_dir, template_path)
    sections = []
    for section, entries in groups:
        cards = []
        for e in entries:
            origin = escape(source_label(threads[e['thread_id']], e['surface']))
            source = (f'<p class="source"><a href="{escape(e["url"], quote=True)}">Open source</a> <span>{origin}</span></p>'
                      if e['url'] is not None else f'<p class="source">{escape(missing_link(e))}</p>')
            cards.append(f'<article><h3>{escape(e["title"])}</h3><p class="summary">{escape(e["summary"])}</p>'
                         f'<p class="why">{escape(e["why"])}</p>'
                         + ''.join(f'<p class="caveat">{escape(c)}</p>' for c in e.get('caveats', [])) + f'{source}</article>')
        sections.append(f'<section><h2>{escape(section)}</h2><div class="entries">' + ''.join(cards) + '</div></section>')
    # The same selection as data, for a custom or generated view. Text only; a template must never treat it as HTML.
    data = {'title': record['title'], 'overview': record['overview'], 'created_at': record['created_at'],
            'meta': meta, 'notices': notices,
            'sections': [{'name': section, 'entries': [
                {'title': e['title'], 'summary': e['summary'], 'why': e['why'], 'caveats': e.get('caveats', []),
                 'url': e['url'], 'source': source_label(threads[e['thread_id']], e['surface']),
                 'surprise': e.get('slot') == 'serendipity'} for e in entries]} for section, entries in groups],
            'coverage': [{'source': source_label(threads[row['thread_id']], row['surface']), 'status': row['status'],
                          'inspected_count': row['inspected_count'], 'more_available': row['more_available'],
                          'stop_reason': row['stop_reason'],
                          **{k: row[k] for k in ('boundary', 'overrun_count',
                              'within_allowance_count', 'unreadable_count', 'has_unreadable_content') if k in row}}
                         for row in record['coverage']]}
    return render_template(contract, interface, {
        'title': escape(record['title']), 'overview': escape(record['overview']), 'meta': escape(meta),
        'layout': 'discovery' if interface == 'discovery_html' else 'briefing', 'content': ''.join(sections),
        'notices': ''.join('<p>' + escape(v) + '</p>' for v in notices), 'data': data_island(data)},
        contract_dir, template_path)


def memory_payloads(contract, record, *, _validated=False):
    if not _validated:
        validate(contract, record)
    groups = {}
    threads = {t['id']: t for t in contract['coverage_threads']}
    for e in record['entries']:
        if e['account_key'] is not None:
            groups.setdefault((threads[e['thread_id']]['service'], e['account_key']), []).append(e)
    result = []
    lines = coverage_lines(contract, record)
    for (service, account), entries in groups.items():
        items = []
        for entry in entries:
            for item in entry['items']:
                extra = {k: entry[k] for k in ('slot', 'topic') if k in entry}
                items.append({**item, **extra})
        entry_threads = {e['thread_id'] for e in entries}
        scope = [line for line, row in zip(lines, record['coverage']) if row['thread_id'] in entry_threads]
        version = 'briefing-' + hashlib.sha256(json.dumps([record['run_id'], service, account]).encode()).hexdigest()[:32]
        # A short inventory, not an unqualified paraphrase of every source claim.
        summary = 'Included source items: ' + '; '.join(e['title'] for e in entries) + '.'
        qualifications = [text for e in entries for text in [e['why'], *e.get('caveats', [])]]
        summary += ' Context and qualifications: ' + ' '.join(dict.fromkeys(qualifications))
        require(len(summary) <= 4000, 'Memory summary exceeds 4000 characters; shorten titles/context without dropping qualifications')
        payload = {'version_id': version, 'items': items, 'coverage': '\n'.join(scope), 'summary': summary}
        result.append({'service': service, 'account_key': account, 'payload': payload})
    return result


def finalize(contract, record, contract_dir=None):
    """One validation and one immutable selection for delivery and memory."""
    validate(contract, record)
    return {'rendered': render(contract, record, contract_dir=contract_dir, _validated=True),
            'memory_payloads': memory_payloads(contract, record, _validated=True)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'render', 'memory-payloads', 'finalize'])
    parser.add_argument('--contract', required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--interface', choices=sorted(INTERFACES), help='Preview another interface using the same selection')
    parser.add_argument('--template', help='Render only: preview this template file instead of the configured one')
    parser.add_argument('--out', help='Optional private output file')
    args = parser.parse_args()
    try:
        contract_path = Path(args.contract).expanduser()
        contract = json.loads(contract_path.read_text())
        record = json.load(sys.stdin) if args.input == '-' else json.loads(Path(args.input).read_text())
        if args.command == 'render':
            output = render(contract, record, args.interface, contract_path.parent, template_path=args.template)
        else:
            if args.command == 'validate':
                validate(contract, record)
                value = {'valid': True, 'entries': len(record['entries'])}
            elif args.command == 'finalize':
                value = finalize(contract, record, contract_path.parent)
            else:
                value = memory_payloads(contract, record)
            output = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            contract_api.write_private(Path(args.out).expanduser(), output)
        else:
            print(output, end='')
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
