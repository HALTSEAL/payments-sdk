"""Build deterministic installable archives using only the Python stdlib."""
import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tomllib
import zipfile
from verify_provenance import ROOT, verify

DATE = (2026, 10, 6, 0, 0, 0)


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    return stream.getvalue()


def versions():
    project = tomllib.loads((ROOT / "packages/python/pyproject.toml").read_text())["project"]
    js = json.loads((ROOT / "packages/javascript/package.json").read_text())
    match = re.fullmatch(r"(\d+\.\d+\.\d+)rc(\d+)", project["version"])
    assert match, "Evaluation version required"
    assert js["version"] == match[1] + "-rc." + match[2], "Package versions disagree"
    assert '__version__ = "' + project["version"] + '"' in (ROOT / "packages/python/haltseal_payments_sdk/__init__.py").read_text()
    return project, js


def build(output):
    provenance = verify()
    project, js = versions()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    dist = "haltseal_payments_evaluation-" + project["version"] + ".dist-info"
    files = {"haltseal_payments_sdk/" + name: (ROOT / "packages/python/haltseal_payments_sdk" / name).read_bytes()
             for name in ["__init__.py", "_client.py", "_transport.py", "_types.py", "py.typed"]}
    metadata = ("Metadata-Version: 2.4\nName: " + project["name"] + "\nVersion: " + project["version"]
                + "\nSummary: " + project["description"] + "\nRequires-Python: " + project["requires-python"]
                + "\nLicense-Expression: MIT\nLicense-File: licenses/LICENSE\n"
                + "Project-URL: Source, https://github.com/HALTSEAL/payments-sdk\n"
                + "Project-URL: Documentation, https://haltseal.com/docs/payments/\n"
                + "Description-Content-Type: text/markdown\n\n" + (ROOT / "packages/python/README.md").read_text())
    files[dist + "/METADATA"] = metadata.encode()
    files[dist + "/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: HALTSEAL deterministic stdlib builder\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files[dist + "/licenses/LICENSE"] = (ROOT / "packages/python/LICENSE").read_bytes()
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        writer.writerow([name, "sha256=" + digest, len(data)])
    writer.writerow([dist + "/RECORD", "", ""])
    files[dist + "/RECORD"] = record.getvalue().encode()
    wheel_name = "haltseal_payments_evaluation-" + project["version"] + "-py3-none-any.whl"
    (output / wheel_name).write_bytes(zip_bytes(files))

    tarstream = io.BytesIO()
    assert js["files"] == ["index.mjs", "index.d.ts", "README.md", "LICENSE"], "Unexpected package files"
    with tarfile.open(fileobj=tarstream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(["package.json", *js["files"]]):
            data = (ROOT / "packages/javascript" / name).read_bytes()
            info = tarfile.TarInfo("package/" + name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    tarball_name = "haltseal-payments-evaluation-" + js["version"] + ".tgz"
    with (output / tarball_name).open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as archive:
            archive.write(tarstream.getvalue())

    allowlist = json.loads((ROOT / "tools/release-files.json").read_text())
    assert allowlist == sorted(set(allowlist)), "Sorted, unique file allowlist required"
    source = {}
    for name in allowlist:
        path = PurePosixPath(name)
        assert not path.is_absolute() and ".." not in path.parts and "\\" not in name, name
        local = ROOT / name
        assert local.is_file() and not local.is_symlink(), name
        source["haltseal-payments-sdk-" + js["version"] + "/" + name] = local.read_bytes()
    source_name = "haltseal-payments-sdk-" + js["version"] + "-source.zip"
    (output / source_name).write_bytes(zip_bytes(source))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
    manifest = {"schema": "haltseal.payments-sdk.release.v1", "tag": "v" + js["version"],
                "python_version": project["version"], "javascript_version": js["version"],
                "production": "NO_GO", "scope": "Evaluation clients and synthetic HTTP fixtures only",
                "client_baseline": provenance["files"], "runtime_migration": provenance["runtime_migration"], "files": dict(hashes),
                "source_files": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in allowlist}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    hashes["manifest.json"] = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text("".join(sha + "  " + name + "\n" for name, sha in sorted(hashes.items())))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--expect-tag")
    args = parser.parse_args()
    if args.expect_tag:
        assert args.expect_tag == "v" + versions()[1]["version"], "Tag/package version mismatch"
    result = build(args.output)
    print("Built " + result["tag"] + ": wheel, tarball, source, manifest, checksums.")
