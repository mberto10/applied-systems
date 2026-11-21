#!/usr/bin/env python3
"""Import the accounts an X user follows into a treg surface's `handles`, as a contract proposal.

Reads the following list through treg (one billed call per page) and prepares a contract revision
that sets the surface's handles to that list. Handles already checked by another surface of the same
thread (for example a watched list) are left out, so no account is called twice. Nothing is
installed: apply the proposal with `contract.py apply --proposal ID` after looking at the changes.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import contract as contract_api  # noqa: E402
import treg_source  # noqa: E402

require = contract_api.require
CATALOG_ID = 'anyapi.twitter.following'  # about 50 accounts per page; tikhub's equivalent rejected some handles
MAX_PAGES = 40
MAX_HANDLES = 500  # the schema's limit for one surface
HANDLE = re.compile(r'^[A-Za-z0-9_]{1,15}$')
NAME_FIELDS = ('username', 'screen_name', 'userName', 'legacy.screen_name', 'core.screen_name')


def _cursor(document):
    """The next-page cursor anywhere in the answer, or None."""
    if isinstance(document, dict):
        for key in ('nextCursor', 'next_cursor', 'cursor_bottom'):
            value = document.get(key)
            if isinstance(value, str) and value and value != '0':
                return value
        for value in document.values():
            found = _cursor(value)
            if found:
                return found
    return None


def following(handle, runner=None, max_pages=MAX_PAGES):
    """Every handle `handle` follows, in the order X lists them, and the total charge in micro-dollars."""
    require(bool(HANDLE.fullmatch(handle or '')), 'Give the X handle without @')
    binary = treg_source.treg_binary() if runner is None else 'treg'
    names, cursor, charged = [], None, 0
    for _ in range(max_pages):
        body = {'username': handle, **({'cursor': cursor} if cursor else {})}
        answer = (runner or treg_source.run_treg)(
            treg_source.call_argv(binary, {'catalog_id': CATALOG_ID, 'method': 'POST', 'body': body, 'query': {}}))
        charged += int((answer.get('_treg') or {}).get('charged_micro') or 0)
        payload = answer.get('result', answer)
        page = []
        for row in treg_source.rows(payload):
            name = next((treg_source._get(row, f) for f in NAME_FIELDS if treg_source._get(row, f)), None)
            if isinstance(name, str) and HANDLE.fullmatch(name.lstrip('@')):
                page.append(name.lstrip('@'))
        fresh = [n for n in page if n.lower() not in {x.lower() for x in names}]
        names += fresh
        cursor = _cursor(payload)
        if not cursor or not fresh:  # an end, or a page that repeats what we have
            break
    return names, charged


def surface_patch(contract, thread_id, surface, handles):
    """The patch that sets the surface's handles, leaving out accounts other surfaces already check."""
    index, thread = next(((i, t) for i, t in enumerate(contract['coverage_threads']) if t['id'] == thread_id),
                         (None, None))
    require(thread is not None and thread['access']['type'] == 'treg', 'Thread is not a configured treg source')
    call = thread['treg_calls'].get(surface)
    require(call is not None, 'Surface is not configured for this treg source')
    require(treg_source.handle_mode(call) is not None, 'The surface call has no {handle} or {from_handles} placeholder')
    elsewhere = {h.lower() for s, c in thread['treg_calls'].items() if s != surface for h in c.get('handles', [])}
    kept = [h for h in handles if h.lower() not in elsewhere]
    require(kept, 'Every followed account is already checked by another surface')
    require(len(kept) <= MAX_HANDLES, f'{len(kept)} accounts; a surface takes at most {MAX_HANDLES}. '
                                      'Move some to another surface or trim the list.')
    before = {h.lower() for h in call.get('handles', [])}
    after = {h.lower() for h in kept}
    path = f'/coverage_threads/{index}/treg_calls/{surface}/handles'
    return ([{'op': 'add', 'path': path, 'value': kept}],
            {'added': sorted(h for h in kept if h.lower() not in before),
             'removed': sorted(h for h in call.get('handles', []) if h.lower() not in after),
             'left_out': sorted(h for h in handles if h.lower() in elsewhere), 'total': len(kept)})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--handle', required=True, help='Your X handle, without @')
    parser.add_argument('--id', help='Contract id; the default contract when omitted')
    parser.add_argument('--thread', help='treg thread id')
    parser.add_argument('--surface', help='Surface whose handles the list replaces')
    parser.add_argument('--list', action='store_true', help='Only print the handles; prepare nothing')
    args = parser.parse_args()
    try:
        handles, charged = following(args.handle)
        if args.list:
            print(json.dumps({'handles': handles, 'charged_micro': charged}))
            return 0
        require(args.thread and args.surface, '--thread and --surface are needed to prepare a proposal')
        path = contract_api.resolve(args.id)
        contract = contract_api.validate(contract_api.memory.read_json(path))
        patch, summary = surface_patch(contract, args.thread, args.surface, handles)
        result = contract_api.prepare({'reason': f'Imported the accounts @{args.handle} follows on X', 'patch': patch},
                                      contract['id'], expected_digest=contract_api.digest(contract))
        print(json.dumps({'proposal': result['proposal'], 'revision': result['revision'], **summary,
                          'charged_micro': charged}, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
