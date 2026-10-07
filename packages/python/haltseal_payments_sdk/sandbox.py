"""Account-free SDK exercise against HALTSEAL's fixed HTTP fixtures.

Run with ``python -m haltseal_payments_sdk.sandbox``. This is an explicit
synthetic exercise, separate from application Client calls and payment authority.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request
from . import Client, UncertainDispatch, __version__
from ._client import _strict_json
from ._transport import Exchange

HOSTED_ORIGIN = "https://haltseal.com"
MAX_RESPONSE = 1_048_576


def fixture_origin(value: str) -> str:
    value = value.rstrip("/")
    if value == HOSTED_ORIGIN:
        return value
    match = re.fullmatch(r"http://(?:127\.0\.0\.1|\[::1\]):([0-9]{1,5})", value)
    if match and 1 <= int(match[1]) <= 65535:
        return value
    raise ValueError("Use https://haltseal.com or a literal loopback fixture origin")


def _http(origin: str, path: str, body=None, key=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(origin + path, data=payload, headers=headers)
    exchange = Exchange(time.monotonic() + 15)

    def send():
        with exchange.open(request, None) as response:
            if response.status != 200:
                raise RuntimeError("Fixture request did not succeed")
            if response.headers.get_content_type() != "application/json":
                raise RuntimeError("Fixture JSON response required")
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise RuntimeError("Fixture response limit exceeded")
            result = _strict_json(data)
            if not isinstance(result, dict):
                raise RuntimeError("Fixture object required")
            return result

    try:
        return exchange.call(send, lambda: None)
    finally:
        exchange.cancel()


def exercise(origin: str = HOSTED_ORIGIN) -> dict:
    origin = fixture_origin(origin)
    session = _http(origin, "/sandbox/session", {})
    if (session.get("sandbox_profile") != "fixed-http-fixtures"
            or session.get("production") != "NO_GO"
            or session.get("api_origin") != origin
            or not isinstance(session.get("api_key"), str)
            or not re.fullmatch(r"hs_sandbox_[a-f0-9]{32}", session["api_key"])
            or not isinstance(session.get("obligation_id"), str)):
        raise RuntimeError("Fixed synthetic session required")
    key, obligation = session["api_key"], session["obligation_id"]
    results = []

    def retain(label, result, condition):
        if not condition:
            raise RuntimeError("Unexpected synthetic recovery result")
        results.append({"step": label, "result": result})

    with Client(origin, key, timeout=15) as client:
        try:
            client.create_attempt(obligation, operation_id="demo-original", route="A", approval_revision=1)
        except UncertainDispatch as lost:
            if lost.operation_id != "demo-original" or lost.recovery_action != "LOOKUP_OPERATION":
                raise RuntimeError("Original recovery identity required")
            original = client.lookup_operation(lost.operation_id, obligation_id=lost.obligation_id)
            retain("original lookup after withheld reply", original,
                   original.get("historical_decision") is True and original.get("redispatched") is False
                   and original.get("execution_outcome") == "UNKNOWN")
        else:
            raise RuntimeError("Expected a withheld original reply")
        backup = client.create_attempt(obligation, operation_id="demo-backup", route="B", approval_revision=1)
        retain("unresolved replacement", backup, backup.get("decision") == "HOLD")
        _http(origin, "/sandbox/fixture", {"action": "inject-closure"}, key)
        closed = client.recover(original["attempt_id"])
        retain("recover injected closure", closed, closed.get("state") == "CLOSED")
        stale = client.create_attempt(obligation, operation_id="demo-stale", route="B", approval_revision=1)
        retain("stale approval", stale, stale.get("decision") == "HOLD")
        _http(origin, "/sandbox/fixture", {"action": "fresh-approval"}, key)
        fresh = client.create_attempt(obligation, operation_id="demo-replacement", route="B", approval_revision=2)
        retain("fresh replacement and predefined PAID fixture", fresh,
               fresh.get("decision") == "ACCEPT" and fresh.get("execution_outcome") == "PAID")
        again = client.create_attempt(obligation, operation_id="demo-after-paid", route="C", approval_revision=2)
        retain("paid history", again, again.get("decision") == "REFUSE")
        report = _http(origin, "/sandbox/report", key=key)
    if report.get("synthetic_dispatches") != 2 or report.get("original_lookup_redispatches") != 0:
        raise RuntimeError("Unexpected synthetic dispatch counts")
    report.update(sdk_results=results, sdk_version=__version__, sdk_package="haltseal-payments")
    encoded = json.dumps(report)
    if key in encoded or '"api_key"' in encoded:
        raise RuntimeError("Credential-free report required")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed synthetic payment recovery exercise. No real funds.")
    parser.add_argument("--origin", default=HOSTED_ORIGIN, help="Hosted sandbox, or a literal loopback fixture for local checks")
    parser.add_argument("--output", type=Path, help="Save the synthetic record to a new JSON file; never overwrite")
    args = parser.parse_args(argv)
    try:
        fixture_origin(args.origin)
        if args.output and args.output.exists():
            raise FileExistsError("Choose a new output file")
        report = exercise(args.origin)
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(json.dumps(report, indent=2) + "\n")
        print("PASS: original lookup; UNKNOWN HOLD; closure; stale HOLD; fresh ACCEPT; PAID REFUSE.")
        print("Synthetic dispatches: 2. Original lookup redispatches: 0.")
        print("Fixed synthetic HTTP fixtures. No real funds or production qualification.")
        if args.output:
            print("Record: " + str(args.output))
        print("Next: https://haltseal.com/pricing/#workflow")
        return 0
    except Exception:
        # Error bodies, session keys and response headers never reach the terminal.
        print("Sandbox exercise stopped. Keep the original identity; an unavailable reply grants no replacement.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
