#!/usr/bin/env python3
"""Correctness-only differential check on the five existing MIPLIB3 inputs.

Uses the existing suite's exact parser and assignment checker, without editing
the suite or seeding the solver from published reference solutions. Timing is
recorded for diagnosis only; this is not an authoritative performance trial.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "experiments" / "solver-bench"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SUITE))
import miplib_import  # noqa: E402
import validate  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_nonfinite(token):
    raise ValueError("Nonfinite JSON number: " + token)


def finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        reject_nonfinite(token)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if not math.isfinite(args.limit_seconds) or args.limit_seconds <= 0:
        parser.error("limit must be positive and finite")
    binary = args.binary.resolve(strict=True)
    report = {"schema_version": 1, "purpose": "correctness_only_not_performance",
              "platform": platform.platform(), "binary_sha256": sha(binary),
              "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
              "limit_seconds": args.limit_seconds, "cases": []}
    for name, (_, _, optimum, digest) in miplib_import.MODELS.items():
        path = SUITE / "miplib-cache" / (name + ".mps")
        case = {"name": name, "input_sha256": sha(path), "expected_objective": optimum, "passed": False}
        try:
            if case["input_sha256"] != digest:
                raise ValueError("Existing published input hash changed")
            exact, metadata = miplib_import.parse_mps(path.read_text(encoding="ascii"))
            started = time.perf_counter()
            proc = subprocess.run([str(binary), str(path), "--time-limit", str(args.limit_seconds),
                                   "--relative-gap", "0", "--absolute-gap", "0", "--seed", "0"],
                                  text=True, capture_output=True, timeout=args.limit_seconds + 10)
            case["process_wall_seconds"] = time.perf_counter() - started
            if proc.stderr:
                case["stderr"] = proc.stderr[-4000:]
            result = json.loads(proc.stdout, parse_constant=reject_nonfinite, parse_float=finite_float)
            case["result"] = result
            if proc.returncode != 0 or result["termination"] != "optimal" or not result["solution_validated"]:
                raise ValueError("No validated optimal result within the correctness-run limit")
            for key in ("objective", "best_bound"):
                if type(result[key]) not in (int, float) or not math.isfinite(result[key]):
                    raise ValueError("Missing or nonfinite numeric " + key)
            names, values = result["variable_names"], result["values"]
            if len(names) != len(values) or len(names) != len(set(names)):
                raise ValueError("Missing or ambiguous witness column mapping")
            mapped = dict(zip(names, values))
            if set(mapped) != set(metadata["column_names"]):
                raise ValueError("Imported variable set differs from exact parser")
            rounded = []
            for column in metadata["column_names"]:
                value = mapped[column]
                if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value-round(value)) > 1e-6:
                    raise ValueError("Witness is not numerically integral")
                rounded.append(round(value))
            checked = validate.validate_assignment(exact, rounded)
            if not checked["valid"]:
                raise ValueError("Independent exact original-input witness check failed: " + str(checked))
            recovered = (metadata["sign"] * Fraction(checked["objective"], metadata["objective_scale"])
                         + Fraction(metadata["original_objective_offset"]))
            if recovered != optimum or abs(result["objective"]-float(recovered)) > 1e-6:
                raise ValueError("Independent objective does not equal published optimum")
            if result["best_bound"] is None or abs(result["best_bound"]-optimum) > 1e-6:
                raise ValueError("Reported best bound does not close at the known optimum")
            case["independent_exact_witness_objective"] = str(recovered)
            case["passed"] = True
        except (ValueError, KeyError, TypeError, OverflowError, subprocess.TimeoutExpired) as error:
            case["error"] = str(error)
        report["cases"].append(case)
        print(name + ": " + ("PASS" if case["passed"] else "FAIL " + case.get("error", "")), flush=True)
    report["passed"] = all(case["passed"] for case in report["cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
