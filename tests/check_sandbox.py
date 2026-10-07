"""Exercise the installed demos with one runtime and fail before financial calls.

The parent test process owns the Node fixture. Each demo's PATH exposes only
its own runtime; neither installed client starts another language or server.
"""
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def check(work, python, javascript, host_origin):
    work, javascript = Path(work), Path(javascript)
    node = shutil.which("node")
    assert node
    runtimes = {}
    for language, executable in [("python", python), ("javascript", node)]:
        directory = work / (language + "-only-path")
        directory.mkdir()
        name = "python" if language == "python" else "node"
        if os.name == "nt":
            # Windows Python needs the original DLL/runtime directory.
            runtimes[language] = str(Path(executable).parent)
        else:
            (directory / name).symlink_to(executable)
            runtimes[language] = str(directory)
    bin_path = javascript / "node_modules/.bin/haltseal-payments-demo"
    assert bin_path.exists(), "Installed npm demo binary missing"

    def command(language, origin, output):
        args = ([str(python), "-I", "-m", "haltseal_payments_sdk.sandbox"] if language == "python"
                else [node, str(bin_path)])
        return [*args, "--origin", origin, "--output", str(output)]

    def invoke(language, origin, output):
        env = {**os.environ, "PATH": runtimes[language]}
        return subprocess.run(command(language, origin, output), cwd=work, env=env,
                              text=True, capture_output=True, timeout=30)

    records = []
    for language in ["python", "javascript"]:
        output = work / (language + "-single-runtime.json")
        result = invoke(language, host_origin, output)
        assert result.returncode == 0, (language, result.stdout, result.stderr)
        assert "Original lookup redispatches: 0" in result.stdout
        record = json.loads(output.read_text())
        assert record["sdk_package"] == ("haltseal-payments" if language == "python" else "@haltseal/payments")
        assert record["production"] == "NO_GO" and record["sandbox_profile"] == "fixed-http-fixtures"
        assert record["synthetic_dispatches"] == 2 and record["original_lookup_redispatches"] == 0
        assert [step["result"]["decision"] for step in record["sdk_results"]] == ["ACCEPT", "HOLD", "OBSERVED", "HOLD", "ACCEPT", "REFUSE"]
        assert '"api_key"' not in json.dumps(record) and "hs_sandbox_" not in output.read_text()
        records.append(record)
    signatures = [[(step["result"].get("decision"), step["result"].get("state"),
                    step["result"].get("execution_outcome")) for step in record["sdk_results"]] for record in records]
    assert signatures[0] == signatures[1]

    requests = []
    mode = ["wrong-profile"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(self.path)
            if mode[0] == "redirect":
                self.send_response(307)
                self.send_header("Location", "/redirect-target")
                self.end_headers()
                return
            body = {"sandbox_profile": "real-payment-service", "production": "GO",
                    "api_origin": test_origin, "api_key": "hs_sandbox_" + "1" * 32,
                    "obligation_id": "sandbox-cash-4822"}
            if mode[0] == "wrong-origin":
                body.update(sandbox_profile="fixed-http-fixtures", production="NO_GO",
                            api_origin="https://example.com")
            elif mode[0] == "unavailable":
                body = {"error": "hs_sandbox_" + "1" * 32}
            self.send_response(503 if mode[0] == "unavailable" else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    test_origin = "http://127.0.0.1:" + str(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = 0
    try:
        for language in ["python", "javascript"]:
            for case in ["wrong-profile", "wrong-origin", "redirect", "unavailable"]:
                mode[0] = case
                before = len(requests)
                output = work / (language + "-" + case + ".json")
                result = invoke(language, test_origin, output)
                assert result.returncode == 1 and not output.exists(), (language, case, result)
                assert requests[before:] == ["/sandbox/session"], "Redirect or financial request escaped fixture gate"
                assert "hs_sandbox_" not in result.stdout + result.stderr
                cases += 1
            for origin in ["https://example.com", test_origin + "/v1", "http://user:secret@127.0.0.1:80"]:
                before = len(requests)
                result = invoke(language, origin, work / (language + "-invalid-origin.json"))
                assert result.returncode == 1 and len(requests) == before
                cases += 1
            output = work / (language + "-existing.json")
            output.write_text("preserved existing record\n")
            before = len(requests)
            result = invoke(language, test_origin, output)
            assert result.returncode == 1 and len(requests) == before
            assert output.read_text() == "preserved existing record\n"
            cases += 1
    finally:
        server.shutdown()
        server.server_close()
    print("PASS: Python-only and Node-only installed demos; " + str(cases) + " fixture/origin/redirect/output gates.")
    return {"single_runtime_languages": 2, "sandbox_boundary_cases": cases, "record_parity": "IDENTICAL"}
