#!/usr/bin/env python3
"""Attention contract: locate, validate, install and compare revisions. Structural rules come from the bundled JSON schema."""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid
from urllib.parse import urlsplit

ID_PATTERN = r"[a-z0-9][a-z0-9-]{0,63}"

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import briefing_memory as memory  # noqa: E402

require, nonempty = memory.require, memory.nonempty


def validate_thread(thread):
    """Cross-field relationships; the contract schema has already checked structure."""
    label = "Thread " + thread["id"]
    surfaces = set(thread["surfaces"])
    require(not set(thread.get("excluded_surfaces", [])) & surfaces,
            label + ": a surface is both included and excluded")
    target_field = "entry_urls" if thread["access"]["type"] == "browser" else "targets"
    require(set(thread[target_field]) == surfaces, label + ": " + target_field + " must cover every configured surface")
    for url in thread.get("entry_urls", {}).values():
        parsed = urlsplit(url)
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password,
                label + ": entry URLs must be plain https")
    require(set(thread.get("collection", {})) <= surfaces, label + ": collection must name configured surfaces")


def validate(contract):
    memory.schema_validation.validate(contract, "attention-contract.schema.json")
    memory.validate_contract(contract)  # shared memory-scope relationships, including legacy ids
    interests = contract["intent"].get("interests", [])
    require(len({i["id"] for i in interests}) == len(interests), "Duplicate interest ids")
    threads = contract["coverage_threads"]
    for thread in threads:
        validate_thread(thread)
    require(len({t["id"] for t in threads}) == len(threads), "Duplicate thread ids")
    services = {t["service"] for t in threads}
    if "serendipity" in contract:
        surfaces = {t["id"] + "/" + surface for t in threads for surface in t["surfaces"]}
        unknown = set(contract["serendipity"]["sources"]) - surfaces
        require(not unknown, "serendipity cannot read beyond configured surfaces: " + ", ".join(sorted(unknown)))
    limits = contract["run_limits"]
    per_service = limits.get("service_minutes", {})
    require(set(per_service) <= services, "service_minutes must name configured services")
    # A contract that permits parallel collection may keep overlapping allowances; the overall
    # ceiling still governs.
    if contract['execution'].get('parallelism', {}).get('mode') != 'when_independent':
        require(sum(per_service.values()) <= limits["elapsed_minutes"], "service_minutes exceed elapsed_minutes")
    composition = contract["composition"]
    require(set(composition.get("max_items_by_thread", {})) <= {t["id"] for t in threads},
            "max_items_by_thread must name configured thread ids")
    formats = {"agent_summary": "markdown", "briefing_html": "html", "discovery_html": "html"}
    require(composition.get("format", formats[composition["interface"]]) == formats[composition["interface"]],
            "Output format does not match interface")
    return contract


def home():
    override = os.environ.get("ATTENTION_DIET_HOME")
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "attention-diet"


def contract_path(contract_id):
    require(re.fullmatch(ID_PATTERN, contract_id), "Invalid contract id")
    return home() / "contracts" / contract_id / "attention_contract.json"


def available():
    folder = home() / "contracts"
    if not folder.is_dir():
        return []
    return sorted(p.parent.name for p in folder.glob("*/attention_contract.json")
                  if re.fullmatch(ID_PATTERN, p.parent.name))


def inventory():
    """Enough context to choose an existing diet without opening every contract."""
    ids, summaries = available(), []
    marker = home() / 'default'
    default = marker.read_text().strip() if marker.is_file() else None
    for ident in ids:
        try:
            document = validate(memory.read_json(contract_path(ident)))
            summaries.append({'id': ident, 'revision': document['revision'], 'default': ident == default,
                              'purpose': document['intent']['purpose'],
                              'sources': [{'service': t['service'], 'surfaces': t['surfaces']}
                                          for t in document['coverage_threads']]})
        except (ValueError, OSError, TypeError, KeyError) as error:
            summaries.append({'id': ident, 'error': str(error)})
    return {'home': str(home()), 'contracts': ids, 'summaries': summaries}


def resolve(contract_id=None):
    found = available()
    if contract_id is None:
        marker = home() / "default"
        if marker.is_file():
            contract_id = marker.read_text().strip()
        elif len(found) == 1:
            contract_id = found[0]
        else:
            require(found, "No contract installed under " + str(home()) + "; run the setup skill")
            raise ValueError("Several contracts are installed; name one: " + ", ".join(found))
    require(contract_id in found, "Contract not installed: " + contract_id)
    return contract_path(contract_id)


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def edit_lock():
    """Serialize installs and proposal application, including the stale-base check."""
    home().mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(home() / '.edit.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.write(b'0')
                stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another contract edit is in progress; retry after it completes')
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def install_document(contract, make_default=False):
    """Caller holds edit_lock. Validate again at the point of installation."""
    validate(contract)
    target = contract_path(contract["id"])
    if target.exists():
        current = memory.read_json(target)
        changes = diff(current, contract)  # enforces same id and revision + 1
        write_private(target.parent / "revisions" / ("%d.json" % current["revision"]),
                      json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    else:
        changes = []
    write_private(target, json.dumps(contract, ensure_ascii=False, indent=2) + "\n")
    if make_default:
        write_private(home() / "default", contract["id"] + "\n")
    return {"path": str(target), "revision": contract["revision"], "changes": changes}


def log_change(target, revision, reason, changes, marker=''):
    """Append one dated line per installed revision to the contract's changelog."""
    changelog = target.parent / 'changelog.md'
    existing = changelog.read_text() if changelog.exists() else ''
    if marker and marker in existing:
        return changelog
    reason = ' '.join(reason.splitlines())
    paths = ', '.join(dict.fromkeys(c['path'] for c in changes))
    line = f"- {datetime.now(timezone.utc).date().isoformat()} · revision {revision}: {reason} ({paths}) {marker}".rstrip() + '\n'
    write_private(changelog, existing + ('\n' if existing and not existing.endswith('\n') else '') + line)
    return changelog


def install(source, make_default=False):
    """File-based installation of a hand-edited copy; skills use prepare/apply instead."""
    with edit_lock():
        result = install_document(memory.read_json(source), make_default)
        if result['changes']:  # A new contract has no earlier revision to compare with.
            log_change(Path(result['path']), result['revision'], 'Manual edit installed from a file',
                       result['changes'])
        return result


def remove(contract_id):
    """Archive, never delete. Briefing memory is left where it is."""
    source = resolve(contract_id).parent
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = home() / "contracts" / ".removed" / (contract_id + "-" + stamp)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source.rename(target)
    marker = home() / "default"
    if marker.is_file() and marker.read_text().strip() == contract_id:
        marker.unlink()
    return {"archived_to": str(target), "memory": "unchanged"}


def export(contract_id):
    """A template-shaped copy: no account lists, identities, history links or personal paths."""
    shared = copy.deepcopy(validate(memory.read_json(resolve(contract_id))))
    shared.update(id="my-attention", revision=1)
    shared.pop("previous_ids", None)
    for thread in shared["coverage_threads"]:
        thread.pop("expected_account", None)
        thread["access"].pop("connection_id", None)
        for field in ("creators", "people", "accounts"):
            if field in thread:
                thread[field] = []
    policy = shared["memory_context"]
    if policy["provider"] == "local":
        policy["directory"] = "~/.local/state/attention-diet/my-attention"
    else:
        shared["memory_context"] = {"provider": "local", "directory": "~/.local/state/attention-diet/my-attention",
                                    "purpose": policy["purpose"], "on_unavailable": policy["on_unavailable"]}
    return validate(shared)


digest = memory.digest


def pointer_part(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def differences(old, new, path=''):
    """Leaf changes, aligned by stable IDs for object lists and by value for other lists."""
    if type(old) is type(new) and old == new:
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        changes = []
        for key in sorted(set(old) | set(new)):
            location = path + '/' + pointer_part(key)
            if key not in old or key not in new:
                changes.append({'path': location, 'op': 'add' if key not in old else 'remove',
                                'before': old.get(key), 'after': new.get(key)})
            else:
                changes.extend(differences(old[key], new[key], location))
        return changes
    if isinstance(old, list) and isinstance(new, list):
        keyed = all(isinstance(v, dict) and isinstance(v.get('id'), str) for v in old + new)
        keyed = keyed and all(len({v['id'] for v in values}) == len(values) for values in (old, new))
        keys = lambda values: [v['id'] if keyed else json.dumps(v, sort_keys=True) for v in values]
        changes = []
        for tag, i, end_i, j, end_j in SequenceMatcher(None, keys(old), keys(new), autojunk=False).get_opcodes():
            paired = min(end_i - i, end_j - j) if tag == 'equal' or not keyed and tag == 'replace' else 0
            for offset in range(paired):
                changes.extend(differences(old[i + offset], new[j + offset], path + '/' + str(j + offset)))
            changes.extend({'path': path + '/' + str(n), 'op': 'remove', 'before': old[n], 'after': None}
                           for n in range(i + paired, end_i))
            changes.extend({'path': path + '/' + str(n), 'op': 'add', 'before': None, 'after': new[n]}
                           for n in range(j + paired, end_j))
        return changes
    return [{'path': path, 'op': 'replace', 'before': old, 'after': new}]


def diff(old, new):
    require(old["id"] == new["id"], "A revision keeps its contract id; use previous_ids for a rename")
    require(new["revision"] == old["revision"] + 1, "A changed contract increments revision by exactly one")
    changes = [c for c in differences(old, new) if c['path'] != '/revision']
    require(changes, "Revision changed without any other difference")
    return changes


def apply_patch(document, operations):
    """The add/replace/remove subset of JSON Patch; never edit the installed file in place."""
    require(isinstance(operations, list) and operations, 'Supply a nonempty patch array')
    document = copy.deepcopy(document)
    for operation in operations:
        require(isinstance(operation, dict), 'Each patch operation must be an object')
        op, path = operation.get('op'), operation.get('path')
        require(op in {'add', 'replace', 'remove'}, 'Use add, replace or remove')
        require(set(operation) == ({'op', 'path'} if op == 'remove' else {'op', 'path', 'value'}),
                'Patch fields must be op, path and (except for remove) value')
        require(isinstance(path, str) and path.startswith('/') and not re.search(r'~(?![01])', path),
                'Use a JSON Pointer path beginning with /')
        parts = [p.replace('~1', '/').replace('~0', '~') for p in path[1:].split('/')]
        require(parts[0] not in {'id', 'revision'}, 'The helper owns id and revision')
        parent = document
        for part in parts[:-1]:
            if isinstance(parent, list):
                require(bool(re.fullmatch(r'0|[1-9][0-9]*', part)) and int(part) < len(parent), 'Missing array path')
                parent = parent[int(part)]
            else:
                require(isinstance(parent, dict) and part in parent, 'Missing parent path: ' + path)
                parent = parent[part]
        key = parts[-1]
        if isinstance(parent, list):
            require(key == '-' and op == 'add' or bool(re.fullmatch(r'0|[1-9][0-9]*', key)), 'Invalid array index')
            index = len(parent) if key == '-' else int(key)
            require(index < len(parent) or op == 'add' and index == len(parent), 'Array index out of range')
            if op == 'remove':
                parent.pop(index)
            elif op == 'add':
                parent.insert(index, copy.deepcopy(operation['value']))
            else:
                parent[index] = copy.deepcopy(operation['value'])
        else:
            require(isinstance(parent, dict), 'Patch parent must be an object or array')
            require(op == 'add' or key in parent, 'Missing field: ' + path)
            if op == 'remove':
                del parent[key]
            else:
                parent[key] = copy.deepcopy(operation['value'])
    return document


def proposal_path(proposal_id):
    require(isinstance(proposal_id, str) and bool(re.fullmatch('[a-f0-9]{32}', proposal_id)), 'Invalid proposal ID')
    return home() / 'proposals' / (proposal_id + '.json')


def prepare(payload, contract_id=None, new=False, expected_digest=None):
    require(isinstance(payload, dict) and set(payload) == {'reason', 'patch'} and nonempty(payload.get('reason')),
            'Supply reason (the user correction) and patch only')
    if new:
        require(contract_id is not None, '--new needs --id')
        require(not contract_path(contract_id).exists(), 'Contract already exists; use tune')
        require(expected_digest is None, 'A new contract has no base digest')
        base = memory.read_json(Path(__file__).resolve().parents[1] / 'templates/attention-contract.json')
        base.update(id=contract_id, revision=1)
        base['memory_context']['directory'] = '~/.local/state/attention-diet/' + contract_id
    else:
        base = validate(memory.read_json(resolve(contract_id)))
        require(expected_digest is not None and expected_digest == digest(base),
                'Contract changed or base digest missing; resolve again before preparing')
    document = apply_patch(base, payload['patch'])
    document['revision'] = 1 if new else base['revision'] + 1
    validate(document)
    changes = [c for c in differences(base, document) if c['path'] != '/revision'] if new else diff(base, document)
    require(changes, 'No contract change to prepare')
    proposal_id = uuid.uuid4().hex
    proposal = {'contract': document, 'base_digest': None if new else digest(base),
                'document_digest': digest(document), 'reason': payload['reason'], 'changes': changes}
    write_private(proposal_path(proposal_id), json.dumps(proposal, ensure_ascii=False, indent=2) + '\n')
    return {'proposal': proposal_id, 'id': document['id'], 'revision': document['revision'],
            'changes': changes, 'installed': False}


def apply_proposal(proposal_id, make_default=False):
    with edit_lock():
        path = proposal_path(proposal_id)
        require(not path.is_symlink(), 'Proposal must be a helper-owned file')
        proposal = memory.read_json(path)
        document = validate(proposal['contract'])
        require(digest(document) == proposal['document_digest'], 'Prepared contract changed; prepare again')
        target = contract_path(document['id'])
        current = memory.read_json(target) if target.exists() else None
        current_digest = digest(current) if current is not None else None
        # A previous apply may have installed before a changelog write failed. Complete it on retry.
        recovering = proposal.get('applying') is True and current_digest == proposal['document_digest']
        require(current_digest == proposal['base_digest'] or recovering,
                'Contract changed since preparation; resolve and prepare again')
        make_default = make_default or proposal.get('make_default', False)
        if not recovering:
            proposal['applying'] = True
            proposal['make_default'] = make_default
            write_private(path, json.dumps(proposal, ensure_ascii=False, indent=2) + '\n')
            result = install_document(document, make_default)
        else:
            if make_default:
                write_private(home() / 'default', document['id'] + '\n')
            result = {'path': str(target), 'revision': document['revision']}
        # Stable marker makes recovery idempotent while keeping the actual correction readable.
        changelog = log_change(target, document['revision'], proposal['reason'], proposal['changes'],
                               '<!-- attention-edit:' + proposal_id + ' -->')
        path.unlink()
        return {**result, 'changes': proposal['changes'], 'changelog': str(changelog), 'proposal_removed': True}


def discard_proposal(proposal_id):
    with edit_lock():
        path = proposal_path(proposal_id)
        proposal = memory.read_json(path)
        require(not proposal.get('applying'), 'Application started; retry apply to finish, then prepare an undo if needed')
        path.unlink()
    return {'discarded': proposal_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "resolve", "list", "install", "diff", "remove", "export",
                                            "prepare", "apply", "discard"])
    parser.add_argument("--out", help="Where export writes its result")
    parser.add_argument("--contract", help="Contract JSON path")
    parser.add_argument("--id", help="Installed contract id")
    parser.add_argument("--old", help="Current revision, for diff")
    parser.add_argument("--default", action="store_true", help="Make the installed contract the default")
    parser.add_argument('--new', action='store_true', help='Prepare from the bundled template; refuse an existing id')
    parser.add_argument('--input', help='Preparation payload JSON file, or - for stdin')
    parser.add_argument('--expected-digest', help='Digest returned by resolve; required when preparing a revision')
    parser.add_argument('--proposal', help='Helper-owned proposal ID returned by prepare')
    args = parser.parse_args()
    try:
        if args.command == "list":
            result = inventory()
        elif args.command == "resolve":
            path = Path(args.contract).expanduser() if args.contract else resolve(args.id)
            contract = validate(memory.read_json(path))
            result = {"path": str(path.resolve()), "id": contract["id"], "revision": contract["revision"],
                      'contract': contract, 'digest': digest(contract)}
        elif args.command == 'prepare':
            require(args.input, '--input is required')
            payload = json.load(sys.stdin) if args.input == '-' else memory.read_json(args.input)
            result = prepare(payload, args.id, args.new, args.expected_digest)
        elif args.command == 'apply':
            result = apply_proposal(args.proposal, args.default)
        elif args.command == 'discard':
            result = discard_proposal(args.proposal)
        elif args.command == "remove":
            require(args.id, "--id is required")
            result = remove(args.id)
        elif args.command == "export":
            require(args.id and args.out, "--id and --out are required")
            document = export(args.id)
            write_private(Path(args.out).expanduser(), json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            result = {"exported": args.out, "review": "Free-text rules may still contain names; read before sharing"}
        else:
            require(args.contract, "--contract is required")
            if args.command == "validate":
                contract = validate(memory.read_json(args.contract))
                result = {"valid": True, "id": contract["id"], "revision": contract["revision"]}
            elif args.command == "install":
                result = install(args.contract, args.default)
            else:
                require(args.old, "--old is required")
                result = {"changes": diff(memory.read_json(args.old), validate(memory.read_json(args.contract)))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
