"""Isolated package installation and short-lived loopback test hosts."""
import contextlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import venv
from verify_provenance import ROOT


def run(command, cwd, capture=False):
    result = subprocess.run([str(x) for x in command], cwd=cwd, check=True, text=True,
                            capture_output=capture, env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    return result.stdout.strip() if capture else None


def install(work, artifacts):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    py = work / "python"
    venv.create(py, with_pip=True)
    python = py / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheel = next(Path(artifacts).glob("*.whl"))
    run([python, "-m", "pip", "install", "--no-index", "--no-deps", wheel], work, capture=True)
    installed = run([python, "-I", "-c", "import haltseal_payments_sdk; print(haltseal_payments_sdk.__file__)"], work, capture=True)
    assert Path(installed).is_relative_to(py), "Python imported source instead of installed wheel"
    js = work / "javascript"
    js.mkdir()
    (js / "package.json").write_text('{"private":true,"type":"module"}\n')
    tarball = next(Path(artifacts).glob("*.tgz"))
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm, "npm is required"
    run([npm, "install", "--ignore-scripts", "--no-audit", "--no-fund", "--offline", tarball], js, capture=True)
    assert (js / "node_modules/@haltseal/payments/index.mjs").is_file()
    return python, js


@contextlib.contextmanager
def host(script, work, *args):
    process = subprocess.Popen(["node", str(script), *map(str, args)], cwd=work,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ready = queue.Queue()
    threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
    try:
        try:
            origin = ready.get(timeout=15).strip()
        except queue.Empty:
            raise RuntimeError("Local fixture host did not start") from None
        assert origin.startswith("http://127.0.0.1:"), "Unexpected fixture host: " + origin
        yield origin
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        process.stdout.close(); process.stderr.close()


def examples(work, python, js):
    with host(ROOT / "tests/start-fixture.mjs", work, Path(work) / "fixture-state") as origin:
        run([python, "-I", ROOT / "examples/recover-original/demo.py", origin], work)
        shutil.copyfile(ROOT / "examples/recover-original/demo.mjs", js / "demo.mjs")
        run(["node", js / "demo.mjs", origin], work)
    records = [json.loads((Path(work) / name).read_text()) for name in
               ["python-synthetic-result.json", "javascript-synthetic-result.json"]]
    for record in records:
        assert record["synthetic_dispatches"] == 2
        assert record["original_lookup_redispatches"] == 0
        assert len(record["sdk_results"]) == 6
        assert "api_key" not in json.dumps(record)
    signatures = [[(step["result"].get("decision"), step["result"].get("state"),
                    step["result"].get("execution_outcome")) for step in r["sdk_results"]] for r in records]
    assert signatures[0] == signatures[1], "Recovery examples disagree"
    print("Synthetic dispatches: 2. Original lookup redispatches: 0.")
    return records
