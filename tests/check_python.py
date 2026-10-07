"""Exercise the installed client on the same HTTP faults as JavaScript."""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from haltseal_payments_sdk import Client, APIError, TransportError, UncertainDispatch, ValidationError

origin, matrix, output = sys.argv[1:]
cases = json.loads(Path(matrix).read_text())
key = "fixture-secret-not-for-output"
results = []


def stats():
    with urlopen(origin + "/__test__/stats") as response:
        return json.load(response)


for case in cases:
    events = []
    before = stats().get(case["id"], 0)
    with Client(origin, key, timeout=case.get("timeout_ms", 2000) / 1000, on_event=events.append) as client:
        try:
            kind = case["kind"]
            if kind == "create":
                client.create_attempt("test-obligation", operation_id=case["id"], route="A", approval_revision=1)
            elif kind == "lookup":
                client.lookup_operation(case["id"])
            elif kind == "source":
                client.approve_source(json.dumps({"test_case": case["id"]}, separators=(",", ":")))
            elif kind == "resume":
                client.resume(case["id"], approval_revision=1)
            else:
                getattr(client, kind)(case["id"])
            raise AssertionError("Expected recovery error: " + case["id"])
        except (APIError, TransportError) as error:
            assert type(error).__name__ == case["expected_error"], (case["id"], type(error).__name__)
            context = error.recovery.to_dict()
            assert context["action"] == case["action"], case["id"]
            assert context["request_may_have_executed"] == (kind not in ["lookup", "attempt"])
            if kind == "create":
                assert error.operation_id == case["id"] and error.obligation_id == "test-obligation"
            elif kind != "source":
                assert context["identity_value"] == case["id"]
            assert len(context["request_fingerprint"]) == 64
            assert key not in json.dumps({"context": context, "events": events})
            try:
                error.recovery.action = "SEND_AGAIN"
                raise AssertionError("Mutable recovery context")
            except FrozenInstanceError:
                pass
            assert stats().get(case["id"], 0) - before == 1, "Automatic resend: " + case["id"]
            results.append({"id": case["id"], "error": type(error).__name__, "recovery": context, "sends": 1})

before = stats()
with Client(origin, key) as client:
    invalid = [dict(operation_id="bad\n", route="A", approval_revision=1),
               dict(operation_id="valid", route="D", approval_revision=1),
               dict(operation_id="valid", route="A", approval_revision=True)]
    for options in invalid:
        try:
            client.create_attempt("test-obligation", **options)
            raise AssertionError("Invalid input sent")
        except ValidationError:
            pass
    client.close()
    try:
        client.attempt("valid")
        raise AssertionError("Closed client sent")
    except ValidationError:
        pass
for bad_origin in ["http://example.com", origin + "/path", "https://key@example.com"]:
    try:
        Client(bad_origin, key)
        raise AssertionError("Invalid origin accepted")
    except ValidationError:
        pass
assert stats() == before and "unexpected" not in before, "Unexpected HTTP request"
Path(output).write_text(json.dumps(results, indent=2) + "\n")
print(f"PASS: Python {len(cases)} HTTP failure cases, 7 zero-send validation/lifecycle checks.")
