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
    for name, record in provenance["files"].items():
        archive = baseline / name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == record["sha256"], name
        if name.endswith(".whl"):
            with zipfile.ZipFile(archive) as source:
                for path in source.namelist():
                    if path.startswith("haltseal_payments_sdk/"):
                        assert source.read(path) == (ROOT / "packages/python" / path).read_bytes(), path
                license_path = next(p for p in source.namelist() if p.endswith("/licenses/LICENSE"))
                assert source.read(license_path) == (ROOT / "packages/python/LICENSE").read_bytes()
        else:
            with tarfile.open(archive) as source:
                for name in ["index.mjs", "index.d.ts", "LICENSE"]:
                    assert source.extractfile("package/" + name).read() == (ROOT / "packages/javascript" / name).read_bytes(), name
    for name, sha in provenance["fixture_source"]["files"].items():
        assert hashlib.sha256((ROOT / "tests/sandbox" / name).read_bytes()).hexdigest() == sha, name
    assert (ROOT / "LICENSE").read_bytes() == (ROOT / "packages/python/LICENSE").read_bytes()
    return provenance


if __name__ == "__main__":
    verify()
    print("PASS: public RC4 runtime/type and fixture provenance.")
