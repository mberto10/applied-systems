import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('benchmark_run', Path(__file__).parents[1] / 'scripts/benchmark_run.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def test_counts_text_without_serialization_overhead_and_stops_at_turn_end(self):
        events = [
            ('event_msg', {'type': 'task_started'}),
            ('turn_context', {'model': 'test-model'}),
            ('response_item', {'type': 'custom_tool_call', 'name': 'exec'}),
            ('response_item', {'type': 'custom_tool_call_output', 'output': [
                {'type': 'input_text', 'text': '12345'}, {'type': 'image', 'data': 'ignored'}]}),
            ('event_msg', {'type': 'token_count', 'info': {'total_token_usage': {
                'input_tokens': 100, 'cached_input_tokens': 60, 'output_tokens': 10}}}),
            ('event_msg', {'type': 'task_complete'}),
            ('event_msg', {'type': 'task_started'}),
            ('response_item', {'type': 'function_call', 'name': 'js'}),
            ('event_msg', {'type': 'token_count', 'info': {'total_token_usage': {
                'input_tokens': 160, 'cached_input_tokens': 100, 'output_tokens': 20}}})]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.jsonl'
            path.write_text('\n'.join(json.dumps({'timestamp': f'2026-09-19T12:00:{i:02d}Z',
                                                 'type': kind, 'payload': payload})
                                       for i, (kind, payload) in enumerate(events)))
            first, second = benchmark.measure(path), benchmark.measure(path, 2)
        self.assertEqual(first['tool_output_characters'], 5)
        self.assertEqual(first['model_tool_calls'], 1)
        self.assertEqual(first['elapsed_seconds'], 5)
        self.assertEqual(first['uncached_input_tokens'], 40)
        self.assertTrue(first['complete'])
        self.assertEqual(second['uncached_input_tokens'], 20)
        self.assertFalse(second['complete'])


if __name__ == '__main__':
    unittest.main()
