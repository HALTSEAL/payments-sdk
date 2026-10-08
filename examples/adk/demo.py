"""Run real ADK tools against the existing loopback-only SDK fixture."""
from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
from urllib.request import Request, urlopen

from haltseal_payments_sdk import Client, __version__

from payment_tools import BoundPaymentTools, OperationJournal, PaymentBinding, PaymentControls
from scripted_agent import run_tools

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from run_installed import host


def fixture_http(origin: str, path: str, body=None, key=None) -> dict:
    """Trusted demo controls, deliberately absent from every agent tool list."""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = Request(origin + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers=headers)
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def require(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError("ADK fixture check failed: " + label)


def decisions(run: dict) -> list[str]:
    return [step["result"].get("decision") for step in run["tool_results"]]


async def exercise(origin: str) -> dict:
    require(version("google-adk") == "2.11.0" and __version__ == "0.2.0rc2", "pinned dependencies")
    session = fixture_http(origin, "/sandbox/session", {})
    require(session.get("sandbox_profile") == "fixed-http-fixtures"
            and session.get("api_origin") == origin and session.get("production") == "NO_GO",
            "fixed local session")
    key, obligation = session["api_key"], session["obligation_id"]
    runs, controls = [], PaymentControls()
    with Client(origin, key, timeout=15) as client:
        def bind(operation: str, route: str, revision: int,
                 *, submitted: bool = False, scope: PaymentControls = controls):
            return BoundPaymentTools(client, OperationJournal(
                PaymentBinding(obligation, operation, route, revision), submitted), scope)

        original = bind("demo-original", "A", 1)
        lost = await run_tools(original, [
            {"tool": "request_payment"}, {"tool": "request_payment"},
            {"tool": "lookup_payment"}], agent_name="original_agent", session_id="original-session")
        require(decisions(lost) == ["HOLD", "HOLD", "ACCEPT"], "lost reply and repeated call")
        found = lost["tool_results"][2]["result"]
        require(found["historical_decision"] is True and found["redispatched"] is False
                and found["execution_outcome"] == "UNKNOWN"
                and found["available_principal_minor"] == 0, "original UNKNOWN reservation")
        require(lost["tool_results"][1]["result"]["sdk_request_sent"] is False,
                "repeat call issues no SDK request")
        runs.append(lost)

        # A fresh runner/session/tool object. Submission intent comes from the
        # trusted host journal, not from ADK conversation memory or a new task ID.
        restored = bind("demo-original", "A", 1, submitted=True)
        handoff = await run_tools(restored, [
            {"tool": "request_payment"}, {"tool": "lookup_payment"}],
            agent_name="handoff_agent", session_id="different-session")
        require(decisions(handoff) == ["HOLD", "ACCEPT"]
                and handoff["tool_results"][1]["result"]["operation_id"] == "demo-original"
                and handoff["tool_results"][1]["result"]["redispatched"] is False,
                "agent/session handoff retains original")
        runs.append(handoff)

        backup = await run_tools(bind("demo-backup", "B", 1), [{
            "tool": "request_payment", "args": {
                "obligation_id": "agent-invented-obligation", "operation_id": "agent-invented-operation",
                "route": "C", "approval_revision": 999, "original_is_closed": True}}],
            agent_name="backup_agent", session_id="backup-session")
        blocked = backup["tool_results"][0]["result"]
        require(blocked["decision"] == "HOLD"
                and blocked["reason"] == "ORIGINAL_OUTCOME_UNRESOLVED"
                and blocked["obligation_id"] == obligation and blocked["operation_id"] == "demo-backup",
                "model arguments cannot override host binding or claim closure")
        runs.append(backup)

        fixture_http(origin, "/sandbox/fixture", {"action": "inject-closure"}, key)
        closure = client.recover(found["attempt_id"])
        require(closure["state"] == "CLOSED", "host observes injected closure")
        stale = await run_tools(bind("demo-stale", "B", 1), [{"tool": "request_payment"}],
                               agent_name="stale_agent", session_id="stale-session")
        require(decisions(stale) == ["HOLD"]
                and stale["tool_results"][0]["result"]["reason"] == "FRESH_POSTCLOSURE_APPROVAL_REQUIRED",
                "closure alone does not refresh approval")
        runs.append(stale)

        fixture_http(origin, "/sandbox/fixture", {"action": "fresh-approval"}, key)
        # Independent adapters and locks, the same backend obligation. The
        # fixture's persisted transaction, not the LLM or a shared Python lock,
        # arbitrates these competing requests. Its winner is predefined PAID.
        contenders = await asyncio.gather(
            run_tools(bind("demo-race-1", "B", 2, scope=PaymentControls()),
                      [{"tool": "request_payment"}], agent_name="route_b_agent", session_id="race-b"),
            run_tools(bind("demo-race-2", "C", 2, scope=PaymentControls()),
                      [{"tool": "request_payment"}], agent_name="route_c_agent", session_id="race-c"))
        require(sorted(decisions(run)[0] for run in contenders) == ["ACCEPT", "REFUSE"],
                "one fresh contender admitted in the fixed fixture")
        runs.extend(contenders)
        paid = await run_tools(bind("demo-after-paid", "C", 2), [{"tool": "request_payment"}],
                              agent_name="after_paid_agent", session_id="after-paid-session")
        require(decisions(paid) == ["REFUSE"], "paid history blocks another route")
        runs.append(paid)
        snapshot = fixture_http(origin, "/sandbox/report", key=key)
        original_writes = [call for call in snapshot["trace"]
                           if call["method"] == "POST" and call["status"] == 503]
        require(len(original_writes) == 1 and snapshot["synthetic_dispatches"] == 2
                and snapshot["original_lookup_redispatches"] == 0, "exact original dispatch counts")

    # Separate fixture: stop while the original is still UNKNOWN, before any
    # closure or fresh approval. This is a local latch, not a remote kill switch.
    stop_session = fixture_http(origin, "/sandbox/session", {})
    stop_key, stop_obligation = stop_session["api_key"], stop_session["obligation_id"]
    stop_controls = PaymentControls()
    with Client(origin, stop_key, timeout=15) as client:
        stop_original = BoundPaymentTools(client, OperationJournal(
            PaymentBinding(stop_obligation, "demo-original", "A", 1)), stop_controls)
        start = await run_tools(stop_original, [{"tool": "request_payment"}],
                                agent_name="stop_original_agent", session_id="stop-original")
        require(decisions(start) == ["HOLD"], "stop fixture original loses reply")
        stop_backup = BoundPaymentTools(client, OperationJournal(
            PaymentBinding(stop_obligation, "demo-backup", "B", 1)), stop_controls)
        stopped = await run_tools(stop_backup, [
            {"tool": "stop_payment_requests"}, {"tool": "request_payment"}],
            agent_name="stop_agent", session_id="stop-backup")
        require(decisions(stopped) == ["HOLD", "HOLD"]
                and all(step["result"]["sdk_request_sent"] is False for step in stopped["tool_results"]),
                "stop blocks later SDK submission")
        read = await run_tools(stop_original, [{"tool": "lookup_payment"}],
                               agent_name="recovery_agent", session_id="read-after-stop")
        require(decisions(read) == ["ACCEPT"]
                and read["tool_results"][0]["result"]["execution_outcome"] == "UNKNOWN",
                "read after stop preserves unresolved original")
        stop_snapshot = fixture_http(origin, "/sandbox/report", key=stop_key)
        require(stop_snapshot["synthetic_dispatches"] == 1
                and stop_snapshot["available_principal_minor"] == 0
                and stop_snapshot["original_lookup_redispatches"] == 0,
                "stop does not restore capacity")

    report = {"schema": "haltseal.adk-example.v1", "status": "PASS",
              "evidence": "ADK_FIXED_HTTP_FIXTURE_EVALUATED", "production": "NO_GO",
              "runtime": {"google-adk": version("google-adk"), "haltseal-payments": __version__,
                          "model": "scripted", "model_api_calls": 0},
              "checks": ["one original POST despite repeat and handoff", "exact-operation lookup, zero redispatch",
                         "host binding survives attempted argument override", "UNKNOWN reserves capacity",
                         "closure alone leaves old approval blocked", "one fresh fixture contender admitted",
                         "PAID blocks another route", "local stop sends no new request",
                         "stop preserves UNKNOWN and read recovery"],
              "main_fixture": {"adk_runs": runs, "host_injected_closure": closure, "snapshot": snapshot},
              "stop_fixture": {"adk_runs": [start, stopped, read], "snapshot": stop_snapshot},
              "limitations": ["Scripted model; no LLM decision quality evaluation",
                              "Fixed synthetic HTTP fixtures, not the payment kernel or source verifier",
                              "In-memory host journal and stop latch; no crash-safe or distributed journal",
                              "No native provider, customer workflow or production qualification",
                              "No A2A endpoint, Agent Card or remote delegation implementation"]}
    encoded = json.dumps(report)
    require(key not in encoded and stop_key not in encoded and '"api_key"' not in encoded,
            "credential-free report")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="ADK + unchanged SDK; local fixed fixtures, no real funds or model API key.")
    parser.add_argument("--output", type=Path, help="Write a new credential-free JSON record; never overwrite")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Choose a new output filename")
    with tempfile.TemporaryDirectory(prefix="haltseal-adk-") as temp:
        work = Path(temp)
        with host(ROOT / "tests/start-fixture.mjs", work, work / "fixture-state") as origin:
            report = asyncio.run(exercise(origin))
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, indent=2) + "\n")
    print("PASS: ADK repeat/handoff; UNKNOWN HOLD; stale HOLD; one fixture winner; PAID REFUSE; local STOP.")
    print("Main fixture dispatches: 2. Separate stop fixture: 1. Original lookup redispatches: 0.")
    print("Scripted model, real ADK runtime. Fixed HTTP fixtures; production NO_GO.")
    if args.output:
        print("Record: " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
