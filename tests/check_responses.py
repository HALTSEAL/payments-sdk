"""Validate installed clients against independent HTTP response records."""
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from haltseal_payments_sdk import Client, TransportError, UncertainDispatch

origin, matrix, output = sys.argv[1:]
cases = json.loads(Path(matrix).read_text())["cases"]
records = []
with urlopen(origin + "/__test__/stats") as response:
    before = json.load(response)
with Client(origin, "synthetic-response-key") as client:
    for case in cases:
        kind, value = case["kind"], case["id"]
        try:
            if kind == "create":
                result = client.create_attempt("test-obligation", operation_id=value, route="A", approval_revision=1)
            elif kind == "lookup":
                result = client.lookup_operation(value, **({"obligation_id": "test-obligation"} if case.get("bind_obligation") else {}))
            elif kind == "source":
                result = client.approve_source(json.dumps({"test_case": value}, separators=(",", ":")))
            elif kind == "resume":
                result = client.resume(value, approval_revision=1)
            else:
                method = "obligation" if kind == "obligation" else kind
                result = getattr(client, method)(value)
            assert case["valid"], "Accepted corrupt response: " + value
            records.append({"id": value, "result": result})
        except TransportError as error:
            assert not case["valid"], "Rejected valid response: " + value
            expected = UncertainDispatch if kind in {"create", "source", "resume", "recover", "cancel"} else TransportError
            assert type(error) is expected and error.code == "INVALID_RESPONSE_CONTRACT", (value, type(error), error.code)
            records.append({"id": value, "error": type(error).__name__, "recovery": error.recovery.to_dict()})
with urlopen(origin + "/__test__/stats") as response:
    counts = json.load(response)
    assert all(counts.get(case["id"], 0) - before.get(case["id"], 0) == 1 for case in cases), "Unexpected resend"
Path(output).write_text(json.dumps(records, indent=2) + "\n")
print(f"PASS: Python {len(cases)} identity/record response cases.")
