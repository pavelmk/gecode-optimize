#!/usr/bin/env python3
"""Run correctness checks, then optionally the serial benchmark protocol."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin", type=Path, default=ROOT / "build/lp-relaxation/bin")
    parser.add_argument("--tests-only", action="store_true")
    args = parser.parse_args()
    results = HERE / "results"
    results.mkdir(exist_ok=True)
    evidence = []
    names = ["test-certificate", "test-backend", "test-propagator"]
    names += [name for name in ["test-certificate-unsupported", "test-certificate-sanitized",
                               "test-propagator-sanitized"] if (args.bin / name).is_file()]
    for name in names:
        binary = args.bin / name
        run = subprocess.run([str(binary)], check=True, text=True, capture_output=True)
        evidence.append(dict(test=name, passed=True, stdout=run.stdout, stderr=run.stderr,
                             binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()))
        print(run.stdout.strip(), flush=True)
    (results / "tests.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if args.tests_only:
        return
    common = [sys.executable, str(HERE / "bench.py"), "--bin", str(args.bin)]
    subprocess.run(common + ["--split", "tiny,control", "--configs",
                             "stock-afc,disabled-afc,root-afc,node-afc", "--repeats", "1",
                             "--output", str(results / "correctness.jsonl")], check=True)
    subprocess.run(common + ["--split", "dev", "--repeats", "3",
                             "--output", str(results / "development.jsonl")], check=True)
    # This is a rerun of the frozen protocol, not a new search for a winner.
    subprocess.run(common + ["--split", "test", "--repeats", "5",
                             "--output", str(results / "held-out.jsonl")], check=True)
    subprocess.run([sys.executable, str(HERE / "analyze.py")], check=True)


if __name__ == "__main__":
    main()
