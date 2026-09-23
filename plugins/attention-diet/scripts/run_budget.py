#!/usr/bin/env python3
"""Run budget for one bounded check.

The agent cannot measure elapsed time by itself. `start` records when a run began; `service` marks
where one source's share begins; `check` reports what is left. Ceilings are never quotas.

Collectors working in parallel share this one run state. Their source clocks then run side by side
under the single overall deadline, and every transaction waits briefly for the state lock.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import briefing_memory as memory  # noqa: E402

require = memory.require


LOCK_WAIT_SECONDS = 10


def now():
    return datetime.now(timezone.utc)


def state_path(run_id):
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id or ""), "Invalid run id")
    root = Path(os.environ.get("XDG_STATE_HOME") or "~/.local/state").expanduser() / "attention-diet" / "runs"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root / (run_id + ".json")


def write(path, state):
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    with os.fdopen(fd, "w") as stream:
        json.dump(state, stream)
    os.replace(temporary, path)


digest = memory.digest


@contextmanager
def locked_state(run_id):
    """Serialize run-state transactions; `check` is a read-only command.

    A transaction lasts milliseconds, so a collector that finds the state locked waits for it
    instead of failing: two collectors may capture at the same moment.
    """
    path = state_path(run_id)
    # Keep the empty lock inode after finish so a waiting process cannot lock a replacement.
    fd = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.write(b'0')
            lock.flush()
        else:
            import fcntl
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                require(time.monotonic() < deadline, 'Run state is busy; repeat the command')
                time.sleep(0.05)
        try:
            yield path, memory.read_json(path)
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def start(contract, at=None, reserve_seconds=0, concurrent=False):
    limits = contract["run_limits"]
    permitted = contract.get("execution", {}).get("parallelism", {}).get("mode") == "when_independent"
    require(not concurrent or permitted, 'This contract does not permit parallel collection')
    require(type(reserve_seconds) in (int, float) and 0 <= reserve_seconds < limits['elapsed_minutes'] * 60,
            'Finalization reserve must fit inside the total budget')
    state = {"run_id": str(uuid.uuid4()), "contract_id": contract["id"], "revision": contract["revision"],
             "started_at": (at or now()).isoformat(), "elapsed_minutes": limits["elapsed_minutes"],
             "service_minutes": limits.get("service_minutes", {}),
             "allowed_services": sorted({t["service"] for t in contract.get("coverage_threads", [])}) or list(limits.get("service_minutes", {})),
             "services": {}, "phase": "collecting", 'reserve_seconds': reserve_seconds,
             "concurrent": bool(concurrent), "contract_digest": digest(contract)}
    write(state_path(state["run_id"]), state)
    return state


def begin_service(state, service, at=None):
    """Open this service's clock. A sequential run first closes the one in progress; reopening resumes a total.

    In a parallel run the clocks of different services run side by side.
    """
    require(state.get('phase', 'collecting') == 'collecting', 'Collection has been sealed')
    allowed = state.get("allowed_services", list(state["service_minutes"]))
    require(service in allowed or not allowed, "No budget for service " + service)
    moment = at or now()
    if not state.get('concurrent'):
        for name in state["services"]:
            close_service(state, name, moment)
    entry = state["services"].setdefault(service, {"used_seconds": 0.0})
    entry.setdefault("open_since", moment.isoformat())
    entry["last_activity"] = moment.isoformat()
    return state


def close_service(state, service, at=None):
    entry = state['services'].get(service, {})
    if entry.get('open_since'):
        entry['used_seconds'] += ((at or now()) - datetime.fromisoformat(entry.pop('open_since'))).total_seconds()


def seal(state, at=None):
    require(state.get('phase') == 'collecting', 'Collection has already been sealed')
    moment = at or now()
    for service, entry in state['services'].items():
        end = moment
        if state.get('concurrent') and entry.get('last_activity'):
            # A collector that finished early stopped at its last capture, not when the slowest one did.
            end = min(moment, datetime.fromisoformat(entry['last_activity']))
        close_service(state, service, end)
    state['phase'] = 'finalizing'
    return state


def check(state, at=None):
    moment = at or now()
    used = (moment - datetime.fromisoformat(state["started_at"])).total_seconds()
    total = state["elapsed_minutes"] * 60
    report = {"run_id": state["run_id"], "contract_id": state["contract_id"], "used_seconds": round(used), "remaining_seconds": round(max(total - used, 0)),
              "over": used >= total, "services": {}}
    for service, entry in state["services"].items():
        spent = entry["used_seconds"]
        if entry.get("open_since"):
            spent += (moment - datetime.fromisoformat(entry["open_since"])).total_seconds()
        ceiling = state["service_minutes"].get(service)
        report["services"][service] = {"used_seconds": round(spent), "active": "open_since" in entry}
        if ceiling is not None:
            report["services"][service].update(remaining_seconds=round(max(ceiling * 60 - spent, 0)),
                                               over=spent >= ceiling * 60)
    report['phase'] = state.get('phase', 'collecting')
    report['reserve_seconds'] = state.get('reserve_seconds', 0)
    report['collection_over'] = used >= total - report['reserve_seconds']
    report['collection_remaining_seconds'] = round(max(total - report['reserve_seconds'] - used, 0))
    report['stop_services'] = [s for s, e in report['services'].items() if e.get('over') and e['active']]
    report['concurrent'] = bool(state.get('concurrent'))
    # In a parallel run one source reaching its ceiling stops only its own collector (see runtime capture).
    report['stop'] = report['collection_over'] or report['phase'] != 'collecting' or (
        bool(report['stop_services']) and not report['concurrent'])
    return report


def finish(state, at=None):
    require(state.get('phase') == 'finalizing', 'Seal collection before finish')
    report = check(state, at)
    report['phase'] = 'complete'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["start", "service", "service-end", "check", "seal", "finish"])
    parser.add_argument("--contract")
    parser.add_argument("--run")
    parser.add_argument("--service")
    parser.add_argument('--reserve-seconds', type=float, default=0)
    parser.add_argument('--parallel', action='store_true', help='Start only: source clocks run side by side')
    args = parser.parse_args()
    try:
        if args.command == "start":
            require(args.contract, "--contract is required")
            contract = memory.read_json(args.contract)
            from contract import validate
            validate(contract)
            result = check(start(contract, reserve_seconds=args.reserve_seconds, concurrent=args.parallel))
        else:
            require(args.run, '--run is required')
            if args.command == 'check':
                result = check(memory.read_json(state_path(args.run)))
            else:
                with locked_state(args.run) as (path, state):
                    if args.command == 'service':
                        require(args.service, '--service is required')
                        begin_service(state, args.service)
                    elif args.command == 'service-end':
                        require(args.service in state['services'], 'Unknown service')
                        close_service(state, args.service)
                    elif args.command == 'seal':
                        seal(state)
                    result = finish(state) if args.command == 'finish' else check(state)
                    if args.command == 'finish':
                        path.unlink()
                    else:
                        write(path, state)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
