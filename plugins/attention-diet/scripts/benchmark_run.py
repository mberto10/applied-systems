#!/usr/bin/env python3
"""Read-only metrics for one Codex rollout turn; prints no source text or account data."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


def events(path):
    with Path(path).open() as stream:
        for line in stream:
            yield json.loads(line)


def measure(path, turn=1):
    index, active, complete = 0, False, False
    started = ended = last = model = None
    calls, output_chars = Counter(), 0
    previous, initial, usage = {}, {}, {}
    samples = 0
    for event in events(path):
        payload = event.get('payload', {})
        kind = payload.get('type')
        if event['type'] == 'event_msg' and kind == 'task_started':
            index += 1
            active = index == turn
            if active:
                started = event['timestamp']
                initial = previous.copy()
        if event['type'] == 'event_msg' and kind == 'token_count':
            total = (payload.get('info') or {}).get('total_token_usage')
            if total:
                previous = total
                if active:
                    usage = {key: value - initial.get(key, 0) for key, value in total.items()}
                    samples += 1
        if not active:
            continue
        last = event['timestamp']
        if event['type'] == 'turn_context':
            model = payload.get('model') or model
        if event['type'] == 'response_item':
            if kind in {'function_call', 'custom_tool_call'}:
                calls[payload['name']] += 1
            elif kind in {'function_call_output', 'custom_tool_call_output'}:
                output = payload.get('output', '')
                output_chars += (len(output) if isinstance(output, str) else
                                 sum(len(block.get('text', '')) for block in output if isinstance(block, dict)))
        if event['type'] == 'event_msg' and kind == 'task_complete':
            ended, complete = event['timestamp'], True
            break
    if not started:
        raise ValueError('Requested turn was not found')
    elapsed = (datetime.fromisoformat((ended or last).replace('Z', '+00:00')) -
               datetime.fromisoformat(started.replace('Z', '+00:00'))).total_seconds()
    return {'complete': complete, 'started_at': started, 'ended_at': ended, 'elapsed_seconds': round(elapsed, 3),
            'model': model, 'model_tool_calls': sum(calls.values()), 'calls_by_name': dict(calls),
            'tool_output_characters': output_chars, 'model_samples': samples,
            'uncached_input_tokens': usage.get('input_tokens', 0) - usage.get('cached_input_tokens', 0),
            'usage': usage}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rollout')
    parser.add_argument('--turn', type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(measure(args.rollout, args.turn), indent=2))
