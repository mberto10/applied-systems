#!/usr/bin/env python3
"""Read one RSS or Atom feed named in a contract, bounded before any entry text leaves this helper.

The feed URL comes from the contract, never from the caller, so this helper cannot be pointed at an
arbitrary address. It returns at most the requested number of unseen entries in document order,
each with a stable identifier and a deterministic comparison basis, and says whether the document
holds more. No sign-in, cookies or credentials are used; a feed is public by definition here.
"""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import contract as contract_api  # noqa: E402
import item_identity as identity  # noqa: E402

require = contract_api.require
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 20
TEXT_LIMIT = 1000  # Fixed, so the comparison basis of an unchanged entry is identical across runs.
USER_AGENT = 'AttentionDiet/0.7 (+https://github.com/mberto10/applied-systems)'
ACCOUNT_KEY = 'feed:public'

ATOM = '{http://www.w3.org/2005/Atom}'
RSS1 = '{http://purl.org/rss/1.0/}'
DC = '{http://purl.org/dc/elements/1.1/}'
CONTENT = '{http://purl.org/rss/1.0/modules/content/}'
MEDIA = '{http://search.yahoo.com/mrss/}'


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {'p', 'br', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'blockquote'}:
            self.parts.append(' ')


def plain(value):
    """Markup in a feed is data: keep its visible text, drop tags, collapse whitespace."""
    if not value:
        return ''
    parser = _Text()
    parser.feed(value)
    parser.close()
    return ' '.join(''.join(parser.parts).split())


def clip(text, limit=TEXT_LIMIT):
    return (text[:limit].rstrip() + '…', True) if len(text) > limit else (text, False)


def timestamp(value):
    if not value or not value.strip():
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)  # RSS: RFC 822
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))  # Atom: RFC 3339
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None  # A time without a zone is not an absolute source time.
    return parsed.astimezone(timezone.utc).isoformat()


def _text(element, *paths):
    for path in paths:
        found = element.find(path)
        if found is not None and (found.text or '').strip():
            return found.text.strip()
    return ''


def _atom_link(entry):
    links = entry.findall(ATOM + 'link')
    for link in links:
        if link.get('rel', 'alternate') == 'alternate' and link.get('href'):
            return link.get('href').strip()
    return links[0].get('href', '').strip() if links else ''


def _https(value):
    parts = urlsplit(value or '')
    return value if parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password else None


def parse(document):
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom bytes into a feed header and entries in document order."""
    require(isinstance(document, bytes), 'Feed document must be bytes')
    head = document[:4096].lower()
    # Entity declarations are how XML expansion attacks work; ordinary feeds never need them.
    require(b'<!doctype' not in head and b'<!entity' not in document.lower(),
            'Feed declares a DOCTYPE or entities; refusing to parse it')
    try:
        root = ET.fromstring(document)
    except ET.ParseError as error:
        raise ValueError(f'Not a well-formed feed: {error}') from None
    if root.tag == ATOM + 'feed':
        header = {'title': _text(root, ATOM + 'title'), 'link': _https(_atom_link(root))}
        raw = []
        for entry in root.findall(ATOM + 'entry'):
            author = _text(entry, f'{ATOM}author/{ATOM}name') or _text(root, f'{ATOM}author/{ATOM}name')
            body = (_text(entry, ATOM + 'summary') or _text(entry, f'{MEDIA}group/{MEDIA}description')
                    or _text(entry, ATOM + 'content'))
            raw.append({'id': _text(entry, ATOM + 'id'), 'link': _atom_link(entry), 'title': _text(entry, ATOM + 'title'),
                        'author': author, 'published': _text(entry, ATOM + 'published', ATOM + 'updated'), 'body': body})
        kind = 'atom'
    elif root.tag == 'rss':
        channel = root.find('channel')
        require(channel is not None, 'RSS document has no channel')
        header = {'title': _text(channel, 'title'), 'link': _https(_text(channel, 'link'))}
        raw = [{'id': _text(item, 'guid'), 'link': _text(item, 'link'), 'title': _text(item, 'title'),
                'author': _text(item, DC + 'creator', 'author'), 'published': _text(item, 'pubDate', DC + 'date'),
                'body': _text(item, 'description', MEDIA + 'description', CONTENT + 'encoded')}
               for item in channel.findall('item')]
        kind = 'rss'
    elif root.tag.endswith('RDF'):
        channel = root.find(RSS1 + 'channel')
        header = {'title': _text(channel, RSS1 + 'title') if channel is not None else '',
                  'link': _https(_text(channel, RSS1 + 'link')) if channel is not None else None}
        raw = [{'id': item.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about', ''), 'link': _text(item, RSS1 + 'link'),
                'title': _text(item, RSS1 + 'title'), 'author': _text(item, DC + 'creator'),
                'published': _text(item, DC + 'date'), 'body': _text(item, RSS1 + 'description', CONTENT + 'encoded')}
               for item in root.findall(RSS1 + 'item')]
        kind = 'rss1'
    else:
        raise ValueError('Not an RSS or Atom feed')
    header['title'] = plain(header['title'])
    entries, unidentified = [], 0
    for item in raw:
        identifier = (item['id'] or item['link']).strip()
        if not identifier:
            unidentified += 1  # Counted, never given a made-up identity.
            continue
        title = plain(item['title'])
        text, truncated = clip(plain(item['body']))
        sender = plain(item['author']) or header['title'] or 'Unnamed feed'
        occurred = timestamp(item['published'])
        basis = {'sender': sender, 'text': (title + '\n' + text).strip() or title or identifier}
        if occurred:
            basis['occurred_at'] = occurred
        entries.append({'identifier': identity.canonical_identifier(identifier), 'url': _https(item['link']),
                        'title': title, 'author': sender, 'published': occurred, 'text': text,
                        'text_truncated': truncated, 'basis': basis})
    return {'format': kind, 'feed': header, 'entries': entries, 'unidentified_entries': unidentified}


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(_https(newurl), 'Feed redirected away from plain https; not followed')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, opener=None):
    require(_https(url), 'Feed URLs must be plain https')
    opener = opener or urllib.request.build_opener(_HttpsOnly())
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
        'Accept': 'application/atom+xml, application/rss+xml, application/xml;q=0.9, text/xml;q=0.8'})
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read(MAX_BYTES + 1)
    require(len(body) <= MAX_BYTES, 'Feed document exceeds 5 MB; not read')
    return body


def fetch(contract, thread_id, surface, max_items, seen=(), opener=None):
    """One bounded read: at most max_items unseen entries, in the order the feed lists them."""
    thread = next((t for t in contract['coverage_threads'] if t['id'] == thread_id), None)
    require(thread is not None and thread['access']['type'] == 'feed', 'Thread is not a configured feed source')
    require(surface in thread['surfaces'], 'Surface is not configured for this feed')
    require(type(max_items) is int and max_items >= 0, 'max_items must be a nonnegative integer, the window limit')
    url = thread['feed_urls'][surface]
    parsed = parse(download(url, opener))
    seen = set(identity.distinct_identifiers(list(seen)))
    unseen, keys = [], set(seen)
    for entry in parsed['entries']:  # A feed that lists one entry twice still counts it once.
        key = identity.count_key(entry['identifier'])
        if key not in keys:
            keys.add(key)
            unseen.append(entry)
    batch, rest = unseen[:max_items], len(unseen) - min(len(unseen), max_items)
    result = {'account_key': ACCOUNT_KEY, 'thread_id': thread_id, 'surface': surface, 'feed_url': url,
              'format': parsed['format'], 'feed': parsed['feed'], 'entries': batch,
              'document_entries': len(parsed['entries']), 'remaining_in_document': rest,
              'unidentified_entries': parsed['unidentified_entries'], 'more_available': rest > 0,
              'evidence': f'The feed document lists {len(parsed["entries"])} identified entries; '
                          f'{rest} unseen remain after this batch.',
              'exhaustion': None}
    if rest == 0:
        result['evidence'] = (f'The feed document lists {len(parsed["entries"])} identified entries and every one '
                              'has been returned; a feed only offers the entries it currently lists.')
        result['exhaustion'] = {'kind': 'documented_connector_end', 'evidence': result['evidence']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('fetch', help='Read one configured feed surface within a window limit.')
    get.add_argument('--contract', required=True)
    get.add_argument('--input', required=True, help='"-" for JSON on stdin: thread_id, surface, max_items, seen_identifiers')
    args = parser.parse_args()
    try:
        contract = contract_api.validate(contract_api.memory.read_json(Path(args.contract).expanduser()))
        payload = json.load(sys.stdin) if args.input == '-' else json.loads(Path(args.input).read_text())
        require(isinstance(payload, dict), 'Input must be an object')
        print(json.dumps(fetch(contract, payload.get('thread_id'), payload.get('surface'), payload.get('max_items'),
                               payload.get('seen_identifiers', [])), ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
