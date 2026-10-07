"""Validate the exact GitHub release bytes before they reach a registry."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile
from build_release import versions


def verify(directory, tag, expected=None):
    directory = Path(directory)
    python, javascript = versions()
    assert tag == "v" + javascript["version"], "Tag/package mismatch"
    assert python["name"] == "haltseal-payments" and javascript["name"] == "@haltseal/payments"
    wheel = "haltseal_payments-" + python["version"] + "-py3-none-any.whl"
    tarball = "haltseal-payments-" + javascript["version"] + ".tgz"
    source = "haltseal-payments-sdk-" + javascript["version"] + "-source.zip"
    required = {wheel, tarball, "manifest.json", "SHA256SUMS.txt"}
    present = {p.name for p in directory.iterdir()}
    assert required <= present and present <= required | {source}, "Unexpected release download surface"
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["tag"] == tag and manifest["production"] == "NO_GO"
    assert manifest["packages"] == {"python": python["name"], "javascript": javascript["name"]}
    checksums = {}
    for line in (directory / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert name not in checksums and len(digest) == 64
        checksums[name] = digest
    for name in [wheel, tarball, "manifest.json", *([source] if source in present else [])]:
        path = directory / name
        assert path.is_file() and not path.is_symlink()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert checksums[name] == digest, "Release checksum mismatch: " + name
        if name != "manifest.json":
            assert manifest["files"][name] == digest, "Manifest mismatch: " + name
        if expected:
            assert (Path(expected) / name).read_bytes() == path.read_bytes(), "GitHub/build bytes differ: " + name
    with zipfile.ZipFile(directory / wheel) as archive:
        prefix = "haltseal_payments-" + python["version"] + ".dist-info/"
        metadata = BytesParser().parsebytes(archive.read(prefix + "METADATA"))
        assert metadata["Name"] == python["name"] and metadata["Version"] == python["version"]
        assert not metadata.get_all("Requires-Dist"), "Unexpected Python runtime dependency"
        assert metadata["License-Expression"] == "MIT" and metadata["License-File"] == "LICENSE"
        assert archive.read(prefix + "licenses/LICENSE")
        assert "haltseal_payments_sdk/sandbox.py" in archive.namelist()
    with tarfile.open(directory / tarball) as archive:
        members = archive.getmembers()
        assert all(m.isfile() and m.name.startswith("package/") and ".." not in Path(m.name).parts for m in members)
        metadata = json.loads(archive.extractfile("package/package.json").read())
        assert metadata["name"] == javascript["name"] and metadata["version"] == javascript["version"]
        assert metadata["bin"] == {"haltseal-payments-demo": "sandbox.mjs"}
        assert metadata["publishConfig"] == {"access": "public", "tag": "next"}
        assert not any(metadata.get(k) for k in ["scripts", "dependencies", "optionalDependencies"])
        assert archive.getmember("package/sandbox.mjs").mode & 0o111
    return {"tag": tag, "wheel": wheel, "tarball": tarball, "status": "PASS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected")
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, args.tag, args.expected), sort_keys=True))
