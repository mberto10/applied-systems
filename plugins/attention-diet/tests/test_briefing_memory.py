import copy
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("briefing_memory", ROOT / "scripts/briefing_memory.py")
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.contract = {"id": "test-contract", "revision": 3, "memory_context": {
            "provider": "local", "directory": self.tmp.name,
            "purpose": "avoid_repeating_previously_briefed_items", "on_unavailable": "continue_with_notice"}}
        self.a = {"service": "private-source", "identifier": "conversation-1",
                  **memory.fingerprint_metadata({"incoming_id": "message-1"})}
        self.b = {**self.a, "change_fingerprint": memory.fingerprint({"incoming_id": "message-2"})}

    def history(self, account="test-account"):
        return memory.load_history(self.contract, account)

    def save(self, version, items, account="test-account", summary="A brief summary."):
        record = memory.build_record(self.contract, account,
                                     {"version_id": version, "items": items,
                                      "coverage": "messages partial", "summary": summary}, self.history(account))
        return record, memory.save_local(self.contract, record)

    def test_consecutive_runs_and_quiet_day(self):
        self.assertEqual(memory.compare(self.history(), [self.a])["new_items"], [self.a])
        first, _ = self.save("run-1", [self.a])
        quiet, _ = self.save("run-2", [], summary="Nothing new.")
        self.assertEqual(quiet["previous_version"], first["version_id"])
        result = memory.compare(self.history(), [self.a, self.b])
        self.assertEqual(result["new_items"], [self.b])
        self.assertEqual(result["already_briefed_count"], 1)

    def test_observed_but_not_included_stays_new(self):
        self.save("run-1", [self.a])
        self.assertEqual(memory.compare(self.history(), [self.b])["new_items"], [self.b])

    def test_account_contract_and_service_isolation(self):
        self.save("run-1", [self.a])
        self.assertEqual(memory.compare(self.history("other-account"), [self.a])["new_items"], [self.a])
        other = {**self.contract, "id": "other-contract"}
        self.assertFalse(memory.load_history(other, "test-account")["records"])
        other_item = {**self.a, "service": "another-service"}
        self.assertEqual(memory.compare(self.history(), [other_item])["new_items"], [other_item])

    def test_round_trip_and_permissions(self):
        record, path = self.save("run-1", [self.a])
        self.assertEqual(memory.decode(Path(path).read_text()), record)
        self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(Path(path).parent.stat().st_mode), 0o700)

    def test_retry_and_conflict(self):
        first, path = self.save("run-1", [self.a])
        retry, retry_path = self.save("run-1", [self.a])
        self.assertEqual((first, path), (retry, retry_path))
        with self.assertRaises(ValueError):
            self.save("run-1", [self.b])
        self.assertEqual(memory.decode(Path(path).read_text()), first)

    def test_parallel_versions_are_both_retained(self):
        empty = self.history()
        records = [memory.build_record(self.contract, "test-account", {
            "version_id": "parallel-" + str(i), "items": [item], "summary": "Briefed.", "coverage": "partial"
        }, empty) for i, item in enumerate([self.a, self.b])]
        with ThreadPoolExecutor() as pool:
            list(pool.map(lambda r: memory.save_local(self.contract, r), records))
        self.assertEqual(memory.compare(self.history(), [self.a, self.b])["new_items"], [])

    def test_fingerprint_ignores_whitespace_and_rejects_badges(self):
        one = memory.fingerprint({"sender": "Alex", "text": "Meeting  tomorrow?"})
        two = memory.fingerprint({"sender": "Alex", "text": "Meeting\ntomorrow?"})
        self.assertEqual(one, two)
        with self.assertRaises(ValueError):
            memory.fingerprint({"sender": "Alex", "text": "Hi", "unread": True})
        with self.assertRaises(ValueError):
            memory.fingerprint({"sender": "Alex", "text": "Hi", "occurred_at": "2 hours ago"})
        self.assertNotEqual(one, memory.fingerprint({"sender": "Alex", "text": "Meeting Friday?"}))

    def test_summary_wording_does_not_affect_comparison(self):
        self.save("run-1", [self.a], summary="An invitation to meet.")
        self.save("run-2", [self.a], summary="A proposed meeting.")
        self.assertEqual(memory.compare(self.history(), [self.a])["new_items"], [])

    def test_provider_uses_same_artifact_and_comparison(self):
        record, path = self.save("run-1", [self.a])
        remote = {**self.contract, "memory_context": {**self.contract["memory_context"],
                  "provider": "supermemory", "space": "test-space"}}
        del remote["memory_context"]["directory"]
        docs = {"space": "test-space", "complete": True, "documents": [
            {"id": "document-1", "status": "done", "contentTruncated": False, "content": Path(path).read_text()}]}
        remote_history = memory.load_history(remote, "test-account", docs)
        self.assertEqual(remote_history["records"][0]["record"], record)
        self.assertEqual(memory.compare(remote_history, [self.a, self.b]), memory.compare(self.history(), [self.a, self.b]))
        docs["complete"] = False
        self.assertEqual(memory.compare(memory.load_history(remote, "test-account", docs), [self.b])["continuity"], "limited")
        docs["documents"][0]["contentTruncated"] = True
        self.assertFalse(memory.load_history(remote, "test-account", docs)["records"])
        docs["space"] = "wrong-space"
        with self.assertRaises(ValueError):
            memory.load_history(remote, "test-account", docs)

    def test_invalid_history_is_not_a_clean_baseline(self):
        _, path = self.save("run-1", [self.a])
        Path(path).write_text("broken")
        result = memory.compare(self.history(), [self.a])
        self.assertFalse(result["baseline"])
        self.assertEqual(result["continuity"], "limited")

    def test_missing_predecessor_is_reported(self):
        _, path = self.save("run-1", [self.a])
        self.save("run-2", [self.b])
        Path(path).unlink()
        self.assertTrue(self.history()["warnings"])

    def test_save_failure_keeps_prior_history(self):
        self.save("run-1", [self.a])
        with patch.object(memory.os, "link", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.save("run-2", [self.b])
        self.assertEqual(len(self.history()["records"]), 1)
        self.assertFalse(list((Path(self.tmp.name) / "summaries").glob(".pending-*")))

    def test_cli_draft_cannot_be_saved(self):
        contract_file = Path(self.tmp.name) / "contract.json"
        contract_file.write_text(json.dumps(self.contract))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/briefing_memory.py"), "save",
                                 "--contract", str(contract_file), "--account", "test-account", "--input", "-"],
                                input=json.dumps({"version_id": "draft", "items": [self.a],
                                                  "coverage": "partial", "summary": "Draft."}),
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.history()["records"])

    BAD_CONFIGS = ({"space": "conflicts"}, {"provider": "unknown"}, {"directory": "relative"}, {"directory": ""})

    def bad_contracts(self):
        for edit in self.BAD_CONFIGS:
            bad = copy.deepcopy(self.contract)
            bad["memory_context"].update(edit)
            yield bad

    def test_runtime_config_validation(self):
        memory.validate_contract(self.contract)
        for bad in self.bad_contracts():
            with self.assertRaises(ValueError):
                memory.validate_contract(bad)

    def test_schemas_agree_with_runtime_validation(self):
        config_validator = memory.schema_validation.validator("attention-contract.schema.json", "#/$defs/memoryContext")
        validator = memory.schema_validation.validator("memory-record.schema.json")
        config_validator.validate(self.contract["memory_context"])
        record, _ = self.save("run-1", [self.a])
        validator.validate(record)
        surprise = copy.deepcopy(record)
        surprise["items"][0].update(slot="serendipity", topic="tidal energy")
        validator.validate(surprise)
        memory.validate_items(surprise["items"])
        for extra in ({"fingerprint_method": "unknown/v1"}, {"slot": "serendipity"}, {"unknown": True}):
            changed = copy.deepcopy(record)
            changed["items"][0].update(extra)
            self.assertTrue(list(validator.iter_errors(changed)))
            with self.assertRaises(ValueError):
                memory.validate_items(changed["items"])
        example = json.loads((ROOT / "integrations/memory/example-record.json").read_text())
        validator.validate(example)
        for bad in self.bad_contracts():
            self.assertFalse(config_validator.is_valid(bad["memory_context"]))


if __name__ == "__main__":
    unittest.main()
