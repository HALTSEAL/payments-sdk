"""Observe customer hook calls without modifying the installed SDK.

Observation is limited to calls through this client. Direct bank calls and other
application paths are not observed or covered by the kit.
"""
import importlib.util
import json
import threading
from pathlib import Path

HOOKS = ("map_reference", "original", "replacement", "recover", "stop")


def load_adapter(path):
    spec = importlib.util.spec_from_file_location("customer_workflow", Path(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.adapter_kind not in {"customer-code", "reference-fixture"}:
        raise RuntimeError("INCOMPLETE: adapter is unconfigured")
    if not all(callable(getattr(module, name, None)) for name in HOOKS):
        raise RuntimeError("INCOMPLETE: missing customer hooks")
    return module


class Hooks:
    def __init__(self, adapter, client, reference, stage):
        self.adapter, self.client = adapter, client
        self.reference, self.stage = reference, stage
        self.events = []
        self.lock = threading.Lock()

    def invoke(self, hook, context, result=None):
        context = {**context, "business_reference": self.reference, "stage": self.stage}
        calls = []
        outputs = []
        target = self.client

        class ObservedClient:
            def __getattr__(self, name):
                method = getattr(target, name)
                if not callable(method):
                    return method

                def observed(*args, **kwargs):
                    allowed = {"create_attempt"} if hook in {"original", "replacement"} else {
                        "lookup_operation", "recover"} if hook == "recover" else set()
                    if name not in allowed:
                        raise RuntimeError("Recovery and stop hooks cannot modify payments")
                    if name in {"create_attempt", "lookup_operation", "recover"}:
                        calls.append({"method": name, "args": list(args), "kwargs": kwargs})
                    output = method(*args, **kwargs)
                    outputs.append(json.dumps(output, sort_keys=True))
                    return output
                return observed

        event = {"stage": self.stage, "hook": hook,
                 "operation_id": context.get("operation_id"), "calls": calls}
        try:
            mapped = self.adapter.map_reference(context)
            if mapped != self.reference:
                raise RuntimeError("Both paths must map the same stable transaction")
            method = getattr(self.adapter, hook)
            output = method(ObservedClient(), context, result) if hook == "stop" else method(ObservedClient(), context)
            if hook in {"original", "replacement"}:
                self._execution_call(calls, context)
            elif hook == "recover":
                expected = "lookup_operation" if context["recovery_action"] == "LOOKUP_OPERATION" else "recover"
                expected_id = context["operation_id"] if expected == "lookup_operation" else context["attempt_id"]
                if len(calls) != 1 or calls[0]["method"] != expected or calls[0]["args"] != [expected_id]:
                    raise RuntimeError("Recovery hook did not query the exact retained identity")
            elif output != "STOP" or calls:
                raise RuntimeError("Blocked workflow must stop without another SDK call")
            if hook != "stop" and (len(outputs) != 1 or json.dumps(output, sort_keys=True) != outputs[0]):
                raise RuntimeError("Adapter changed the observed SDK result")
            event["outcome"] = output.get("decision", output.get("state")) if isinstance(output, dict) else output
            return output
        except Exception as exc:
            if hook in {"original", "replacement"}:
                self._execution_call(calls, context)
            event["error_type"] = type(exc).__name__
            raise
        finally:
            with self.lock:
                self.events.append(event)

    @staticmethod
    def _execution_call(calls, context):
        if len(calls) != 1 or calls[0] != {
            "method": "create_attempt", "args": [context["obligation_id"]],
            "kwargs": {"operation_id": context["operation_id"],
                       "route": context["route"], "approval_revision": context["approval_revision"]},
        }:
            raise RuntimeError("Execution hook must call the unchanged SDK exactly once with the agreed identity")
