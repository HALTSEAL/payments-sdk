"""Type-check an integration against the installed ESM package exports.

Development check only: downloads a pinned compiler via npm. The SDK and
offline quickstart require no runtime dependencies or registry downloads.
"""
from pathlib import Path
import shutil
import tempfile
from build_release import build, ROOT
from run_installed import install, run

with tempfile.TemporaryDirectory(prefix="haltseal-sdk-types-") as directory:
    work = Path(directory)
    build(work / "dist")
    _, javascript = install(work / "installed", work / "dist")
    shutil.copyfile(ROOT / "tests/types.mts", javascript / "integration.mts")
    npm = shutil.which("npm.cmd" if __import__("os").name == "nt" else "npm")
    run([npm, "exec", "--yes", "--package=typescript@5.9.3", "--", "tsc", "--noEmit", "--strict",
         "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "integration.mts"], javascript)
print("PASS: TypeScript integration against installed package exports.")
