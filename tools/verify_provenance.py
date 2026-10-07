"""Verify public RC4 runtime/types and copied public fixtures, offline."""
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def verify():
    baseline = ROOT / "release-baseline"
    provenance = json.loads((baseline / "provenance.json").read_text())
    migration = json.loads((baseline / "v2-migration.json").read_text())
    registry = json.loads((baseline / "registry-beta.json").read_text())
    old_runtime = {}
    for name, record in provenance["files"].items():
        archive = baseline / name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == record["sha256"], name
        if name.endswith(".whl"):
            with zipfile.ZipFile(archive) as source:
                for path in source.namelist():
                    if path.startswith("haltseal_payments_sdk/"):
                        old_runtime["packages/python/" + path] = hashlib.sha256(source.read(path)).hexdigest()
                license_path = next(p for p in source.namelist() if p.endswith("/licenses/LICENSE"))
                assert source.read(license_path) == (ROOT / "packages/python/LICENSE").read_bytes()
        else:
            with tarfile.open(archive) as source:
                for name in ["index.mjs", "index.d.ts", "LICENSE"]:
                    old_runtime["packages/javascript/" + name] = hashlib.sha256(source.extractfile("package/" + name).read()).hexdigest()
    assert migration["from_version"] == "0.1.0-rc.4" and migration["to_version"] == "0.2.0-rc.1"
    assert migration["baseline_runtime_sha256"] == old_runtime, "RC4 runtime provenance changed"
    expected = {"packages/python/haltseal_payments_sdk/" + name for name in ["__init__.py", "_client.py", "_transport.py", "_types.py", "py.typed"]}
    expected |= {"packages/javascript/index.mjs", "packages/javascript/index.d.ts"}
    assert set(migration["reviewed_runtime_sha256"]) == expected, "Unexpected reviewed runtime surface"
    for name, sha in migration["reviewed_runtime_sha256"].items():
        data = (ROOT / name).read_bytes()
        if name.endswith("/__init__.py"):
            data = data.replace(b'__version__ = "0.2.0rc2"', b'__version__ = "0.2.0rc1"')
        assert hashlib.sha256(data).hexdigest() == sha, "SDK v2 client changed: " + name
    assert registry["from_version"] == "0.2.0-rc.1" and registry["to_version"] == "0.2.0-rc.2"
    assert set(registry["reviewed_runtime_sha256"]) == expected | {"packages/python/haltseal_payments_sdk/sandbox.py", "packages/javascript/sandbox.mjs"}
    for name, sha in registry["reviewed_runtime_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, "Registry beta runtime changed: " + name
    for name, sha in provenance["fixture_source"]["files"].items():
        assert hashlib.sha256((ROOT / "tests/sandbox" / name).read_bytes()).hexdigest() == sha, name
    assert (ROOT / "LICENSE").read_bytes() == (ROOT / "packages/python/LICENSE").read_bytes()
    return {**provenance, "runtime_migration": migration, "registry_beta": registry}


if __name__ == "__main__":
    verify()
    print("PASS: unchanged public RC4 archives, reviewed SDK v2 migration and fixture provenance.")
