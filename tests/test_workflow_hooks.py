"""A fake expected result, identity mismatch or recovery send must not pass."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/workflow-evaluation/python"
sys.path.insert(0, str(EXAMPLES))
from hooks import Hooks, load_adapter
from contract import load_workflow
import reference_adapter as reference


class Client:
    def __init__(self):
        self.sends = 0
    def create_attempt(self, oid, **kwargs):
        self.sends += 1
        return {"decision": "HOLD"}
    def lookup_operation(self, op, **kwargs):
        return {"operation_id": op, "redispatched": False}
    def recover(self, aid):
        return {"state": "PENDING", "attempt_id": aid}


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.context = {"obligation_id": "obl-test", "operation_id": "op-test", "route": "A", "approval_revision": 1}
        self.adapter = types.SimpleNamespace(**{name: getattr(reference, name) for name in ["map_reference", "original", "replacement", "recover", "stop"]})
        self.hooks = Hooks(self.adapter, self.client, "eval:one", "original")

    def test_empty_template_is_incomplete(self):
        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE"):
            load_adapter(EXAMPLES / "customer_adapter.py")

    def test_customer_module_import_and_dataclass_are_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "local_payment_app.py").write_text("def execute(client, context):\n    return client.create_attempt(context['obligation_id'], operation_id=context['operation_id'], route=context['route'], approval_revision=context['approval_revision'])\n")
            source = "from __future__ import annotations\nfrom dataclasses import dataclass\nfrom local_payment_app import execute\nfrom reference_adapter import map_reference, recover, stop\nadapter_kind='customer-code'\n@dataclass\nclass Mapping:\n    reference: str\noriginal=execute\nreplacement=execute\n"
            path = root / "adapter.py"; path.write_text(source)
            adapter = load_adapter(path)
            observed = Hooks(adapter, self.client, "eval:one", "original")
            self.assertEqual(observed.invoke("original", self.context), {"decision": "HOLD"})
            self.assertEqual(self.client.sends, 1)
            self.assertEqual(observed.events[0]["hook"], "original")

    def test_expected_value_without_sdk_call_is_rejected(self):
        self.adapter.original = lambda c, ctx: {"decision": "HOLD"}
        with self.assertRaisesRegex(RuntimeError, "exactly once"):
            self.hooks.invoke("original", self.context)
        self.assertEqual(self.client.sends, 0)

    def test_wrong_transaction_mapping_never_sends(self):
        self.adapter.map_reference = lambda ctx: "foreign"
        with self.assertRaises(RuntimeError):
            self.hooks.invoke("original", self.context)
        self.assertEqual(self.client.sends, 0)

    def test_rewritten_sdk_result_is_rejected(self):
        def rewrite(c, ctx):
            reference.original(c, ctx)
            return {"decision": "ACCEPT"}
        self.adapter.original = rewrite
        with self.assertRaisesRegex(RuntimeError, "changed the observed"):
            self.hooks.invoke("original", self.context)

    def test_recovery_create_is_blocked_before_send(self):
        self.adapter.recover = reference.original
        with self.assertRaisesRegex(RuntimeError, "cannot modify"):
            self.hooks.invoke("recover", {**self.context, "recovery_action": "LOOKUP_OPERATION"})
        self.assertEqual(self.client.sends, 0)

    def test_stop_create_is_blocked_before_send(self):
        self.adapter.stop = lambda c, ctx, result: reference.original(c, ctx)
        with self.assertRaisesRegex(RuntimeError, "cannot modify"):
            self.hooks.invoke("stop", self.context, {"decision": "HOLD"})
        self.assertEqual(self.client.sends, 0)

    def test_recovery_foreign_identity_is_rejected(self):
        self.adapter.recover = lambda c, ctx: c.lookup_operation("foreign")
        with self.assertRaisesRegex(RuntimeError, "exact retained"):
            self.hooks.invoke("recover", {**self.context, "recovery_action": "LOOKUP_OPERATION"})

    def test_same_input_contract_rejects_missing_extra_and_third_paths(self):
        template = json.loads((EXAMPLES.parent / "workflow.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(template))
            self.assertEqual(load_workflow(path), template)
            for mutate in [lambda x: x.update(extra=True), lambda x: x["paths"].append(x["paths"][0]), lambda x: x["paths"][1].update(route="A")]:
                bad = json.loads(json.dumps(template)); mutate(bad)
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    load_workflow(path)


if __name__ == "__main__":
    unittest.main()
