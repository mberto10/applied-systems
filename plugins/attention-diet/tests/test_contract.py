import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/attention-contract.json"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load_script("contract")
budget = load_script("run_budget")


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ATTENTION_DIET_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.data = json.loads(TEMPLATE.read_text())

    def write(self, data, name="draft.json"):
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(data))
        return path

    def test_hard_limits_cannot_be_loosened_by_editing(self):
        for field, value, message in (("account_actions", "reply", "account_actions"),
                                      ("access", "user_browser", "access"),
                                      ("external_session_reuse", True, "access")):
            data = copy.deepcopy(self.data)
            target = data["coverage_threads"][0]
            if field == "external_session_reuse":
                target = target["access"]
            target[field] = value
            with self.assertRaisesRegex(ValueError, message):
                contract.validate(data)
        self.data["execution"]["schedule_enabled"] = True
        with self.assertRaisesRegex(ValueError, "schedule_enabled"):
            contract.validate(self.data)

    def test_cross_field_rules(self):
        data = copy.deepcopy(self.data)
        data["coverage_threads"][0]["excluded_surfaces"] = ["recommendations"]
        data["coverage_threads"][0]["surfaces"].append("recommendations")
        with self.assertRaisesRegex(ValueError, "included and excluded"):
            contract.validate(data)
        data = copy.deepcopy(self.data)
        data["run_limits"]["service_minutes"]["example-source"] = 60
        with self.assertRaisesRegex(ValueError, "exceed"):
            contract.validate(data)
        self.data["surprise"] = True
        with self.assertRaisesRegex(ValueError, "Additional properties"):
            contract.validate(self.data)

    def test_browser_choice_is_required_without_loosening_interaction_limits(self):
        for provider in ('host_default', 'codex_in_app', 'claude_browser', 'agent_browser'):
            data = copy.deepcopy(self.data)
            data['coverage_threads'][0]['access']['provider'] = provider
            self.assertEqual(contract.validate(data), data)
            for field, value in (('external_session_reuse', True), ('session', 'everyday'),
                                 ('fallback', 'connector'), ('provider', 'chrome')):
                invalid = copy.deepcopy(data)
                invalid['coverage_threads'][0]['access'][field] = value
                with self.subTest(provider=provider, field=field), self.assertRaises(ValueError):
                    contract.validate(invalid)
        for field in ('access', 'procedure'):
            invalid = copy.deepcopy(self.data)
            invalid['coverage_threads'][0].pop(field)
            with self.assertRaises(ValueError):
                contract.validate(invalid)

    def test_install_resolve_and_revision_history(self):
        with self.assertRaisesRegex(ValueError, "No contract installed"):
            contract.resolve()
        first = contract.install(self.write(self.data))
        self.assertEqual(contract.resolve(), Path(first["path"]))
        self.assertEqual(Path(first["path"]).stat().st_mode & 0o777, 0o600)

        revised = copy.deepcopy(self.data)
        revised["composition"]["max_items_by_thread"]["source-1"] = 3
        with self.assertRaisesRegex(ValueError, "increments revision"):
            contract.install(self.write(revised))
        revised["revision"] = 2
        result = contract.install(self.write(revised))
        self.assertEqual([c["path"] for c in result["changes"]], ["/composition/max_items_by_thread/source-1"])
        kept = Path(first["path"]).parent / "revisions/1.json"
        self.assertEqual(json.loads(kept.read_text())["composition"]["max_items_by_thread"]["source-1"], 5)
        log = (Path(first["path"]).parent / "changelog.md").read_text()  # A hand edit leaves a record too.
        self.assertIn("revision 2: Manual edit installed from a file (/composition/max_items_by_thread/source-1)", log)

    def test_install_migration_preserves_older_revision_and_history_binding(self):
        old = copy.deepcopy(self.data)
        old['schema_version'] = 'attention-diet-contract/1.0'
        for thread in old['coverage_threads']:
            thread.pop('procedure')
        target = contract.contract_path(old['id'])
        contract.write_private(target, json.dumps(old))
        revised = copy.deepcopy(self.data)
        revised['revision'] = 2
        contract.install(self.write(revised))
        self.assertEqual(json.loads((target.parent / 'revisions/1.json').read_text()), old)
        self.assertEqual(json.loads(target.read_text())['memory_context'], old['memory_context'])

    def test_several_contracts_need_a_choice_or_default(self):
        contract.install(self.write(self.data))
        other = {**copy.deepcopy(self.data), "id": "work"}
        contract.install(self.write(other))
        with self.assertRaisesRegex(ValueError, "Several contracts"):
            contract.resolve()
        self.assertEqual(contract.resolve("work").parent.name, "work")
        contract.install(self.write({**other, "revision": 2, "intent": {**other["intent"], "success": "Changed."}}),
                         make_default=True)
        self.assertEqual(contract.resolve().parent.name, "work")

    def test_single_template_is_valid_generic_and_impersonal(self):
        names = sorted(p.name for p in (ROOT / "templates").glob("*.json"))
        self.assertEqual(names, ["attention-contract.json"])
        for name in names:
            text = (ROOT / "templates" / name).read_text()
            data = contract.validate(json.loads(text))
            self.assertEqual(data["id"], "my-attention")
            self.assertEqual(len(data["coverage_threads"]), 1)
            self.assertEqual(data["coverage_threads"][0]["content"], "private_communication")
            self.assertNotIn("previous_ids", data)
            self.assertEqual(data["revision"], 1)
            self.assertFalse(data.get("serendipity", {}).get("enabled", False), "surprise is opt-in")
            self.assertFalse(any("expected_account" in t for t in data["coverage_threads"]))

    def test_serendipity_grants_no_access(self):
        block = self.data["serendipity"]
        block["enabled"] = True
        block["sources"] = ["source-1/items"]
        contract.validate(self.data)
        for edit, message in (({"sources": ["source-1/recommendations"]}, "beyond configured surfaces"),
                              ({"sources": ["unconfigured/items"]}, "beyond configured surfaces"),
                              ({"sources": []}, "serendipity/sources"),
                              ({"max_items": 4}, "serendipity/max_items"),
                              ({"share_of_discovery_sample": 0.9}, "share_of_discovery_sample"),
                              ({"extra_scrolling": True}, "Additional properties")):
            data = copy.deepcopy(self.data)
            data["serendipity"].update(edit)
            with self.assertRaisesRegex(ValueError, message):
                contract.validate(data)

    def test_remove_archives_and_export_strips_identity(self):
        self.data["coverage_threads"][0]["content"] = "public_posts"
        self.data["coverage_threads"][0]["expected_account"] = "public-source:12345"
        self.data["coverage_threads"][0]["creators"] = [{"name": "A Person", "handle": "aperson", "url": "https://reading.example.org/aperson"}]
        self.data.update(id="personal", previous_ids=["older"])
        contract.install(self.write(self.data), make_default=True)
        shared = contract.export("personal")
        text = json.dumps(shared)
        for private in ("public-source:12345", "aperson"):
            self.assertNotIn(private, text)
        self.assertNotIn("previous_ids", shared)
        self.assertTrue(shared["memory_context"]["directory"].endswith("/my-attention"))
        self.assertEqual((shared["id"], shared["revision"]), ("my-attention", 1))

        result = contract.remove("personal")
        self.assertEqual(contract.available(), [])
        self.assertTrue((Path(result["archived_to"]) / "attention_contract.json").is_file())
        self.assertFalse((Path(self.tmp.name) / "default").exists())

    def test_permission_for_parallel_collection_stays_valid_but_consultation_is_gone(self):
        """A contract that permits parallel collection may overlap its service allowances; consultation stays removed."""
        self.data["execution"]["parallelism"] = {"mode": "when_independent", "max_workers": 2}
        self.data["run_limits"].update(elapsed_minutes=10, service_minutes={"example-source": 10})
        contract.validate(self.data)
        self.data["memory_context"]["also_consult"] = [{"contract": "work", "services": ["example-source"]}]
        with self.assertRaisesRegex(ValueError, "also_consult"):
            contract.validate(self.data)

    def test_bundled_schema_rejects_unknown_fields_and_checks_formats(self):
        validator = contract.memory.schema_validation.validator("attention-contract.schema.json")
        validator.validate(self.data)
        for change in (lambda c: c["coverage_threads"][0].update(account_actions="reply"),
                       lambda c: c["coverage_threads"][0]["entry_urls"].update(items="https://bad host/items")):
            data = copy.deepcopy(self.data)
            change(data)
            self.assertTrue(list(validator.iter_errors(data)))
            with self.assertRaises(ValueError):
                contract.validate(data)


class RenamedContractMemoryTest(unittest.TestCase):
    def test_history_follows_previous_ids(self):
        memory = contract.memory
        with tempfile.TemporaryDirectory() as folder:
            policy = {"provider": "local", "directory": folder,
                      "purpose": "avoid_repeating_previously_briefed_items", "on_unavailable": "continue_with_notice"}
            old = {"id": "old-name", "revision": 4, "memory_context": policy}
            item = {"service": "private-source", "identifier": "c1", "change_fingerprint": memory.fingerprint({"incoming_id": "m1"})}
            record = memory.build_record(old, "acct", {"version_id": "v1", "items": [item], "coverage": "checked",
                                                       "summary": "One message."}, memory.load_history(old, "acct"))
            memory.save_local(old, record)
            renamed = {"id": "new-name", "previous_ids": ["old-name"], "revision": 5, "memory_context": policy}
            self.assertEqual(memory.compare(memory.load_history(renamed, "acct"), [item])["new_items"], [])
            unrelated = {"id": "other", "revision": 1, "memory_context": policy}
            self.assertEqual(memory.compare(memory.load_history(unrelated, "acct"), [item])["new_items"], [item])


class SharedAndSerendipityMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ATTENTION_DIET_HOME": self.tmp.name + "/config"})
        env.start()
        self.addCleanup(env.stop)
        self.memory = contract.memory

    def installed(self, contract_id, **extra):
        data = json.loads(TEMPLATE.read_text())
        data["id"] = contract_id
        data["coverage_threads"][0].update(service="public-source", content="public_posts")
        data["run_limits"]["service_minutes"] = {"public-source": 10}
        data["memory_context"]["directory"] = self.tmp.name + "/state/" + contract_id
        data["memory_context"].update(extra)
        path = Path(self.tmp.name) / (contract_id + ".json")
        path.write_text(json.dumps(data))
        contract.install(path)
        return data

    def brief(self, data, items, version="v1", account="public-source:1"):
        m = self.memory
        record = m.build_record(data, account, {"version_id": version, "items": items, "coverage": "sampled",
                                                "summary": "A summary."}, m.load_history(data, account))
        m.save_local(data, record)

    def item(self, service, ident, **extra):
        return {"service": service, "identifier": ident,
                "change_fingerprint": self.memory.fingerprint({"incoming_id": ident}), **extra}

    def test_serendipity_items_keep_identity_and_report_recent_topics(self):
        m = self.memory
        data = self.installed("personal")
        surprise = self.item("public-source", "public-source:post:9", slot="serendipity", topic="tidal energy")
        self.brief(data, [self.item("public-source", "public-source:post:1"), surprise])
        history = m.load_history(data, "public-source:1")
        self.assertEqual(m.recent_topics(history, 5), ["tidal energy"])
        self.assertEqual(m.recent_topics(history, 0), [])
        plain_again = self.item("public-source", "public-source:post:9")  # same post seen later without the slot fields
        self.assertEqual(m.compare(history, [plain_again])["new_items"], [])
        for bad in ({"slot": "serendipity"}, {"topic": "no slot"}, {"slot": "other", "topic": "t"},
                    {"slot": "serendipity", "topic": "public-source" * 61}, {"rank": 1}):
            with self.assertRaises(ValueError):
                m.validate_items([self.item("public-source", "public-source:post:3", **bad)])
        m.decode(m.encode(history["records"][0]["record"]))  # round trip with optional fields


class BudgetTest(unittest.TestCase):
    def test_configured_service_without_own_time_share_uses_overall_budget(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_STATE_HOME': folder}):
            data = json.loads(TEMPLATE.read_text())
            data['run_limits']['service_minutes'] = {}
            state = budget.start(data)
            budget.begin_service(state, 'example-source')
            self.assertTrue(budget.check(state)['services']['example-source']['active'])
            with self.assertRaises(ValueError):
                budget.begin_service(state, 'unconfigured')

    def test_overall_and_service_ceilings(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_STATE_HOME": folder}):
            t0 = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
            state = budget.start({"id": "c", "revision": 1,
                                  "run_limits": {"elapsed_minutes": 12, "service_minutes": {"private-source": 5, "public-source": 7}}}, at=t0)
            budget.begin_service(state, "private-source", at=t0)
            report = budget.check(state, at=t0 + timedelta(minutes=4))
            self.assertFalse(report["stop"])
            self.assertEqual(report["services"]["private-source"]["remaining_seconds"], 60)
            self.assertTrue(budget.check(state, at=t0 + timedelta(minutes=6))["stop"])

            budget.begin_service(state, "public-source", at=t0 + timedelta(minutes=6))
            report = budget.check(state, at=t0 + timedelta(minutes=8))
            self.assertFalse(report["stop"])  # The first service is closed; the second still has time
            self.assertEqual(report["services"]["private-source"]["used_seconds"], 360)
            self.assertTrue(budget.check(state, at=t0 + timedelta(minutes=12))["over"])
            with self.assertRaisesRegex(ValueError, "No budget"):
                budget.begin_service(state, "unconfigured-source")


if __name__ == "__main__":
    unittest.main()
