"""Normalize observed identity links, never manufacture a source link or fetch content."""
import re
from urllib.parse import urlsplit, urlunsplit


def canonical_identifier(identifier):
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError('An observed item identifier is required')
    value = identifier.strip()
    url = urlsplit(value)
    # Analytics/photo/video links observed on a post identify that same post.
    # This is identity normalization, not service routing or a guessed navigation URL.
    if url.scheme == 'https' and url.hostname in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'}:
        match = re.fullmatch(r'(/[^/]+/status/[0-9]+)(?:/(?:analytics|photo/[0-9]+|video/[0-9]+))?/?', url.path)
        if match:
            return urlunsplit(('https', 'x.com', match[1], '', ''))
    return value


def count_key(identifier):
    value = canonical_identifier(identifier)
    opaque = re.fullmatch(r'x:post:([0-9]+)', value)
    if opaque:
        return 'x-status:' + opaque[1]
    match = re.fullmatch(r'https://x.com/[^/]+/status/([0-9]+)', value)
    return 'x-status:' + match[1] if match else value


def distinct_identifiers(identifiers):
    if not isinstance(identifiers, list):
        raise ValueError('identifiers must be an array of observed item IDs')
    return list(dict.fromkeys(count_key(value) for value in identifiers))
