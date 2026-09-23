#!/usr/bin/env python3
"""The run: plan, start, capture observations, finalize once, finish.

No browser/connector access and no relevance decisions. Provider operations stay with
the agent. Sensitive inputs live in one private workspace, removed by finish.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import briefing  # noqa: E402
import briefing_memory as memory  # noqa: E402
import contract as contract_api  # noqa: E402
import run_budget as budget  # noqa: E402
import run_plan  # noqa: E402
import surface_coverage as coverage  # noqa: E402

require = memory.require


def open_service(state, contract, thread_ids, at=None):
    """The first window or capture for a source starts its clock. Returns that service, if any.

    A sequential run closes the previous source's clock; in a parallel run the clocks overlap.
    """
    threads = {t['id']: t for t in contract['coverage_threads']}
    require(all(t in threads for t in thread_ids), 'Unconfigured thread')
    services = {threads[t]['service'] for t in thread_ids}
    require(len(services) <= 1, 'One batch covers one source service')
    for service in services:
        if state['services'].get(service, {}).get('open_since'):
            state['services'][service]['last_activity'] = (at or budget.now()).isoformat()
        else:
            budget.begin_service(state, service, at)
        return service


def scoped_stop(report, service):
    """Whether the collector of this service should stop; another source's ceiling is not its concern."""
    return bool(report['collection_over'] or report['phase'] != 'collecting'
                or report['services'].get(service, {}).get('over'))


def start(path, reserve_seconds=None, expected_digest=None, parallel=False):
    path = Path(path).expanduser().resolve()
    contract = contract_api.validate(memory.read_json(path))
    require(expected_digest is None or budget.digest(contract) == expected_digest, 'Contract changed since the startup plan')
    reserve = min(60, contract['run_limits']['elapsed_minutes'] * 6) if reserve_seconds is None else reserve_seconds
    state = budget.start(contract, reserve_seconds=reserve, concurrent=parallel)
    workspace = Path(tempfile.mkdtemp(prefix='attention-diet-' + state['run_id'] + '-'))
    state.update(contract_path=str(path), workspace=str(workspace), candidates={}, surfaces={}, notices=[], finalized=False)
    # Reuse these two files for batches and the provider export; no file per item/check.
    contract_api.write_private(workspace / 'input.json', '{}\n')
    contract_api.write_private(workspace / 'history.json', '{}\n')
    budget.write(budget.state_path(state['run_id']), state)
    return {**budget.check(state), 'workspace': str(workspace), 'contract_path': str(path), 'revision': contract['revision']}


def documents(state, contract):
    if contract['memory_context']['provider'] == 'local':
        return None
    data = memory.read_json(Path(state['workspace']) / 'history.json')
    return data or None


def history(state, contract, account):
    return memory.load_history(contract, account, documents(state, contract))


def import_history(state, contract, payload):
    require(state['phase'] == 'collecting', 'Import history before finalization')
    require(contract['memory_context']['provider'] == 'supermemory', 'No remote export for local memory')
    require(isinstance(payload, dict) and payload.get('space') == contract['memory_context']['space'], 'Wrong history space')
    require(type(payload.get('complete')) is bool and isinstance(payload.get('documents'), list), 'Invalid history export')
    ids = set()
    for doc in payload['documents']:
        require(isinstance(doc, dict) and memory.nonempty(doc.get('id')) and doc['id'] not in ids,
                'History needs distinct original document IDs')
        require(type(doc.get('contentTruncated')) is bool and isinstance(doc.get('status'), str)
                and (doc.get('content') is None or isinstance(doc['content'], str)), 'Invalid original document')
        ids.add(doc['id'])
    fingerprint = budget.digest(payload)
    require(not state.get('history_import_digest') or state['history_import_digest'] == fingerprint,
            'History is frozen for this run; do not replace it between accounts')
    if not state.get('history_import_digest'):
        require(not state['candidates'], 'Import history before assessing candidates')
        contract_api.write_private(Path(state['workspace']) / 'history.json', json.dumps(payload, ensure_ascii=False))
        state['history_import_digest'] = fingerprint
    return {'documents': len(ids), 'complete': payload['complete'], 'imported': True}


def observation_window(state, contract, payload, at=None):
    require(state['phase'] == 'collecting', 'Collection has been sealed')
    require(memory.nonempty(payload.get('account_key')), 'Window needs a verified account key')
    maximum = payload.get('max_items')
    require(type(maximum) is int and maximum > 0, 'Request a positive batch size within source-specific sublimits')
    key = payload['thread_id'] + '/' + payload['surface']
    prior = state['surfaces'].get(key, {})
    open_service(state, contract, [payload['thread_id']], at)
    report = budget.check(state, at)
    assessed = coverage.assess(contract, {'thread_id': payload['thread_id'], 'surface': payload['surface'],
        'identifiers': prior.get('identifiers', []), 'more_available': None}, report)
    service = report['services'][assessed['service']]
    remaining = min(report['collection_remaining_seconds'], service.get('remaining_seconds', report['remaining_seconds']))
    limit = min(maximum, assessed['remaining_items']) if assessed['remaining_items'] is not None else maximum
    if assessed['action'] == 'stop' or remaining <= 0 or prior.get('overrun_count', 0):
        limit = 0
    window = {'ticket': uuid.uuid4().hex, 'account_key': payload['account_key'],
              'thread_id': payload['thread_id'], 'surface': payload['surface'], 'limit': limit,
              'seen_identifiers': prior.get('identifiers', []),
              'deadline_ms': int(((at or budget.now()).timestamp() + max(0, remaining)) * 1000)}
    # One outstanding window per source: a new request invalidates that source's stale work,
    # and never the window of a collector working on another source.
    state.setdefault('observation_windows', {})[assessed['service']] = copy.deepcopy(window)
    return window


def capture_window(state, contract, payload, at=None):
    require(state['phase'] == 'collecting', 'Collection has been sealed')
    receipt = state.get('overrun_receipts', {}).get(payload.get('ticket'))
    if receipt:
        require(receipt['digest'] == budget.digest(payload), 'Consumed recovery ticket has a different payload')
        return copy.deepcopy(receipt['result'])
    owner, window = next(((s, w) for s, w in state.get('observation_windows', {}).items()
                          if w['ticket'] == payload.get('ticket')), (None, None))
    require(window, 'Missing, consumed or stale observation window')
    cards = payload.get('cards')
    require(isinstance(cards, list), 'Observation cards must be an array')
    excess = max(0, len(cards) - window['limit'])
    recovery = payload.get('overrun')
    require(not excess or recovery is not None,
            'Extraction exceeded its window; retain every card and resubmit this ticket with overrun cause and evidence')
    if recovery is not None:
        require(excess > 0 and isinstance(recovery, dict)
                and recovery.get('cause') in {'unbounded_observation', 'atomic_tool_response'}
                and memory.nonempty(recovery.get('evidence')), 'Overrun recovery needs excess cards, cause and evidence')
    # An extraction can finish just before its deadline; capture the real observation
    # even if transfer took longer. Coverage still reports the actual elapsed clock.
    prior = state['surfaces'].get(window['thread_id'] + '/' + window['surface'], {})
    require(prior.get('identifiers', []) == window['seen_identifiers'], 'Surface advanced after window creation')
    identifiers, items, read_errors, unreadable_ids = [], [], [], []
    seen = set(window['seen_identifiers'])
    for position, card in enumerate(cards):
        identifier = coverage.identity.count_key(card['identifier'])
        require(identifier not in seen, 'Window must contain only distinct newly observed identities')
        seen.add(identifier)
        identifiers.append(card['identifier'])
        if 'read_error' in card:
            require(memory.nonempty(card['read_error']) and 'basis' not in card,
                    'An unreadable card needs an explanation and cannot be a candidate')
            read_errors.append(card['read_error'])
            unreadable_ids.append(identifier)
        if 'basis' not in card or position >= window['limit']:
            # Rejected cards still count; only eligible candidates need comparison text.
            continue
        number = len(state['candidates']) + len(items) + 1
        while 'c' + str(number) in state['candidates'] or any(i['ref'] == 'c' + str(number) for i in items):
            number += 1
        ref = 'c' + str(number)
        items.append({'ref': ref, 'thread_id': window['thread_id'], 'surface': window['surface'],
                      'identifier': card['identifier'], 'basis': card['basis']})
    allowed = {'more_available', 'evidence', 'loading', 'automatic_selection', 'access_failure',
               'retrieval_limit', 'retrieval_stalled', 'exhaustion', 'novelty_boundary', 'notices'}
    require('more_available' in payload, 'Observation needs availability evidence')
    observation = {k: payload[k] for k in allowed if k in payload}
    observation.update(thread_id=window['thread_id'], surface=window['surface'], identifiers=identifiers,
                       inspection_errors=read_errors, unreadable_identifiers=unreadable_ids)
    if excess:
        observation['overflow_identifiers'] = identifiers[window['limit']:]
    staged = copy.deepcopy(state)
    # Direct capture cannot bypass a live ticket. Consume only on this staged copy.
    del staged['observation_windows'][owner]
    result = collect_batch(staged, contract, {'account_key': window['account_key'], 'items': items,
                                           'surfaces': [observation]}, at)
    result['references'] = [{'identifier': item['identifier'], 'ref': item['ref']} for item in items]
    if 'next_max_items' in payload:
        maximum = payload['next_max_items']
        require(type(maximum) is int and maximum > 0, 'Next batch size must be positive')
        result['next_window'] = None
        if not result['stop'] and result['coverage'][0]['action'] != 'stop':
            following = observation_window(staged, contract, {k: window[k] for k in
                ('account_key', 'thread_id', 'surface')} | {'max_items': maximum}, at)
            # The browser already holds identities and scope. Return only the next allowance.
            if following['limit'] > 0:
                result['next_window'] = {k: following[k] for k in ('ticket', 'limit', 'deadline_ms')}
    if excess:
        result['overrun'] = {'count': excess, 'disposition': 'counted_without_candidate_references'}
        result['next_window'] = None
        staged.setdefault('overrun_receipts', {})[window['ticket']] = {
            'digest': budget.digest(payload), 'cause': recovery['cause'], 'evidence': recovery['evidence'],
            'result': copy.deepcopy(result)}
    state.clear()
    state.update(staged)
    return result


def transfer_receipt(state, payload):
    bundle = prepared_memory(state)
    account = payload['account_key']
    require(bundle['provider'] == 'supermemory' and account in state['memory_digests'], 'No remote artifact for account')
    receipts = state.setdefault('transfers', {})
    action = payload['action']
    require(action in {'begin', 'ack', 'status'}, 'Unknown transfer action')
    if action == 'begin' and account not in receipts:
        # Persisted before the connector call; an interrupted/uncertain save is never
        # retried automatically. This tracks the upload, not delivery or reading.
        receipts[account] = {'attempted': True, 'document_id': None}
        return {**receipts[account], 'may_save': True}
    if action == 'ack':
        require(account in receipts and memory.nonempty(payload.get('document_id')), 'Missing upload receipt')
        prior = receipts[account]['document_id']
        require(prior in (None, payload['document_id']), 'Cannot replace an upload receipt')
        receipts[account]['document_id'] = payload['document_id']
    return {**receipts.get(account, {'attempted': False, 'document_id': None}), 'may_save': False,
            'verification': state['storage'][account]}


def collect_batch(state, contract, payload, at=None):
    staged = copy.deepcopy(state)
    result = _collect_batch(staged, contract, payload, at)
    state.clear()
    state.update(staged)
    return result


def _collect_batch(state, contract, payload, at=None):
    require(state['phase'] == 'collecting', 'Collection has been sealed')
    require(isinstance(payload, dict), 'Batch input must be an object')
    threads = {t['id']: t for t in contract['coverage_threads']}
    account = payload.get('account_key')
    require(memory.nonempty(account), 'Batch needs the authenticated account key')
    service = open_service(state, contract, [o['thread_id'] for o in payload.get('items', []) + payload.get('surfaces', [])], at)
    report = budget.check(state, at)
    allowed_ids = {}
    overflows = {}
    for observed in payload.get('surfaces', []):
        key = observed['thread_id'] + '/' + observed['surface']
        require(key not in allowed_ids, 'One checkpoint per surface in a batch')
        require('inspected_count' not in observed, 'Supply observed identifiers, not a manually counted total')
        require('identifiers' in observed, 'Surface checkpoints need observed identifiers')
        require(not any(w['thread_id'] == observed['thread_id'] and w['surface'] == observed['surface']
                        for w in state.get('observation_windows', {}).values()),
                'Use capture-window for a surface with an outstanding ticket, including overrun recovery')
        prior = state['surfaces'].get(key, {})
        old = prior.get('identifiers', [])
        fresh = [i for i in coverage.identity.distinct_identifiers(observed['identifiers']) if i not in old]
        allowance = coverage.assess(contract, {'thread_id': observed['thread_id'], 'surface': observed['surface'],
            'identifiers': old, 'more_available': None}, report)['remaining_items']
        overflow = set(prior.get('overflow_identifiers', []))
        overflow.update(coverage.identity.distinct_identifiers(observed.get('overflow_identifiers', [])))
        require(overflow <= set(old + fresh), 'Overflow identities must be observed on this surface')
        if prior.get('overrun_count', 0):
            overflow.update(fresh)
        elif allowance is not None:
            overflow.update(fresh[allowance:])
        overflows[key] = [i for i in old + fresh if i in overflow]
        allowed_ids[key] = set(old + fresh) - overflow
    items, refs = [], []
    for observed in payload.get('items', []):
        thread = threads.get(observed['thread_id'])
        require(thread and observed['surface'] in thread['surfaces'], 'Unconfigured item surface')
        key = observed['thread_id'] + '/' + observed['surface']
        require(key in allowed_ids, 'Candidates need a surface checkpoint in the same batch')
        if coverage.identity.count_key(observed['identifier']) not in allowed_ids[key]:
            require(coverage.identity.count_key(observed['identifier']) in overflows[key],
                    'Candidate is missing from inspected surface identities')
            continue  # Count overflow, but never compare or save its private text.
        ref = observed['ref']
        require(memory.nonempty(ref) and ref not in refs, 'Need distinct nonempty local references')
        item = {'service': thread['service'], 'identifier': coverage.identity.canonical_identifier(observed['identifier']),
                **memory.fingerprint_metadata(observed['basis'])}
        captured = {'account_key': account, 'thread_id': thread['id'], 'surface': observed['surface'], 'item': item}
        prior = state['candidates'].get(ref)
        require(prior is None or all(prior[k] == v for k, v in captured.items()), 'Cannot overwrite an observed item reference')
        state['candidates'][ref] = captured
        items.append(item)
        refs.append(ref)
    # Keep post and conversation evidence separate, including within one service.
    # Repeated observed cards remain one version per policy, not per reference.
    grouped = {False: {}, True: {}}
    modes = {ref: threads[state['candidates'][ref]['thread_id']].get('content') == 'public_posts'
             for ref in refs}
    for ref, item in zip(refs, items):
        grouped[modes[ref]][memory.item_key(item)] = item
    loaded = history(state, contract, account)
    compared = {mode: memory.compare(loaded, list(group.values()), public_posts=mode)
                for mode, group in grouped.items()}
    new = {mode: {memory.item_key(i) for i in result['new_items']} for mode, result in compared.items()}
    uncertain = {mode: {memory.item_key(i) for i in result['uncertain_items']} for mode, result in compared.items()}
    warnings = sorted({warning for result in compared.values() for warning in result['warnings']})
    decisions = {}
    for ref, item in zip(refs, items):
        mode, key = modes[ref], memory.item_key(item)
        status = 'new' if key in new[mode] else 'uncertain' if key in uncertain[mode] else 'already_briefed'
        state['candidates'][ref]['novelty'] = status
        decisions[ref] = status
    state['notices'] = list(dict.fromkeys(state['notices'] + warnings))
    results = []
    for observed in payload.get('surfaces', []):
        require('inspected_count' not in observed, 'Supply observed identifiers, not a manually counted total')
        require('identifiers' in observed, 'Surface checkpoints need observed identifiers (an empty array is valid)')
        if observed.get('more_available') is False and observed.get('loading') is not True:
            require(memory.nonempty(observed.get('evidence')), 'Exhaustion needs observed evidence, not an empty/loading frame')
        key = observed['thread_id'] + '/' + observed['surface']
        prior = state['surfaces'].get(key, {})
        identifiers = list(dict.fromkeys(prior.get('identifiers', []) + coverage.identity.distinct_identifiers(observed['identifiers'])))
        observation = {**observed, 'identifiers': identifiers, 'overrun_count': len(overflows[key])}
        # Once an automatic selection is observed, later pages cannot erase its warning.
        if prior.get('read_state_effect') == 'unknown':
            observation['automatic_selection'] = True
        assessed = coverage.assess(contract, observation, report)
        assessed['identifiers'] = identifiers
        assessed['overflow_identifiers'] = overflows[key]
        assessed['overrun_count'] = len(overflows[key])
        if assessed['overrun_count']:
            assessed['action'] = 'stop'
            assessed['remaining_items'] = 0
        assessed['within_allowance_count'] = len(identifiers) - len(overflows[key])
        assessed['observation_evidence'] = observed.get('evidence', prior.get('observation_evidence', ''))
        assessed['notices'] = list(dict.fromkeys(prior.get('notices', []) + observed.get('notices', []) + assessed['notices']))
        errors = observed.get('inspection_errors', [])
        require(isinstance(errors, list) and all(memory.nonempty(e) for e in errors),
                'Inspection errors need observed explanations')
        assessed['inspection_errors'] = list(dict.fromkeys(prior.get('inspection_errors', []) + errors))
        assessed['unreadable_identifiers'] = list(dict.fromkeys(prior.get('unreadable_identifiers', []) +
            coverage.identity.distinct_identifiers(observed.get('unreadable_identifiers', []))))
        require(set(assessed['unreadable_identifiers']) <= set(identifiers), 'Unreadable identities must be observed')
        state['surfaces'][key] = assessed
        results.append({k: v for k, v in assessed.items() if k not in {'identifiers', 'overflow_identifiers', 'unreadable_identifiers', 'coverage_note', 'inspection_errors'}})
    return {'decisions': decisions, 'coverage': results, 'warnings': warnings,
            'stop': scoped_stop(report, service), 'budget': report, 'baseline': compared[False]['baseline']}


def selected_coverage(state, contract):
    rows = []
    for thread in contract['coverage_threads']:
        for surface in thread['surfaces']:
            source = state['surfaces'].get(thread['id'] + '/' + surface)
            if source is None:
                rows.append({'thread_id': thread['id'], 'surface': surface, 'status': 'not_checked',
                    'inspected_count': 0, 'more_available': None, 'stop_reason': 'not_checked',
                    'evidence': 'No verified observation was captured for this surface.',
                    'boundary': 'unknown', 'exhaustion': None, 'overrun_count': 0, 'within_allowance_count': 0,
                    'unreadable_count': 0, 'has_unreadable_content': False})
                continue
            reason = source['stop_reason'] or 'agent_stopped_early'
            errors = source.get('inspection_errors', [])
            if errors and reason in {'exhausted_results', 'novelty_boundary'}:
                reason = 'source_limit'  # The list ended, but some identified cards were unreadable.
            sample = thread.get('collection', {}).get(surface, {}).get('mode') == 'sample'
            status = ('checked' if reason in {'exhausted_results', 'novelty_boundary'} and not sample else
                      'unavailable' if reason == 'access_failure' and source['inspected_count'] == 0 else 'partial')
            rows.append({k: source[k] for k in ('thread_id', 'surface', 'inspected_count', 'more_available',
                                                'read_state_effect', 'notices')} | {
                'status': status, 'stop_reason': reason,
                'boundary': source.get('boundary', 'unknown'),
                'exhaustion': source.get('exhaustion'),
                'unreadable_count': len(source.get('unreadable_identifiers', [])),
                'has_unreadable_content': bool(errors),
                'overrun_count': source.get('overrun_count', 0),
                'within_allowance_count': source.get('within_allowance_count', source['inspected_count']),
                'evidence': ' '.join(filter(None, [source.get('observation_evidence'), source['evidence'], *errors])) or
                            'Collection stopped without a supported stopping boundary.'})
    return rows


def finalize(state, contract, draft):
    require(not state.get('finalized'), 'Selection already finalized; do not reselect after memory preparation')
    require(set(draft) <= {'title', 'overview', 'entries', 'notices'}, 'Supply editorial fields only; runtime owns scope and evidence')
    if state['phase'] == 'collecting':
        budget.seal(state)  # Finalizing ends collection; later captures are rejected.
    entries = []
    for original in draft['entries']:
        entry = copy.deepcopy(original)
        refs = entry.pop('item_refs')
        require(isinstance(refs, list) and refs, 'Every entry needs captured item references')
        require('items' not in entry, 'Use item_refs instead of copying hashes')
        captures = [state['candidates'][ref] for ref in refs]
        for key in ('account_key', 'thread_id', 'surface'):
            entry.setdefault(key, captures[0][key])
        entry.setdefault('id', 'e' + str(len(entries) + 1))
        if 'section' not in entry:
            sections = [s for s in contract['composition']['sections'] if s != 'overview']
            require(len(sections) == 1, 'Choose a configured section when more than one is available')
            entry['section'] = sections[0]
        for captured in captures:
            require(captured['novelty'] == 'new', 'Only compared new items may enter the selection')
            require(all(captured[k] == entry[k] for k in ('account_key', 'thread_id', 'surface')),
                    'Entry must preserve the captured account and surface')
            row = state['surfaces'].get(entry['thread_id'] + '/' + entry['surface'], {})
            require(coverage.identity.count_key(captured['item']['identifier']) not in row.get('overflow_identifiers', []),
                    'Overflow observations cannot enter the selection')
            require(coverage.identity.count_key(captured['item']['identifier']) in row.get('identifiers', []),
                    'Selected item is missing from inspected surface identities')
        entry['items'] = [c['item'] for c in captures]
        entries.append(entry)
    record = {'schema_version': 'attention-selection/1.2', 'contract_id': contract['id'],
              'contract_revision': contract['revision'], 'run_id': state['run_id'],
              'created_at': budget.now().isoformat(), 'title': draft['title'], 'overview': draft['overview'],
              'entries': entries, 'coverage': selected_coverage(state, contract),
              'notices': list(dict.fromkeys(state['notices'] + draft.get('notices', [])))}
    result = briefing.finalize(contract, record, Path(state['contract_path']).parent)
    records = []
    for group in result['memory_payloads']:
        loaded = history(state, contract, group['account_key'])
        artifact = memory.build_record(contract, group['account_key'], group['payload'], loaded)
        records.append({'account_key': group['account_key'], 'version_id': artifact['version_id'],
                        'content': memory.encode(artifact)})
    workspace = Path(state['workspace'])
    suffix = '.md' if contract['composition']['interface'] == 'agent_summary' else '.html'
    output = workspace / ('briefing' + suffix)
    contract_api.write_private(output, result['rendered'])
    bundle = {'provider': contract['memory_context']['provider'], 'artifacts': records}
    if bundle['provider'] == 'supermemory':
        bundle['space'] = contract['memory_context']['space']
    contract_api.write_private(workspace / 'memory.json', json.dumps(bundle, ensure_ascii=False))
    state.update(finalized=True, output_path=str(output), selection=record,
                 storage={r['account_key']: {'status': 'not_attempted'} for r in records},
                 memory_target={k: bundle[k] for k in ('provider', 'space') if k in bundle},
                 memory_digests={r['account_key']: budget.digest(memory.decode(r['content'])) for r in records})
    result = {'output_path': str(output), 'memory_path': str(workspace / 'memory.json'),
              'memory_versions': [r['version_id'] for r in records], 'entries': len(entries)}
    if bundle['provider'] == 'local':
        result['memory'] = save_local_memory(state, contract, bundle)
    return result


def save_local_memory(state, contract, bundle):
    """Idempotent. A failed save never withholds the briefing: finish reports limited continuity."""
    saved = []
    for artifact in bundle['artifacts']:
        try:
            saved.append(memory.save_local(contract, memory.decode(artifact['content'])))
            state['storage'][artifact['account_key']] = {'status': 'verified'}
        except (OSError, ValueError) as error:
            state['storage'][artifact['account_key']] = {
                'status': 'failed', 'notice': 'Briefing memory could not be saved (' + str(error) + '); continuity is limited.'}
    return {'saved': saved, 'storage': {k: v['status'] for k, v in state['storage'].items()}}


def prepared_memory(state):
    require(state.get('finalized'), 'Finalize before saving memory')
    bundle = memory.read_json(Path(state['workspace']) / 'memory.json')
    require({k: bundle[k] for k in ('provider', 'space') if k in bundle} == state['memory_target'],
            'Prepared memory target changed after finalization')
    require(len(bundle['artifacts']) == len(state['memory_digests']) and
            {a['account_key'] for a in bundle['artifacts']} == set(state['memory_digests']),
            'Prepared memory account set changed after finalization')
    for artifact in bundle['artifacts']:
        record = memory.decode(artifact['content'])
        require(record['version_id'] == artifact['version_id'] and record['account_key'] == artifact['account_key']
                and record['contract_id'] == state['contract_id'] and record['contract_revision'] == state['revision'],
                'Prepared memory has mismatched scope')
        require(budget.digest(record) == state['memory_digests'][artifact['account_key']],
                'Prepared memory changed after finalization')
    return bundle


def verify_memory(state, payload):
    bundle = prepared_memory(state)
    account = payload['account_key']
    artifact = next((a for a in bundle['artifacts'] if a['account_key'] == account), None)
    require(artifact is not None, 'No prepared artifact for this account')
    result = memory.verify_artifact(artifact['content'], payload['document'])
    state['storage'][account] = result
    return result


def finish(state, contract, out=None, notices=(), retain=False):
    require(state.get('finalized'), 'Finalize output and prepare memory before finish')
    report = budget.finish(state)
    rendered = Path(state['output_path']).read_text()
    notices = list(notices)
    for result in state.get('storage', {}).values():
        if result['status'] != 'verified':
            notices.append(result.get('notice', 'Briefing memory storage has not been verified; continuity is limited.'))
    if notices:
        record = copy.deepcopy(state['selection'])
        record['notices'].extend(notices)
        rendered = briefing.render(contract, record, contract_dir=Path(state['contract_path']).parent)
    if contract['composition']['interface'] != 'agent_summary':
        require(out, 'HTML delivery requires --out outside the temporary workspace')
    workspace = Path(state['workspace'])
    if out:
        target = Path(out).expanduser().resolve()
        require(not target.is_relative_to(workspace.resolve()), 'Delivery output must be outside the temporary workspace')
        require(not target.exists(), 'Delivery output already exists; choose a new filename')
        contract_api.write_private(target, rendered)
    result = {'budget': report, 'entries': len(state['selection']['entries']),
              'coverage': state['selection']['coverage'], 'output_path': str(target) if out else None,
              'rendered': rendered if contract['composition']['interface'] == 'agent_summary' else None}
    if retain:
        result['retained_workspace'] = str(workspace)
    else:
        # Delete only known run-owned files. Never recursively delete an arbitrary directory.
        require(workspace.name.startswith('attention-diet-' + state['run_id'] + '-') and not workspace.is_symlink(),
                'Workspace ownership could not be verified')
        for name in ('input.json', 'history.json', 'memory.json', 'briefing.md', 'briefing.html'):
            (workspace / name).unlink(missing_ok=True)
        workspace.rmdir()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'start', 'history', 'import-history', 'window', 'capture-window',
                                            'capture', 'finalize', 'memory', 'transfer', 'verify-memory', 'finish'])
    parser.add_argument('--host', choices=['codex', 'claude', 'other'], help='Plan only: the current agent host')
    parser.add_argument('--contract')
    parser.add_argument('--id')
    parser.add_argument('--run')
    parser.add_argument('--account')
    parser.add_argument('--expected-digest')
    parser.add_argument('--input', help='JSON file, - for stdin; default is the reusable workspace input.json')
    parser.add_argument('--out')
    parser.add_argument('--notice', action='append', default=[])
    parser.add_argument('--retain', action='store_true', help='Explicit diagnostic retention; otherwise temporary files are deleted')
    parser.add_argument('--parallel', action='store_true', help='Start only: collectors share this run, one per source service')
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            require(args.host, '--host is required')
            result = run_plan.prepare(args.contract or contract_api.resolve(args.id), args.host)
        elif args.command == 'start':
            result = start(args.contract or contract_api.resolve(args.id), expected_digest=args.expected_digest,
                           parallel=args.parallel)
        else:
            require(args.run, '--run is required')
            with budget.locked_state(args.run) as (path, state):
                contract = memory.read_json(state['contract_path'])
                require(budget.digest(contract) == state['contract_digest'], 'Contract changed during this run')
                payload = (json.load(sys.stdin) if args.input == '-' else memory.read_json(
                    args.input or str(Path(state['workspace']) / 'input.json'))) if args.command in {
                        'capture', 'finalize', 'verify-memory', 'import-history', 'window', 'capture-window', 'transfer'} else None
                if args.command == 'history':
                    result = memory.context(history(state, contract, args.account), contract)
                elif args.command == 'import-history':
                    result = import_history(state, contract, payload)
                elif args.command == 'window':
                    result = observation_window(state, contract, payload)
                elif args.command == 'capture-window':
                    result = capture_window(state, contract, payload)
                elif args.command == 'transfer':
                    result = transfer_receipt(state, payload)
                elif args.command == 'capture':
                    result = collect_batch(state, contract, payload)
                elif args.command == 'finalize':
                    result = finalize(state, contract, payload)
                elif args.command == 'memory':
                    bundle = prepared_memory(state)
                    # Local memory was saved by finalize; this repeats it harmlessly. Remote artifacts
                    # come back in the exact shape of memory.json, with no second extraction format.
                    result = save_local_memory(state, contract, bundle) if bundle['provider'] == 'local' else bundle
                elif args.command == 'verify-memory':
                    result = verify_memory(state, payload)
                else:
                    result = finish(state, contract, args.out, args.notice, args.retain)
                if args.command == 'finish' and not args.retain:
                    path.unlink()
                else:
                    budget.write(path, state)
        print(json.dumps(result, ensure_ascii=False))  # Compact: the reader is a model.
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
