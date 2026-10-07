"""One command: verified packages, two installed clients, local recovery."""
import argparse
from pathlib import Path
import shutil
import tempfile
from build_release import build
from run_installed import install, examples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Retain synthetic result JSON in this directory")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="haltseal-sdk-") as temp:
        work = Path(temp)
        build(work / "dist")
        python, js = install(work / "installed", work / "dist")
        examples(work, python, js)
        if args.output:
            destination = Path(args.output).resolve()
            destination.mkdir(parents=True, exist_ok=True)
            for name in ["python-synthetic-result.json", "javascript-synthetic-result.json"]:
                shutil.copyfile(work / name, destination / name)
            print("Synthetic records: " + str(destination))


if __name__ == "__main__":
    main()
