"""Check the installed demos against the public fixed HTTP fixture endpoint."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from build_release import build
from run_installed import install


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="haltseal-hosted-check-") as directory:
        work = Path(directory)
        manifest = build(work / "dist")
        python, javascript = install(work / "installed", work / "dist")
        commands = [
            ("python", [str(python), "-I", "-m", "haltseal_payments_sdk.sandbox"]),
            ("javascript", [shutil.which("node"), str(javascript / "node_modules/.bin/haltseal-payments-demo")]),
        ]
        records = {}
        for language, command in commands:
            output = work / (language + ".json")
            result = subprocess.run([*command, "--output", str(output)], cwd=work,
                                    text=True, capture_output=True, timeout=120)
            if result.returncode:
                raise RuntimeError(language + " hosted fixture exercise did not complete; no release qualification")
            data = json.loads(output.read_text())
            assert '"api_key"' not in output.read_text() and "hs_sandbox_" not in output.read_text()
            decisions = [s["result"]["decision"] for s in data["sdk_results"]]
            assert decisions == ["ACCEPT", "HOLD", "OBSERVED", "HOLD", "ACCEPT", "REFUSE"]
            assert data["synthetic_dispatches"] == 2 and data["original_lookup_redispatches"] == 0
            records[language] = {"sdk_version": data["sdk_version"], "sdk_package": data["sdk_package"],
                                 "decisions": decisions, "synthetic_dispatches": 2, "lookup_redispatches": 0}
        report = {"schema": "haltseal.sdk.hosted-demo-verification.v1", "tag": manifest["tag"],
                  "origin": "https://haltseal.com", "status": "PASS", "production": "NO_GO",
                  "scope": "Installed clients over fixed public HTTP fixtures, not native-provider or customer qualification",
                  "languages": records}
        Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("PASS: installed Python and Node hosted demos; six recovery steps; zero lookup redispatches.")


if __name__ == "__main__":
    main()
