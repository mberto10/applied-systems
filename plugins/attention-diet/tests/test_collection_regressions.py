"""Synthetic surface transitions and legacy memory comparison."""
import importlib.util
from pathlib import Path
import unittest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


coverage = load("surface_coverage")
memory = load("briefing_memory")


class IncomingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.contract = {"id": "personal", "coverage_threads": [{"id": "incoming", "service": "private-source", "surfaces": ["messages"]}],
                         "run_limits": {"items_per_surface": 30}}
        self.budget = {"over": False, "services": {"private-source": {
            "active": True, "over": False, "used_seconds": 64, "remaining_seconds": 236}}}
        self.observation = {"thread_id": "incoming", "surface": "messages", "inspected_count": 10, "more_available": True}

    def test_preview_pagination_continues_without_opening_conversations(self):
        # Scripted browser fixture: each load adds ten previews. Reading previews never opens a conversation.
        actions = []
        for count in (10, 20, 30):
            report = coverage.assess(self.contract, {**self.observation, "inspected_count": count}, self.budget)
            actions.append(report["action"])
        self.assertEqual(actions, ["load_more", "load_more", "stop"])
        self.assertEqual(report["stop_reason"], "item_ceiling")
        self.assertIn("more results available", report["coverage_note"])

    def test_automatic_selection_does_not_stop_pagination_or_claim_preservation(self):
        report = coverage.assess(self.contract, {**self.observation, "automatic_selection": True}, self.budget)
        self.assertEqual(report["action"], "load_more")
        self.assertEqual(report["read_state_effect"], "unknown")

    def test_exhaustion_ceiling_and_real_blocker(self):
        for obs, budget, expected in [
            ({**self.observation, "more_available": False, "exhaustion": {"kind": "explicit_end_marker", "evidence": "End marker visible."}}, self.budget, "exhausted_results"),
            (self.observation, {**self.budget, "over": True}, "time_ceiling"),
            ({**self.observation, "access_failure": "Load more button returns access denied"}, self.budget, "access_failure"),
        ]:
            self.assertEqual(coverage.assess(self.contract, obs, budget)["stop_reason"], expected)

    def test_unknown_availability_and_unsupported_novelty_boundary(self):
        obs = {**self.observation, "more_available": None}
        self.assertEqual(coverage.assess(self.contract, obs, self.budget)["action"], "inspect_availability")
        obs["novelty_boundary"] = {"evidence": "Recognized one conversation"}
        self.assertIsNone(coverage.assess(self.contract, obs, self.budget)["stop_reason"])
        obs["novelty_boundary"] = {"ordering_verified": True, "covered_range_verified": True,
                                   "evidence": "Chronological incoming dates reach the previously inspected unchanged range"}
        self.assertEqual(coverage.assess(self.contract, obs, self.budget)["stop_reason"], "novelty_boundary")

    def test_cannot_use_budget_after_switching_away(self):
        budget = {"services": {"private-source": {"active": False, "over": False}}}
        with self.assertRaises(ValueError):
            coverage.assess(self.contract, self.observation, budget)

    def history(self, item):
        return {"records": [{"record": {"items": [item], "created_at": "2026-09-18T05:13:39Z"}}], "warnings": []}

    def item(self, **extra):
        return {"service": "private-source", "identifier": "conversation-1", **extra}

    def test_legacy_mismatch_is_uncertain_not_new(self):
        old = self.item(change_fingerprint="old-undocumented-hash")
        current = self.item(**memory.fingerprint_metadata({"sender": "A", "text": "Same old preview"}))
        result = memory.compare(self.history(old), [current])
        self.assertEqual(result["new_items"], [])
        self.assertEqual(result["uncertain_items"], [current])
        self.assertEqual(result["already_briefed_count"], 0)
        self.assertEqual(result["continuity"], "limited")

    def test_latest_unversioned_summary_exact_match_prevents_transition_repeat(self):
        current = self.item(**memory.fingerprint_metadata({"sender": "A", "text": "Same old preview"}))
        old = {k: v for k, v in current.items() if k != "fingerprint_method"}
        result = memory.compare(self.history(old), [current])
        self.assertEqual(result["new_items"], [])
        self.assertEqual(result["uncertain_items"], [])
        self.assertEqual(result["already_briefed_count"], 1)

    def test_different_documented_methods_are_not_content_change(self):
        old = self.item(**memory.fingerprint_metadata({"incoming_id": "m1"}))
        current = self.item(**memory.fingerprint_metadata({"sender": "A", "text": "Message one"}))
        self.assertEqual(memory.compare(self.history(old), [current])["uncertain_items"], [current])

    def test_new_message_in_known_conversation_still_qualifies(self):
        old = self.item(**memory.fingerprint_metadata({"incoming_id": "m1"}))
        current = self.item(**memory.fingerprint_metadata({"incoming_id": "m2"}))
        self.assertEqual(memory.compare(self.history(old), [current])["new_items"], [current])

    def test_later_source_event_can_resolve_legacy_uncertainty(self):
        old = self.item(change_fingerprint="legacy")
        new = self.item(**memory.fingerprint_metadata({"sender": "A", "text": "New message", "occurred_at": "2026-09-18T06:00:00Z"}))
        self.assertEqual(memory.compare(self.history(old), [new])["new_items"], [new])
        earlier = {**new, "source_timestamp": "2026-09-17T06:00:00Z"}
        self.assertEqual(memory.compare(self.history(old), [earlier])["uncertain_items"], [earlier])

    def test_metadata_distinguishes_basis_and_requires_absolute_time(self):
        self.assertEqual(memory.fingerprint_metadata({"incoming_id": "m1"})["fingerprint_method"], "incoming-id/v1")
        with self.assertRaises(ValueError):
            memory.validate_items([self.item(change_fingerprint="h", fingerprint_method="guessed")])
        with self.assertRaises(ValueError):
            memory.validate_items([self.item(change_fingerprint="h", source_timestamp="yesterday")])


if __name__ == "__main__":
    unittest.main()
