"""Actual public Python SDK over the fixed, financially inert HTTP sandbox."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from haltseal_payments_sdk import Client, UncertainDispatch

origin = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"

def http(path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = Request(origin + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urlopen(req, timeout=15) as res:
        return json.load(res)

session = http("/sandbox/session", {})
assert session["sandbox_profile"] == "fixed-http-fixtures"
key, obligation = session["api_key"], session["obligation_id"]
client = Client(origin, key, timeout=15)
results = []
try:
    client.create_attempt(obligation, operation_id="demo-original", route="A", approval_revision=1)
except UncertainDispatch as lost:
    assert lost.operation_id == "demo-original" and lost.recovery_action == "LOOKUP_OPERATION"
    original = client.lookup_operation(lost.operation_id, obligation_id=lost.obligation_id)
    assert original["historical_decision"] and not original["redispatched"]
    results.append({"step": "original lookup after withheld reply", "result": original})
else:
    raise AssertionError("Expected the fixture to withhold the successful original reply")
backup = client.create_attempt(obligation, operation_id="demo-backup", route="B", approval_revision=1)
assert backup["decision"] == "HOLD"
results.append({"step": "unresolved replacement", "result": backup})
http("/sandbox/fixture", {"action": "inject-closure"}, key)
closed = client.recover(original["attempt_id"])
assert closed["state"] == "CLOSED"
results.append({"step": "recover injected closure", "result": closed})
stale = client.create_attempt(obligation, operation_id="demo-stale", route="B", approval_revision=1)
assert stale["decision"] == "HOLD"
results.append({"step": "stale approval", "result": stale})
http("/sandbox/fixture", {"action": "fresh-approval"}, key)
fresh = client.create_attempt(obligation, operation_id="demo-replacement", route="B", approval_revision=2)
assert fresh["decision"] == "ACCEPT" and fresh["execution_outcome"] == "PAID"
results.append({"step": "fresh replacement and predefined PAID fixture", "result": fresh})
again = client.create_attempt(obligation, operation_id="demo-after-paid", route="C", approval_revision=2)
assert again["decision"] == "REFUSE"
results.append({"step": "paid history", "result": again})
report = http("/sandbox/report", key=key)
assert report["synthetic_dispatches"] == 2 and report["original_lookup_redispatches"] == 0
report["sdk_results"] = results
Path("python-synthetic-result.json").write_text(json.dumps(report, indent=2) + "\n")
client.close()
print("PASS: original lookup; UNKNOWN HOLD; closure; stale HOLD; fresh ACCEPT; PAID REFUSE.")
print("Synthetic HTTP fixtures only. No payment kernel, native provider or customer qualification.")
print("Record: python-synthetic-result.json")
