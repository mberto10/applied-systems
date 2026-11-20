#!/usr/bin/env python3
"""HTML bodies for the needs-you list and the front page.

Both take the selection as plain data (the same shape briefing.py exposes as `$data`) and return
escaped HTML for a template's `$content`. Source text is always escaped; the pages stay offline,
and the needs-you filters work with CSS alone, so no script is needed under the templates' CSP.
"""
from html import escape
import re
from urllib.parse import urlsplit

VIDEO_HOSTS = ('youtube.com', 'youtu.be', 'vimeo.com', 'tiktok.com')
POST_HOSTS = ('x.com', 'twitter.com', 'bsky.app', 'threads.net', 'reddit.com', 'news.ycombinator.com', 'linkedin.com')


def kind(entry):
    """Video, post or article, from the entry's link; an entry without a link counts as an article."""
    host = (urlsplit(entry.get('url') or '').hostname or '').removeprefix('www.')
    if any(host == h or host.endswith('.' + h) for h in VIDEO_HOSTS):
        return 'video'
    if any(host == h or host.endswith('.' + h) for h in POST_HOSTS):
        return 'post'
    return 'article'


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'other'


def entries_of(data):
    """Every entry with its section name attached, in selection order."""
    return [dict(entry, section=section['name']) for section in data['sections'] for entry in section['entries']]


def link(entry, text, cls=''):
    attr = f' class="{cls}"' if cls else ''
    if entry.get('url'):
        return f'<a{attr} href="{escape(entry["url"], quote=True)}">{escape(text)}</a>'
    return f'<span{attr}>{escape(text)}</span>'


def summary(entry):
    """The summary, unless it only repeats the title."""
    text, title = entry.get('summary') or '', entry['title'].rstrip('…').strip()
    return '' if not text or text.startswith(title) else f'<p class="sum">{escape(text)}</p>'


REASONS = ('<input type="checkbox" id="why" class="toggle">'
           '<label for="why" class="why-toggle">Reasons</label>')


def held_back(data):
    rows = data.get('held_back') or []
    if not rows:
        return ''
    items = ''.join(f'<li><span>{escape(r["reason"])}</span><b>{int(r["count"])}</b></li>' for r in rows)
    return f'<details class="held"><summary>Held back</summary><ul>{items}</ul></details>'


def kicker(entry, sections, sources):
    """Section and source, each only when the page holds more than one; a surprise is always marked."""
    parts = ([entry['section']] if len(sections) > 1 else []) + ([entry['source']] if len(sources) > 1 else [])
    if entry.get('surprise'):
        parts.append('outside your interests')
    return ' · '.join(parts)


def needs_you(data):
    entries = entries_of(data)
    sections = list(dict.fromkeys(e['section'] for e in entries))
    sources = list(dict.fromkeys(e['source'] for e in entries))
    filters = [('all', 'All')]
    filters += [('s-' + slug(s), s) for s in sections if len(sections) > 1]
    filters += [('o-' + slug(s), s) for s in sources if len(sources) > 1]
    radios = ''.join(f'<input type="radio" name="f" id="f-{key}"{" checked" if key == "all" else ""}>' for key, _ in filters)
    chips = ''.join(f'<label for="f-{key}">{escape(name)}</label>' for key, name in filters) if len(filters) > 1 else ''
    rules = ''.join(f'#f-{key}:checked~.list article:not(.{key}){{display:none}}'
                    f'#f-{key}:checked~.chips label[for=f-{key}]{{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}}'
                    for key, _ in filters if key != 'all')
    rules += '#f-all:checked~.chips label[for=f-all]{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}'
    cards = []
    for n, e in enumerate(entries):
        classes = f's-{slug(e["section"])} o-{slug(e["source"])}'
        caveats = ''.join(f'<p class="caveat">{escape(c)}</p>' for c in e.get('caveats', []))
        tag = kicker(e, sections, sources)
        cards.append(f'<article class="{classes}" style="animation-delay:{n * 0.05:.2f}s">'
                     + (f'<p class="src">{escape(tag)}</p>' if tag else '') +
                     f'{link(e, e["title"], "title")}'
                     f'{summary(e)}<p class="why">{escape(e["why"])}</p>{caveats}</article>')
    empty = '<p class="empty">Nothing new worth your time.</p>' if not entries else ''
    return (f'<style>{rules}</style>{REASONS}{radios}<div class="chips" role="group" aria-label="Filter">{chips}</div>'
            f'<div class="list">{"".join(cards)}{empty}</div>{held_back(data)}')


def front_page(data):
    entries = entries_of(data)
    if not entries:
        return '<p class="empty">Nothing new worth your time.</p>' + held_back(data)

    sections = list(dict.fromkeys(e['section'] for e in entries))
    sources = list(dict.fromkeys(e['source'] for e in entries))

    def story(e, cls):
        caveats = ''.join(f'<p class="caveat">{escape(c)}</p>' for c in e.get('caveats', []))
        tag = kicker(e, sections, sources)
        return (f'<article class="{cls} {kind(e)}">' + (f'<p class="kicker">{escape(tag)}</p>' if tag else '') +
                f'<h3>{link(e, e["title"])}</h3>{summary(e)}'
                f'<p class="why">{escape(e["why"])}</p>{caveats}</article>')

    lead, rest = entries[0], entries[1:]
    side, rest = rest[:2], rest[2:]
    parts = ['<section class="top">' + story(lead, 'lead') + '<div class="side">' + ''.join(story(e, 'second') for e in side) + '</div></section>']
    for name, label in (('video', 'Watch'), ('post', 'Posts'), ('article', 'Read')):
        group = [e for e in rest if kind(e) == name]
        if group:
            parts.append(f'<section class="row {name}"><h2>{label}</h2><div class="grid">' + ''.join(story(e, 'card') for e in group) + '</div></section>')
    return REASONS + ''.join(parts) + held_back(data)
