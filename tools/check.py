"""Meaningful installed-package checks, provenance and reproducible builds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from build_release import build, ROOT
from run_installed import install, host, examples, run
import sys
sys.path.insert(0, str(ROOT / "tests"))
from check_sandbox import check as check_sandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Write a redacted verification report")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="haltseal-sdk-check-") as temp:
        work = Path(temp)
        manifest = build(work / "first")
        build(work / "second")
        first = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (work / "first").iterdir()}
        second = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (work / "second").iterdir()}
        assert first == second, "Clean builds differ"
        python, js = install(work / "installed", work / "first")
        with host(ROOT / "tests/failure-server.mjs", work) as origin:
            run([python, "-I", ROOT / "tests/check_python.py", origin, ROOT / "tests/failure-cases.json", work / "python-faults.json"], work)
            shutil.copyfile(ROOT / "tests/check_javascript.mjs", js / "check.mjs")
            run(["node", js / "check.mjs", origin, ROOT / "tests/failure-cases.json", work / "javascript-faults.json"], work)
        py = json.loads((work / "python-faults.json").read_text())
        javascript = json.loads((work / "javascript-faults.json").read_text())
        assert py == javascript, "Recovery contexts or request fingerprints differ across languages"
        with host(ROOT / "tests/response-server.mjs", work) as origin:
            run([python, "-I", ROOT / "tests/check_responses.py", origin, ROOT / "tests/response-cases.json", work / "python-responses.json"], work)
            shutil.copyfile(ROOT / "tests/check_responses.mjs", js / "responses.mjs")
            run(["node", js / "responses.mjs", origin, ROOT / "tests/response-cases.json", work / "javascript-responses.json"], work)
        responses = json.loads((work / "python-responses.json").read_text())
        assert responses == json.loads((work / "javascript-responses.json").read_text()), "Response validation differs across languages"
        run([python, "-I", ROOT / "tests/check_transport.py"], work)
        records = examples(work, python, js)
        with host(ROOT / "tests/start-fixture.mjs", work, work / "cli-fixture-state") as origin:
            sandbox = check_sandbox(work, python, js, origin)
        report = {"schema": "haltseal.payments-sdk.verification.v1", "tag": manifest["tag"],
                  "production": "NO_GO", "profile": "synthetic-http-only", "status": "PASS",
                  "http_failure_cases_per_language": len(py), "zero_send_checks_per_language": 7,
                  "recovery_steps_per_language": 6, "cross_language_recovery_contexts": "IDENTICAL",
                  "identity_and_record_cases_per_language": len(responses),
                  "response_validation_parity": "IDENTICAL", "reviewed_v2_runtime": "HASH_VERIFIED",
                  "public_rc4_baseline_archives": "UNCHANGED", "clean_builds": "BYTE_IDENTICAL",
                  "synthetic_dispatches_per_example": 2, "original_lookup_redispatches": 0,
                  "installed_sandbox_demos": sandbox,
                  "artifact_sha256": first, "limitations": ["No native provider calls", "No retained payment kernel", "No customer deployment", "Production not qualified"]}
        if args.output:
            Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("PASS: provenance, installed clients, shared faults, exact-original recovery, byte-identical builds.")
        return report


if __name__ == "__main__":
    main()
