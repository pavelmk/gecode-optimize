#!/usr/bin/env python3
"""Bounded correctness/regression panel for PREBUILT Gecode binaries (POSIX).

Windows containment is implemented for CI verification, with production support
disabled until those platform tests provide evidence.
"""
import time
ENTRY = time.monotonic()
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import threading

NATIVE_CASES = (
    ("cp_distinct", "Int::Distinct::Dom::Dense"),
    ("cp_element", "Int::Element::Matrix::Int::IntVar::XY"),
    ("cp_cumulative", "Int::Cumulative::Man::Fix::0::2::[1,1,1,1]::[1,1,1,1]::Def+B+A"),
    ("cp_search", "Search::DFS::Sol::Binary::Binary::Binary::2::1::1"),
)
INTEGER_ORACLE = min(4*n + 5*k + 2 for n in range(-3, 8) for k in range(6) if 2*n+3*k >= 7)
RECOURSE_ORACLE = [min(-4 + 7*b + 3*n + 1.5*max(0, d-3*n)
                        for b in range(2) for n in range(6) if max(0, d-3*n) <= 25*b)
                   for d in (3, 7, 11, 17, 19, 23)]
NATIVE_OBJECTIVES = [-2*n + 3*s - 4*b + (1-b) - 7
                     for b in range(2) for n in range(-3, 4) for s in (0, 2, 3, 4)
                     if (-2 <= 2*n-s+b <= 1 if b else n+s <= 2)]
HYBRID_OBJECTIVES = [4*n + 5*k + 2 for n in range(-3, 8) for k in range(6) if 7 <= 2*n+3*k <= 12]
PRESOLVED_OBJECTIVES = [5 + 2*y for y in range(-2, 3) if 4 <= 6-2*y <= 8]
START_OBJECTIVES = [x - 10*b + 3 for b in (0, 1) for x in range(5) if not b or x >= 3]
REGULAR_OBJECTIVES = [a+b+c for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)
                      if ((a == 1) + (b == 1) + (c == 1)) % 2 == 0]
OPTIMIZE_CASES = {
    "native_neighborhoods": ("optimal", [-29]),
    "lp_sensitivity": ("sensitivity_checked", []),
    "lp_evidence": ("evidence_checked", []),
    "scenario_batches": ("optimal", [5, 9, -11, 7]),
    "native_regular": ("optimal", [min(REGULAR_OBJECTIVES), max(REGULAR_OBJECTIVES)]),
    "lp_observations": ("optimal", [15, 19]),
    "lp_min_offset": ("optimal", [4]), "lp_max_offset": ("optimal", [15]),
    "bounded_integer": ("optimal", [INTEGER_ORACLE]), "mixed_recourse": ("optimal", RECOURSE_ORACLE),
    "indicators_boolean": ("optimal", [-13]), "semis": ("optimal", [8, -1]),
    "multiobjective": ("optimal", [14, 1]), "infeasible": ("infeasible", []),
    "unbounded": ("unbounded", []), "edits_io": ("optimal", [5, 7, 7, 7, -1]),
    "limit_contracts": ("contract_pass", []),
    "session_reoptimization": ("optimal", [5, 13, 18, -6, 2, 3, 5, 5]),
    "diagnostics_groups": ("irreducible", []),
    "native_exact_reified": ("optimal", [min(NATIVE_OBJECTIVES), max(NATIVE_OBJECTIVES)]),
    "native_globals": ("optimal", [7, 30]),
    "c_api_ownership": ("optimal", [5.75, 6.25]),
    "feasibility_repair": ("optimal", [1, -1, 0, -2]),
    "native_checked_lp": ("optimal", [min(HYBRID_OBJECTIVES), max(HYBRID_OBJECTIVES)]),
    "solution_pool": ("optimal", sorted(n + max(0, 4-2*n) - 1 for n in range(3))),
    "integer_presolve": ("optimal", [min(PRESOLVED_OBJECTIVES), max(PRESOLVED_OBJECTIVES)]),
    "native_frontier_bounds": ("optimal", [-17, -15, -17, 17, 15, 17]),
    "convex_quadratic": ("optimal", [3.5, 2.5]),
    "native_root_covers": ("optimal", [15, 19]),
    "native_binary_branching": ("optimal", [-17, 17]),
    "native_complete_start": ("optimal", [min(START_OBJECTIVES), max(START_OBJECTIVES)]),
}
REQUIRED = [name for name, _ in NATIVE_CASES] + list(OPTIMIZE_CASES)
MAX_OUTPUT = 65536
_CONTAINMENT = None


def containment_module():
    # This file is also loaded directly through importlib by runner tests, where
    # its directory need not be on sys.path. Do not change the caller's sys.path.
    global _CONTAINMENT
    if _CONTAINMENT is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gecode_fast_process_containment", Path(__file__).with_name("process_containment.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CONTAINMENT = module
    return _CONTAINMENT


def platform_support_error(name):
    if name == "posix":
        return None
    if name == "nt":
        if containment_module().WINDOWS_RUNTIME_VERIFIED:
            return None
        return ("Unsupported: Windows FAST support is unfinished. Job Object containment "
                "requires real Windows CI verification before this command is enabled.")
    return "Unsupported: this platform has no verified process-tree containment"


class Failure(RuntimeError):
    pass


class Budget:
    """One outer monotonic deadline; reserve time for cleanup and final report."""
    def __init__(self, seconds, start=None, watchdog=False):
        self.start = time.monotonic() if start is None else start
        self.deadline = self.start + seconds
        self.work_deadline = self.deadline - min(0.75, seconds / 4)
        self.pid = None
        self.containment = None
        if watchdog:
            timer = threading.Timer(max(0, self.deadline-time.monotonic()), self.emergency)
            timer.daemon = True
            timer.start()

    def emergency(self):
        # Do not risk blocking on output from the last-resort watchdog.
        try:
            self.kill_group()
        finally:
            os._exit(124)

    def kill_group(self):
        if self.containment is not None:
            self.containment.terminate()
        elif self.pid is not None:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def remaining(self):
        return max(0.0, self.work_deadline-time.monotonic())

    def check(self):
        if self.remaining() <= 0:
            raise Failure("whole-run wall budget exhausted")


def sha256(path, budget):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            budget.check()
            data = stream.read(1024*1024)
            if not data:
                return digest.hexdigest()
            digest.update(data)


def run_command(command, budget, seconds, directory):
    """Capture bounded output without inherited-pipe hangs; kill descendants."""
    budget.check()
    if budget.containment is not None:
        raise Failure("prior Windows Job Object cleanup failed; refusing another launch")
    started = time.monotonic()
    finish = min(budget.work_deadline, started+seconds)
    result = {"command": [str(x) for x in command], "returncode": None, "stdout": "", "stderr": ""}
    proc = None
    with tempfile.TemporaryFile(dir=directory) as stdout, tempfile.TemporaryFile(dir=directory) as stderr:
        try:
            if os.name == "nt":
                proc = containment_module().WindowsJobProcess()
                # The watchdog must know the job owner before ANY process exists.
                budget.containment = proc
                proc.start(command, stdout, stderr, directory)
            else:
                proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        start_new_session=True, cwd=directory, close_fds=True)
                budget.pid = proc.pid
            while proc.poll() is None:
                if max(os.fstat(stdout.fileno()).st_size, os.fstat(stderr.fileno()).st_size) > MAX_OUTPUT:
                    raise Failure("subprocess output limit exceeded")
                if time.monotonic() >= finish:
                    raise Failure("subprocess wall deadline exceeded")
                time.sleep(min(0.01, max(0, finish-time.monotonic())))
            if time.monotonic() >= finish:
                raise Failure("subprocess completed after wall deadline")
        except (Failure, OSError, ValueError) as error:
            result["error"] = str(error)
        finally:
            if proc is not None:
                # Also terminate descendants after a successful parent exit.
                reserve = max(0, min(0.2, budget.deadline-time.monotonic()))
                if budget.containment is not None:
                    try:
                        proc.cleanup(timeout=reserve)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        result["error"] = "Windows subprocess cleanup failed: " + str(error)
                    # On a failed handle close, retain the job for the watchdog.
                    if proc.job is None:
                        budget.containment = None
                else:
                    budget.kill_group()
                    try:
                        proc.wait(timeout=max(0.001, min(0.2, budget.deadline-time.monotonic())))
                    except subprocess.TimeoutExpired:
                        result["error"] = "subprocess could not be reaped within cleanup reserve"
                result["returncode"] = proc.returncode
            budget.pid = None
            for label, stream in (("stdout", stdout), ("stderr", stderr)):
                stream.seek(0)
                data = stream.read(MAX_OUTPUT+1)
                if len(data) > MAX_OUTPUT:
                    result["error"] = "subprocess output limit exceeded"
                result[label] = data[:MAX_OUTPUT].decode("utf-8", errors="replace")
    result["wall_seconds"] = time.monotonic()-started
    return result


def validate_output(name, result, native=None):
    if result.get("error"):
        raise Failure(result["error"])
    if result["returncode"] != 0:
        raise Failure("subprocess failed with exit code " + str(result["returncode"]))
    if result["stderr"]:
        raise Failure("unexpected subprocess stderr")
    if native is not None:
        if result["stdout"].strip() != native + " +":
            raise Failure("required native case missing, duplicated, or failed")
        return {"status": "passed_native_oracle", "checks": 1, "objectives": [],
                "backend": "native Gecode CP"}
    def reject_constant(value):
        raise Failure("nonfinite JSON number: " + value)
    try:
        payload = json.loads(result["stdout"], parse_constant=reject_constant)
    except (ValueError, TypeError) as error:
        raise Failure("invalid panel JSON: " + str(error)) from error
    if not isinstance(payload, dict) or payload.get("case") != name:
        raise Failure("wrong or missing panel case")
    status, expected = OPTIMIZE_CASES[name]
    if payload.get("status") != status:
        raise Failure("unexpected optimization status")
    if type(payload.get("checks")) is not int or payload["checks"] < 1:
        raise Failure("panel performed no checks")
    for field in ("backend", "backend_version"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise Failure("missing backend identity")
    native_bridge = name in ("native_exact_reified", "native_globals", "native_regular", "native_checked_lp", "integer_presolve", "native_frontier_bounds", "native_root_covers", "native_binary_branching", "native_complete_start", "native_neighborhoods")
    expected_backend = {"native_neighborhoods": "Gecode native frontier + BinaryHamming", "native_checked_lp": "Gecode native + checked LP", "native_root_covers": "Gecode native + checked LP", "native_frontier_bounds": "Gecode native frontier", "native_binary_branching": "Gecode native frontier", "convex_quadratic": "HiGHS QP"}.get(name, "Gecode native" if native_bridge else "HiGHS")
    if payload["backend"] != expected_backend:
        raise Failure("wrong backend provenance for required case")
    if payload.get("guarantee") != ("exact" if native_bridge else "numerical"):
        raise Failure("wrong guarantee for required case")
    elapsed = payload.get("elapsed_seconds")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise Failure("invalid panel elapsed time")
    values = payload.get("objectives")
    if not isinstance(values, list) or len(values) != len(expected):
        raise Failure("missing objective observations")
    for value, oracle in zip(values, expected):
        if (type(value) not in (int, float) or not math.isfinite(value)
                or (value != oracle if native_bridge else abs(value-oracle) > 1e-6)):
            raise Failure("independent objective oracle mismatch")
    return payload


def source_fingerprint(root, budget):
    files = [Path("test/optimize/fast_benchmark.cpp"), Path("test/test.cpp"), Path("test/int.cpp"),
             Path("test/int.hh"), Path("test/int/distinct.cpp"), Path("test/int/element.cpp"),
             Path("test/int/cumulative.cpp"), Path("test/search.cpp"),
             Path("gecode/kernel/core.cpp"), Path("gecode/kernel/core.hpp"),
             Path("experiments/optimize/fast_regression.py"),
             Path("experiments/optimize/process_containment.py")]
    files += [p.relative_to(root) for p in (root/"gecode/optimize").glob("*") if p.suffix in (".h", ".hpp", ".cpp")]
    files += [Path("gecode/minimodel")/name for name in
              ("lp-model.hpp", "lp-backend.hpp", "lp-relaxation.hpp", "lp-certificate.hpp")]
    files += [p.relative_to(root) for p in (root/"experiments/optimize/fast-fixtures").glob("*") if p.is_file()]
    hashes = {str(p): sha256(root/p, budget) for p in sorted(set(files))}
    aggregate = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"sha256": aggregate, "files": hashes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-binary", required=True, type=Path)
    parser.add_argument("--optimize-binary", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--library", action="append", type=Path, default=[], help="also hash each dynamically linked solver library")
    parser.add_argument("--budget-seconds", type=float, default=28.0)
    parser.add_argument("--case-seconds", type=float, default=4.0)
    parser.add_argument("--output", type=Path, help="optional NEW report path; never overwrite")
    args = parser.parse_args(argv)
    if not (math.isfinite(args.budget_seconds) and 1 <= args.budget_seconds <= 28):
        parser.error("--budget-seconds must be finite and between 1 and 28")
    if not (math.isfinite(args.case_seconds) and 0 < args.case_seconds <= args.budget_seconds):
        parser.error("--case-seconds must be positive, finite and within the outer budget")
    budget = Budget(args.budget_seconds, ENTRY, watchdog=True)
    report = {"schema": 1, "passed": False, "budget_seconds": args.budget_seconds, "timing_comparable": False,
              "timing_note": "Correctness gate; compare timings only on an uncontended host with matching build configuration.",
              "platform": platform.platform(), "python": platform.python_version(), "seed": 1701,
              "native_bridge_seed": 0, "threads": 1,
              "required_cases": REQUIRED, "cases": []}
    unsupported = platform_support_error(os.name)
    if unsupported:
        report["error"] = unsupported
        report["cases"] = [{"case": name, "correctness": "not_run",
                            "error": unsupported} for name in REQUIRED]
        report["elapsed_seconds"] = time.monotonic()-ENTRY
        print(json.dumps(report, allow_nan=False))
        return 1
    try:
        root = args.source_root.resolve(strict=True)
        binaries = {"native": args.native_binary.resolve(strict=True), "optimize": args.optimize_binary.resolve(strict=True)}
        if args.output and args.output.exists():
            raise Failure("report destination already exists")
        report["source"] = source_fingerprint(root, budget)
        report["binaries"] = {name: {"path": str(path), "sha256": sha256(path, budget)} for name, path in binaries.items()}
        report["libraries"] = [{"path": str(path.resolve()), "sha256": sha256(path, budget)} for path in args.library]
        with tempfile.TemporaryDirectory(prefix="gecode-fast-") as temporary:
            for name in REQUIRED:
                if not budget.remaining():
                    report["cases"].append({"case": name, "correctness": "not_run", "error": "whole-run wall budget exhausted"})
                    continue
                native = dict(NATIVE_CASES).get(name)
                seconds = min(args.case_seconds, budget.remaining())
                directory = Path(temporary)/name
                directory.mkdir()
                if native:
                    command = [str(binaries["native"]), "-threads", "1", "-seed", "1701", "-iter", "1", "-test", "^"+native]
                else:
                    command = [str(binaries["optimize"]), "--case", name, "--work-dir", str(directory),
                               "--fixtures", str(root/"experiments/optimize/fast-fixtures"), "--seconds", str(seconds)]
                result = run_command(command, budget, seconds, directory)
                result.update(case=name, correctness="fail")
                try:
                    result["observation"] = validate_output(name, result, native)
                    result["correctness"] = "pass"
                except Failure as error:
                    result["error"] = str(error)
                report["cases"].append(result)
        report["passed"] = len(report["cases"]) == len(REQUIRED) and all(c["correctness"] == "pass" for c in report["cases"])
    except (Failure, OSError) as error:
        report["error"] = str(error)
    present = {case["case"] for case in report["cases"]}
    report["cases"] += [{"case": name, "correctness": "not_run", "error": report.get("error", "required case absent")} for name in REQUIRED if name not in present]
    report["elapsed_seconds"] = time.monotonic()-ENTRY
    if report["elapsed_seconds"] >= args.budget_seconds:
        report.update(passed=False, error="whole-run wall budget exceeded")
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n"
    if args.output and not args.output.exists():
        try:
            with args.output.open("x") as output:
                output.write(text)
        except OSError as error:
            report.update(passed=False, error="cannot create report: "+str(error))
            text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n"
    sys.stdout.write(text)
    sys.stdout.flush()
    return 0 if report["passed"] and time.monotonic() < budget.deadline else 1


if __name__ == "__main__":
    sys.exit(main())
