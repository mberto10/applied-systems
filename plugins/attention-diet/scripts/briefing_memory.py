#!/usr/bin/env python3
"""Briefing memory. Schema-validated records; provider tools remain agent-operated."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import item_identity as identity  # noqa: E402
import validation as schema_validation  # noqa: E402

VERSION = "attention-summary/1.0"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(document):
    """The one canonical JSON fingerprint for contracts, run payloads and prepared memory."""
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def read_json(path):
    return json.loads(Path(path).read_text())


def validate_contract(contract):
    """Validate the memory scope even when reading an older contract revision."""
    schema_validation.validate(contract, "attention-contract.schema.json", "#/$defs/memoryScope")
    require(contract["id"] not in contract.get("previous_ids", []), "previous_ids must list earlier contract ids only")
    policy = contract["memory_context"]
    if policy["provider"] == "local":
        require(Path(policy["directory"]).expanduser().is_absolute(), "Memory directory must be absolute or start with ~/")
    return policy


def validate_items(items):
    schema_validation.validate(items, "memory-record.schema.json", "#/properties/items")
    require(len({item_key(i) for i in items}) == len(items), "Duplicate item versions")


def item_key(item):
    return tuple(item[k] for k in ("service", "identifier", "change_fingerprint"))


def comparison_key(item):
    # Known observed X URL/native-ID aliases are the same post. Leave stored
    # records and validation untouched; arbitrary opaque identifiers stay exact.
    return (item['service'], identity.count_key(item['identifier']), item['change_fingerprint'])


def parse_timestamp(value):
    schema_validation.validate(value, "memory-record.schema.json", "#/$defs/itemVersion/properties/source_timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return stamp


def validate_record(record):
    schema_validation.validate(record, "memory-record.schema.json")
    require(record["previous_version"] != record["version_id"], "A summary cannot reference itself")
    require(len({item_key(i) for i in record["items"]}) == len(record["items"]), "Duplicate item versions")
    return record


def encode(record):
    validate_record(record)
    metadata = {k: v for k, v in record.items() if k != "summary"}
    # JSON is valid YAML front matter, and avoids a runtime YAML dependency.
    return "---\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n---\n" + record["summary"].strip() + "\n"


def decode(content):
    require(isinstance(content, str) and content.startswith("---\n"), "Missing summary front matter")
    front, body = content[4:].split("\n---\n", 1)
    record = json.loads(front)
    require(isinstance(record, dict) and "summary" not in record, "Invalid summary metadata")
    record["summary"] = body.strip()
    return validate_record(record)


def potential_summary(content):
    """Mixed provider spaces contain ordinary notes too; uncertain envelopes stay visible."""
    if 'attention-summary/' in content:
        return True
    if not content.startswith('---\n'):
        return any('"' + key + '"' in content for key in ('contract_id', 'account_key', 'version_id'))
    try:
        metadata = json.loads(content[4:].split('\n---\n', 1)[0])
    except (ValueError, TypeError):
        return True  # An ambiguous/broken envelope is not evidence of unrelated content.
    return not isinstance(metadata, dict) or bool(
        {'schema_version', 'contract_id', 'account_key', 'version_id'} & set(metadata))


def load_history(contract, account, documents=None):
    policy = validate_contract(contract)
    require(nonempty(account), "Authenticated account key is required")
    records, warnings = [], []
    sources = []
    if policy["provider"] == "local":
        require(documents is None, "Local memory must not use a provider export")
        folder = Path(policy["directory"]).expanduser() / "summaries"
        try:
            if folder.exists():
                require(folder.is_dir(), "Summary location is not a directory")
                for path in sorted(folder.iterdir()):
                    if path.suffix == ".md":
                        try:
                            sources.append((path.name, path.read_text()))
                        except (OSError, UnicodeError):
                            warnings.append("Could not read a local summary")
        except (OSError, ValueError):
            warnings.append("Local history is unavailable")
    else:
        if documents is None:
            warnings.append("Provider history was not retrieved")
        else:
            require(isinstance(documents, dict) and documents.get("space") == policy["space"],
                    "Provider history belongs to a different space")
            require(isinstance(documents.get("documents"), list), "Invalid provider export")
            if documents.get("complete") is not True:
                warnings.append("Provider history retrieval is incomplete")
            for doc in documents["documents"]:
                if (doc.get("status") != "done" or doc.get("contentTruncated") is not False
                        or not isinstance(doc.get("content"), str)):
                    warnings.append("A provider document is not fully available")
                else:
                    sources.append((doc["id"], doc["content"]))
    seen_versions = {}
    # A renamed contract keeps the history saved under its earlier ids.
    contract_ids = {contract["id"], *contract.get("previous_ids", [])}
    for reference, content in sources:
        if policy['provider'] != 'local' and not potential_summary(content):
            continue
        try:
            record = decode(content)
            if record["contract_id"] not in contract_ids or record["account_key"] != account:
                continue
            prior = seen_versions.get(record["version_id"])
            if prior is not None:
                require(prior == record, "Conflicting version contents")
                continue
            seen_versions[record["version_id"]] = record
            records.append({"reference": reference, "record": record})
        except (ValueError, TypeError, KeyError):
            warnings.append("A history document could not be validated")
    records.sort(key=lambda r: (datetime.fromisoformat(r["record"]["created_at"].replace("Z", "+00:00")),
                                r["record"]["version_id"]))
    ids = {r["record"]["version_id"] for r in records}
    if any(r["record"]["previous_version"] and r["record"]["previous_version"] not in ids for r in records):
        warnings.append("An earlier referenced summary is missing")
    return {"records": records, "warnings": sorted(set(warnings))}


def context(history, contract, full=False):
    latest = history['records'][-1] if history['records'] else None
    if latest is not None and not full:
        latest = {'reference': latest['reference'], 'record': {
            k: v for k, v in latest['record'].items() if k != 'items'}}
    result = {'latest': latest, 'versions': len(history['records']), 'warnings': history['warnings']}
    runs = contract.get('serendipity', {}).get('avoid_repeating_topics_for_runs', 0)
    if runs:
        result['recent_serendipity_topics'] = recent_topics(history, runs)
    return result


def verify_artifact(content, document):
    """Check the original retrieved artifact, not a queued acknowledgement or semantic summary."""
    expected = decode(content)  # A traceback/failed command can never be a valid outbound artifact.
    require(isinstance(document, dict), 'Expected an original provider document')
    if document.get('status') == 'failed':
        return {'status': 'failed', 'notice': 'Briefing memory storage failed.'}
    if document.get('status') != 'done':
        return {'status': 'pending', 'notice': 'Briefing memory storage is pending; continuity is not yet verified.'}
    if document.get('contentTruncated') is not False or not isinstance(document.get('content'), str):
        return {'status': 'unverified', 'notice': 'Briefing memory could not be retrieved in full; storage is unverified.'}
    try:
        actual = decode(document['content'])
    except (ValueError, TypeError, KeyError):
        return {'status': 'failed', 'notice': 'The stored document is not the prepared briefing artifact; briefing memory was not saved correctly.'}
    if actual != expected:
        return {'status': 'failed', 'notice': 'Stored briefing fields differ from the prepared artifact; briefing memory was not saved correctly.'}
    return {'status': 'verified', 'version_id': expected['version_id']}


def recent_topics(history, runs):
    """Topics of serendipity items in the latest `runs` summaries, newest first."""
    latest = history["records"][-runs:] if runs > 0 else []
    return [i["topic"] for r in reversed(latest) for i in r["record"]["items"] if i.get("slot") == "serendipity"]


def compare(history, candidates, *, public_posts=False):
    """Changed captures need event evidence; public post edits are not yet verifiable."""
    validate_items(candidates)
    seen = {comparison_key(i) for r in history["records"] for i in r["record"]["items"]}
    warnings = sorted(set(history["warnings"]))
    new, uncertain = [], []
    for candidate in candidates:
        if comparison_key(candidate) in seen:
            continue  # Exact stored identity/hash, including an unversioned old record.
        previous = [(i, r["record"]["created_at"]) for r in history["records"]
                    for i in r["record"]["items"]
                    if comparison_key(i)[:2] == comparison_key(candidate)[:2]]
        method = candidate.get("fingerprint_method")
        # The method describes how a hash was made, not whether extraction depth,
        # author presentation or included link/media text stayed the same.
        new_incoming = (not public_posts and method == "incoming-id/v1" and
                        any(i.get("fingerprint_method") == method for i, _ in previous))
        later_event = (not public_posts and previous and candidate.get("source_timestamp") and
                       parse_timestamp(candidate["source_timestamp"]) >
                       max(parse_timestamp(created) for _, created in previous))
        if not previous or new_incoming or later_event:
            new.append(candidate)
        else:
            uncertain.append(candidate)
    if uncertain:
        warnings.append("Some known items have changed captures without reliable evidence of a new event; novelty is uncertain")
    return {"new_items": new, "uncertain_items": uncertain,
            "already_briefed_count": sum(comparison_key(i) in seen for i in candidates),
            "baseline": not history["records"] and not history["warnings"],
            "continuity": "limited" if warnings else "available",
            "warnings": warnings}


def fingerprint(basis):
    require(isinstance(basis, dict), "Fingerprint input must be an object")
    require(set(basis) <= {"incoming_id", "sender", "text", "occurred_at"},
            "Use stable incoming identity/content, not UI badges or relative time")
    if nonempty(basis.get("incoming_id")):
        stable = {"incoming_id": basis["incoming_id"].strip()}
    else:
        require(nonempty(basis.get("sender")) and nonempty(basis.get("text")),
                "Need incoming_id or sender and visible source text")
        stable = {"sender": " ".join(basis["sender"].split()), "text": " ".join(basis["text"].split())}
        if basis.get("occurred_at"):
            stamp = datetime.fromisoformat(basis["occurred_at"].replace("Z", "+00:00"))
            require(stamp.tzinfo is not None, "Use an absolute source timestamp")
            stable["occurred_at"] = stamp.astimezone(timezone.utc).isoformat()
    return "sha256:" + hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fingerprint_metadata(basis):
    digest = fingerprint(basis)
    method = ("incoming-id/v1" if nonempty(basis.get("incoming_id")) else
              "sender-text-time/v1" if basis.get("occurred_at") else "sender-text/v1")
    result = {"change_fingerprint": digest, "fingerprint_method": method}
    if basis.get("occurred_at"):
        result["source_timestamp"] = parse_timestamp(basis["occurred_at"]).astimezone(timezone.utc).isoformat()
    return result


def build_record(contract, account, payload, history):
    require(set(payload) == {"version_id", "items", "coverage", "summary"}, "Invalid save payload fields")
    require(nonempty(payload["summary"]), "Summary must not be empty")
    record = {"schema_version": VERSION, "version_id": payload["version_id"],
              "previous_version": history["records"][-1]["record"]["version_id"] if history["records"] else None,
              "contract_id": contract["id"], "contract_revision": contract["revision"],
              "account_key": account, "created_at": datetime.now(timezone.utc).isoformat(),
              "items": payload["items"], "coverage": payload["coverage"], "summary": payload["summary"].strip()}
    for entry in history["records"]:
        old = entry["record"]
        if old["version_id"] == record["version_id"]:
            require(all(old[k] == record[k] for k in ("items", "coverage", "summary", "contract_revision")),
                    "Version id already contains different content")
            return old
    return validate_record(record)


def save_local(contract, record):
    policy = validate_contract(contract)
    require(policy["provider"] == "local", "Use provider tools to save remote memory")
    content = encode(record)
    root = Path(policy["directory"]).expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    folder = root / "summaries"
    folder.mkdir(exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    # Hash the account/contract scope to avoid raw identities in filenames.
    scope = hashlib.sha256(json.dumps([record["contract_id"], record["account_key"]]).encode()).hexdigest()[:24]
    target = folder / (scope + "-" + record["version_id"] + ".md")
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=folder)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)  # Atomic create, never replace a concurrent version.
        except FileExistsError:
            require(target.read_text() == content, "Version already exists with different content")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "load", "compare", "fingerprint", "fingerprint-batch", "render", "save"])
    parser.add_argument("--contract")
    parser.add_argument("--account")
    parser.add_argument("--input", help="JSON file, or - for stdin")
    parser.add_argument("--documents", help="Normalized Supermemory original-document export")
    parser.add_argument("--finalized", action="store_true", help="Input describes the finalized briefing, not candidates")
    parser.add_argument('--full', action='store_true', help='Load only: include item versions for diagnostics')
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else read_json(args.input) if args.input else None
        if args.command == "fingerprint":
            result = fingerprint_metadata(payload)
        elif args.command == 'fingerprint-batch':
            require(isinstance(payload, list), 'Batch input must be an array of fingerprint bases')
            result = [fingerprint_metadata(basis) for basis in payload]
        else:
            require(args.contract, "--contract is required")
            contract = read_json(args.contract)
            validate_contract(contract)
            if args.command == "validate":
                result = {"valid": True, "provider": contract["memory_context"]["provider"]}
            else:
                history = load_history(contract, args.account, read_json(args.documents) if args.documents else None)
                if args.command == "load":
                    result = context(history, contract, args.full)
                elif args.command == "compare":
                    # Diagnostic items have no thread reference. If a service mixes
                    # public posts and private messages, use the stricter policy.
                    public_services = {t['service'] for t in contract.get('coverage_threads', [])
                                       if t.get('content') == 'public_posts'}
                    result = compare(history, payload, public_posts=any(
                        item['service'] in public_services for item in payload))
                else:
                    require(isinstance(payload, dict), "Save/render requires a summary payload")
                    require(args.finalized, "Only finalized summaries can enter memory; pass --finalized")
                    record = build_record(contract, args.account, payload, history)
                    result = {"version_id": record["version_id"], "warnings": history["warnings"]}
                    if args.command == "save":
                        result["path"] = save_local(contract, record)
                    else:
                        result["content"] = encode(record)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
