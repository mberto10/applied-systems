#!/usr/bin/env python3
"""Read-only startup plan. Resolve routing once; never create a run or access accounts."""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling helpers, also when loaded by path
import contract as contract_api  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = {'codex_in_app': 'codex.md', 'claude_browser': 'claude.md', 'agent_browser': 'agent-browser.md'}
MEMORY_OPERATIONS = ['list_spaces', 'list_documents', 'get_document', 'add_memory']


def guide_for(route):
    if route['type'] == 'browser':
        return 'integrations/browsers/' + BROWSERS[route['provider']] if route.get('provider') else None
    return 'integrations/connectors.md'


def prepare(path, host):
    path = Path(path).expanduser().resolve()
    contract = contract_api.validate(contract_api.memory.read_json(path))
    # The run skill owns collection rules. Load only integrations used by this run.
    guides = []
    routes, namespaces, browser = [], [], False
    for thread in contract['coverage_threads']:
        access = copy.deepcopy(thread['access'])
        if access['type'] == 'browser':
            browser = True
            provider = access['provider']
            if provider == 'host_default':
                provider = {'codex': 'codex_in_app', 'claude': 'claude_browser'}.get(host)
            supported = provider is not None and not (
                provider == 'codex_in_app' and host != 'codex' or provider == 'claude_browser' and host != 'claude')
            route = {'thread_id': thread['id'], 'type': 'browser', 'provider': provider,
                     'host_supported': supported, 'availability': 'verify_tools_and_account' if supported else 'unavailable'}
            if provider:
                guides.append('integrations/browsers/' + BROWSERS[provider])
        else:
            guides.append('integrations/connectors.md')
            namespaces.append(access['tool_namespace'])
            route = {'thread_id': thread['id'], **access, 'availability': 'verify_tools_and_account'}
        routes.append(route)
    remote = contract['memory_context']['provider'] == 'supermemory'
    if remote:
        guides.append('integrations/codex-adapter.md' if host == 'codex' else 'integrations/memory/supermemory.md')
    paths = [str(ROOT / guide) for guide in dict.fromkeys(guides)]
    contract_api.require(all(Path(p).is_file() for p in paths), 'A selected integration guide is missing')
    # Keep every contract-owned field, including source-specific sublimits and policies.
    # This is the single contract read, not a lossy generated summary of its permissions.
    composition = contract['composition']
    template_base = ROOT if composition['template_path_base'] == 'plugin_root' else path.parent
    template_path = (template_base / composition['template']).resolve()
    contract_api.require(template_path.is_file(), 'Configured composition template is missing')
    helpers = {'runtime': str(ROOT / 'scripts/runtime.py')}
    if browser:
        helpers['browser_extract'] = str(ROOT / 'scripts/browser_extract.js')
    if host == 'codex' and remote:
        helpers['host_adapter'] = str(ROOT / 'scripts/codex_adapter.js')
    # One collector per source service: threads of one service share an account, a tab and a time allowance.
    policy = contract['execution'].get('parallelism', {})
    services = list(dict.fromkeys(t['service'] for t in contract['coverage_threads']))
    execution = {'mode': 'sequential'}
    if policy.get('mode') == 'when_independent' and policy.get('max_workers', 1) > 1 and len(services) > 1:
        execution = {'mode': 'parallel_permitted', 'max_workers': policy['max_workers'],
            'guide': str(ROOT / 'skills/attention-diet/references/parallel.md'), 'collectors': [
            {'service': service,
             'thread_ids': [t['id'] for t in contract['coverage_threads'] if t['service'] == service],
             'guides': [str(ROOT / 'skills/attention-diet/SKILL.md'),
                        *dict.fromkeys(str(ROOT / guide_for(r)) for r in routes
                                       if r['thread_id'] in {t['id'] for t in contract['coverage_threads']
                                                             if t['service'] == service} and guide_for(r))]}
            for service in services]}
    return {'capabilities': ['capture-window-overrun/1', 'structured-exhaustion/1', 'attention-selection/1.2'],
            'plan_version': 'attention-run-plan/2', 'contract_path': str(path),
            'contract_digest': contract_api.digest(contract),
            'contract': contract, 'host': host, 'execution': execution, 'routes': routes, 'read_once': paths,
            'tools': {'source_namespaces': list(dict.fromkeys(namespaces)),
                      'memory_names': ['mcp__supermemory__' + op for op in MEMORY_OPERATIONS]
                      if host == 'codex' and remote else []},
            'helpers': helpers, 'composition_template_path': str(template_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract')
    parser.add_argument('--id')
    parser.add_argument('--host', required=True, choices=['codex', 'claude', 'other'])
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.contract or contract_api.resolve(args.id), args.host), ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
