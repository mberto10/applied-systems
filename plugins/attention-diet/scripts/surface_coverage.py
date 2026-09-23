#!/usr/bin/env python3
"""Decide whether any configured surface has a supported stopping reason."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import item_identity as identity  # noqa: E402


def exhaustion_evidence(observation, count):
    """Validate the collector's explicit evidence, never infer an end from missing UI."""
    value = observation.get('exhaustion')
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('kind') not in {
            'explicit_end_marker', 'authoritative_total_matched', 'documented_connector_end'}:
        raise ValueError('Exhaustion needs an explicit marker, authoritative total, or documented connector end')
    if set(value) - {'kind', 'evidence', 'total'}:
        raise ValueError('Unknown exhaustion evidence fields')
    if 'total' in value and (type(value['total']) is not int or value['total'] < 0):
        raise ValueError('Exhaustion total must be a nonnegative integer')
    if not isinstance(value.get('evidence'), str) or not value['evidence'].strip():
        raise ValueError('Exhaustion needs observed evidence')
    if value['kind'] == 'authoritative_total_matched':
        if type(value.get('total')) is not int or value['total'] != count:
            raise ValueError('Authoritative total must match distinct inspected identities')
    return value


def assess(contract, observation, budget):
    surface = observation["surface"]
    thread = next((t for t in contract["coverage_threads"] if t["id"] == observation["thread_id"]), None)
    if thread is None:
        raise ValueError("Thread is not configured")
    if surface not in thread["surfaces"]:
        raise ValueError("Surface is not configured")
    count = (len(identity.distinct_identifiers(observation['identifiers']))
             if 'identifiers' in observation else observation["inspected_count"])
    if 'identifiers' in observation and 'inspected_count' in observation and observation['inspected_count'] != count:
        raise ValueError('Inspected count differs from distinct observed item IDs')
    more = observation["more_available"]
    if type(count) is not int or count < 0 or (more is not None and type(more) is not bool):
        raise ValueError("Need an inspected count and true/false/null availability")
    exhaustion = exhaustion_evidence(observation, count)
    unverified_end = more is False and exhaustion is None and observation.get('loading') is not True
    if observation.get('loading') is True or unverified_end:
        more = None  # Missing controls and loading frames cannot establish exhaustion.
    boundary = 'exhausted_results' if more is False else 'unknown'
    novelty = observation.get('novelty_boundary', {})
    if (more is not False and novelty.get('ordering_verified') is True
            and novelty.get('covered_range_verified') is True
            and isinstance(novelty.get('evidence'), str) and novelty['evidence'].strip()
            and observation.get('loading') is not True):
        boundary = 'verified_prior_range'
    if budget.get("contract_id", contract["id"]) != contract["id"]:
        raise ValueError("Budget belongs to another contract")
    service = budget.get("services", {}).get(thread["service"], {})
    if service.get("active") is not True:
        raise ValueError("Check the budget while the source service is still active")
    policy = thread.get("collection", {}).get(surface, {"mode": "scan"})
    # run_limits.items_per_surface caps every surface; a surface's own max_items can only lower it.
    ceilings = [n for n in (contract["run_limits"].get("items_per_surface"), policy.get("max_items")) if n is not None]
    ceiling = min(ceilings) if ceilings else None
    reason = None
    evidence = ""
    retrieval_limit = observation.get("retrieval_limit")
    if retrieval_limit is not None and (not isinstance(retrieval_limit, str) or not retrieval_limit.strip()):
        raise ValueError("retrieval_limit needs concrete evidence of the retrieval constraint")
    stalled = observation.get('retrieval_stalled')
    if stalled is not None and (not isinstance(stalled, str) or not stalled.strip()):
        raise ValueError('retrieval_stalled needs concrete no-progress evidence')
    if stalled or retrieval_limit or observation.get('access_failure'):
        more, boundary = None, 'unknown'
    if observation.get("access_failure"):
        reason, evidence = "access_failure", str(observation["access_failure"])
    elif budget.get("over") is True or service.get("over") is True or budget.get('collection_over') is True:
        reason, evidence = "time_ceiling", "Measured run or service time ceiling reached"
        if budget.get('collection_over') and not budget.get('over') and not service.get('over'):
            evidence = 'Collection window reached; remaining run time is reserved for finalization'
    elif ceiling is not None and count >= ceiling:
        if policy.get("mode") == "sample" and count >= policy["max_items"]:
            reason, evidence = "sample_ceiling", "Contract sample ceiling reached; coverage is sampled"
        else:
            reason, evidence = "item_ceiling", "Contract item ceiling reached"
    elif observation.get('overrun_count', 0):
        reason, evidence = 'window_overrun', 'Observation exceeded its allowance; further collection stopped'
    elif retrieval_limit:
        reason, evidence = "source_limit", retrieval_limit
    elif stalled:
        reason, evidence = 'retrieval_stalled', stalled
    elif more is False:
        reason, evidence = "exhausted_results", "No further results available in this surface"
    elif boundary == 'verified_prior_range':
        reason, evidence = 'novelty_boundary', novelty['evidence']
    result = {"thread_id": thread["id"], "service": thread["service"], "surface": surface, "inspected_count": count, "more_available": more,
              "action": "stop" if reason else "load_more" if more is True else "inspect_availability",
              "stop_reason": reason, "evidence": evidence}
    result["read_state_effect"] = ("unknown" if observation.get("automatic_selection") is True
                                   else "not_assessed")
    result['item_ceiling'] = ceiling
    result['remaining_items'] = max(0, ceiling - count) if ceiling is not None else None
    result['boundary'] = boundary
    result['exhaustion'] = exhaustion if more is False else None
    result['unverified_end'] = unverified_end
    result['notices'] = []
    if ceiling is not None and count > ceiling:
        result['notices'].append(f'Inspection exceeded the configured {ceiling}-item ceiling by {count - ceiling}; '
                                 'this was a collection overrun, not a source retrieval limit.')
    result["coverage_note"] = (f"Inspected {count} items; more results " +
                               ("available" if more is True else "unavailable" if more is False else "unknown") +
                               "; " + (evidence if reason else "no supported stopping reason yet"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--input", required=True, help="JSON with observation and the current budget report")
    parser.add_argument('--run', help='Read the actual run clock; input contains observation only')
    args = parser.parse_args()
    try:
        with open(args.contract) as f:
            contract = json.load(f)
        payload = json.load(sys.stdin) if args.input == '-' else json.loads(Path(args.input).read_text())
        from contract import validate
        validate(contract)
        if args.run:
            import run_budget
            state = run_budget.memory.read_json(run_budget.state_path(args.run))
            if run_budget.digest(contract) != state['contract_digest']:
                raise ValueError('Contract changed during collection')
            report = run_budget.check(state)
        else:
            report = payload['budget']
        print(json.dumps(assess(contract, payload["observation"], report), indent=2))
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
