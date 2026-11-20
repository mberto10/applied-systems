#!/usr/bin/env python3
"""Collect public posts through treg (treg.to), one catalog call per surface, bounded before any text leaves.

The catalog id and query come from the contract, never from the caller, so this helper cannot call a
tool the contract did not name. treg relays each call to a data vendor and bills the treg account
signed in with the `treg` CLI; this helper holds no credentials. Every row is normalized into the
same entry shape as the feed helper: a stable identifier, a deterministic comparison basis, and
engagement counts kept outside the basis so a changing like count never makes a post look new.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import contract as contract_api  # noqa: E402
import item_identity as identity  # noqa: E402

require = contract_api.require
ACCOUNT_KEY = 'treg:public'
TEXT_LIMIT = 1000  # Fixed, so the comparison basis of an unchanged post is identical across runs.
TIMEOUT_SECONDS = 60
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

# Field names vendors use for the same thing. Dotted paths reach into nested objects.
FIELDS = {
    'id': 'id_str id rest_id aweme_id video_id post_id objectID',
    'url': 'permalink share_url url link hn_url web_url',  # Reddit: the thread, not the linked image
    'text': 'full_text text title desc description selftext caption content story_text tagline',
    'author': 'authorUsername author.userName author.username author.unique_id author.screen_name user.screen_name channel.name '
              'author.name author username screen_name',
    'created': 'created_at createdAt created_utc createdUtc create_time createTime published_at '
               'publishedAt timestamp time',
    'likes': 'favorite_count likeCount like_count likes ups score points statistics.digg_count digg_count',
    'comments': 'reply_count replyCount num_comments comment_count comments statistics.comment_count',
    'shares': 'retweet_count retweetCount reposts share_count statistics.share_count',
    'views': 'view_count viewCount views play_count statistics.play_count',
}
WRAPPERS = ('aweme_info', 'data', 'legacy', 'tweet', 'post')  # vendors that wrap each row once more
PLACEHOLDER = re.compile(r'\{(since_unix|since_iso|since_date)\}')


def _get(row, path):
    value = row
    for part in path.split('.'):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def first(row, field):
    for path in FIELDS[field].split():
        value = _get(row, path)
        if value not in (None, '', [], {}):
            return value
    return None


def count(value):
    """A number from 1234, '1,234', '1.2K' or '3M views'; 0 when nothing numeric is there."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r'([\d][\d.,]*)\s*([kmb])?', str(value or '').lower())
    if not match:
        return 0
    number = float(match.group(1).replace(',', '') or 0)
    return int(number * {'k': 1e3, 'm': 1e6, 'b': 1e9}.get(match.group(2) or '', 1))


def moment(value):
    """An absolute UTC time from epoch seconds or milliseconds, ISO 8601 or Twitter's format; else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        seconds = float(value)
        seconds = seconds / 1000 if seconds > 1e12 else seconds
        return datetime.fromtimestamp(seconds, timezone.utc)
    text = str(value).strip()
    for parse in (lambda v: datetime.fromisoformat(v.replace('Z', '+00:00')),
                  lambda v: datetime.strptime(v, '%a %b %d %H:%M:%S %z %Y')):
        try:
            parsed = parse(text)
        except ValueError:
            continue
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None  # no zone, no absolute time
    return None


def rows(document):
    """The largest list of objects anywhere in a vendor answer, each row unwrapped once."""
    best = []

    def walk(node):
        nonlocal best
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            objects = [item for item in node if isinstance(item, dict)]
            if len(objects) > len(best):
                best = objects
            for item in objects:
                walk(item)

    walk(document)
    out = []
    for row in best:
        inner = next((row[key] for key in WRAPPERS if isinstance(row.get(key), dict)), None)
        out.append({**row, **inner} if inner else row)
    return out


def _https(value):
    parts = urlsplit(value or '')
    return value if parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password else None


def _post_url(url):
    if isinstance(url, str) and url.startswith('/r/'):
        url = 'https://www.reddit.com' + url
    if isinstance(url, str) and re.search(r'(^|\.)(x|twitter|tiktok)\.com/', url):
        url = url.split('?')[0]  # tracking parameters are not part of a post's identity
    return _https(url.rstrip('/')) if isinstance(url, str) else None


def entry(row, source_label, catalog_id):
    """One normalized entry, or None when the row has neither a post link nor a vendor id."""
    url = _post_url(first(row, 'url'))
    raw_id = first(row, 'id')
    if not url and raw_id is None:
        return None
    identifier = identity.canonical_identifier(url or f'{catalog_id}:{raw_id}')
    text = ' '.join(str(first(row, 'text') or '').split())
    clipped = text[:TEXT_LIMIT].rstrip() + '…' if len(text) > TEXT_LIMIT else text
    author = first(row, 'author')
    author = author if isinstance(author, str) and author.strip() else None
    created = moment(first(row, 'created'))
    sender = ('@' + author.lstrip('@')) if author else source_label
    basis = {'sender': sender, 'text': clipped or identifier}
    if created:
        basis['occurred_at'] = created.isoformat()
    engagement = {name: count(first(row, name)) for name in ('likes', 'comments', 'shares', 'views')}
    return {'identifier': identifier, 'url': url, 'author': author, 'published': created.isoformat() if created else None,
            'text': clipped, 'text_truncated': len(text) > TEXT_LIMIT, 'engagement': engagement, 'basis': basis}


def window_values(window_hours, now):
    since = now - window_hours * 3600
    return {'since_unix': str(int(since)),
            'since_iso': datetime.fromtimestamp(since, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'since_date': datetime.fromtimestamp(since, timezone.utc).strftime('%Y-%m-%d')}


def fill(value, values):
    """Replace window placeholders in every string of a query or body; other values pass unchanged."""
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: values[m.group(1)], value)
    if isinstance(value, dict):
        return {key: fill(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [fill(item, values) for item in value]
    return value


def resolve_query(query, window_hours, now):
    values = window_values(window_hours, now)
    return {key: str(fill(value, values)) for key, value in query.items()}


def treg_binary():
    found = os.environ.get('TREG_BIN') or shutil.which('treg') or str(Path('~/.local/bin/treg').expanduser())
    require(Path(found).is_file(), 'The treg CLI is not installed; see https://treg.to/llms.txt and sign in with treg login')
    return found


def run_treg(argv):
    """Run the treg CLI without a shell; return its parsed JSON."""
    done = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
    require(len(done.stdout) <= MAX_OUTPUT_BYTES, 'treg answer exceeds 8 MB; not read')
    if done.returncode != 0:
        message = (done.stderr or done.stdout).decode('utf-8', 'replace').strip().splitlines()
        raise ValueError('treg call failed: ' + (message[-1] if message else f'exit {done.returncode}'))
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise ValueError('treg answered with something other than JSON') from None


def call_argv(binary, call):
    argv = [binary, '--json', 'call', call['catalog_id']]
    if call.get('method', 'GET') != 'GET':
        argv += ['--method', call['method'], '--data', json.dumps(call['body'], ensure_ascii=False)]
    for key, value in call['query'].items():
        argv += ['--query', f'{key}={value}']
    return argv


def fetch(contract, thread_id, surface, max_items, seen=(), runner=None, now=None):
    """One bounded read: at most max_items unseen entries inside the surface's window, best first as the vendor ranked them."""
    thread = next((t for t in contract['coverage_threads'] if t['id'] == thread_id), None)
    require(thread is not None and thread['access']['type'] == 'treg', 'Thread is not a configured treg source')
    require(surface in thread['surfaces'], 'Surface is not configured for this treg source')
    require(type(max_items) is int and max_items >= 0, 'max_items must be a nonnegative integer, the window limit')
    spec = thread['treg_calls'][surface]
    now = time.time() if now is None else now
    call = {'catalog_id': spec['catalog_id'], 'method': spec.get('method', 'GET'),
            'body': fill(spec.get('body', {}), window_values(spec['window_hours'], now)),
            'query': resolve_query(spec.get('query', {}), spec['window_hours'], now)}
    answer = (runner or run_treg)(call_argv(treg_binary() if runner is None else 'treg', call))
    payload = answer.get('result', answer) if isinstance(answer, dict) else answer
    charged = (answer.get('_treg') or {}).get('charged_micro') if isinstance(answer, dict) else None
    label = spec.get('label') or thread['service']
    entries, identified, unidentified, outside, undated = [], 0, 0, 0, 0
    keys = set(identity.count_key(i) for i in identity.distinct_identifiers(list(seen)))
    cutoff = now - spec['window_hours'] * 3600
    for row in rows(payload):
        item = entry(row, label, spec['catalog_id'])
        if item is None:
            unidentified += 1  # counted, never given a made-up identity
            continue
        identified += 1
        if item['published'] and datetime.fromisoformat(item['published']).timestamp() < cutoff:
            outside += 1
            continue
        undated += item['published'] is None
        key = identity.count_key(item['identifier'])
        if key not in keys:  # also drops a row the vendor listed twice
            keys.add(key)
            entries.append(item)
    batch, rest = entries[:max_items], max(0, len(entries) - max_items)
    return {'account_key': ACCOUNT_KEY, 'thread_id': thread_id, 'surface': surface, 'catalog_id': spec['catalog_id'],
            'query': call['query'] or call['body'], 'window_hours': spec['window_hours'], 'entries': batch,
            'response_entries': identified, 'remaining_in_response': rest, 'outside_window': outside,
            'undated_entries': undated, 'unidentified_entries': unidentified,
            'charged_micro': int(charged) if isinstance(charged, (int, float)) else None,
            # One search call returns one page; whether the service holds more is not known.
            'more_available': True if rest else None,
            'evidence': (f'One {spec["catalog_id"]} call for the last {spec["window_hours"]} hours returned '
                         f'{identified} identified rows; {outside} were older than the window and '
                         f'{rest} unseen remain after this batch. Further pages were not requested.'),
            'exhaustion': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('fetch', help='Run one configured treg surface within a window limit.')
    get.add_argument('--contract', required=True)
    get.add_argument('--input', required=True, help='"-" for JSON on stdin: thread_id, surface, max_items, seen_identifiers')
    args = parser.parse_args()
    try:
        contract = contract_api.validate(contract_api.memory.read_json(Path(args.contract).expanduser()))
        payload = json.load(sys.stdin) if args.input == '-' else json.loads(Path(args.input).read_text())
        require(isinstance(payload, dict), 'Input must be an object')
        print(json.dumps(fetch(contract, payload.get('thread_id'), payload.get('surface'), payload.get('max_items'),
                               payload.get('seen_identifiers', [])), ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
