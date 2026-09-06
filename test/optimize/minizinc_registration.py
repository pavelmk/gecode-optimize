#!/usr/bin/env python3
"""Pinned MiniZinc-to-driver compatibility gate; no download, build, or benchmarks.

Requires an actual MiniZinc 2.10.1 compiler with its matching standard library and
an actual native-enabled driver. Each required child and the suite have deadlines.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "org.gecode.optimize.experimental"
# Exact complete-predicate admission, deliberately independent of registry aliases.
PRIMITIVES = set("int_eq int_le int_lt int_ge int_gt int_plus int_minus int_lin_eq int_lin_le bool_eq bool_le bool_not bool_and bool_or array_bool_and array_bool_or bool_clause bool_lin_eq bool_lin_le bool2int int_in int_le_reif int_le_imp int_eq_imp int_lin_le_reif int_lin_le_imp array_int_element array_var_int_element all_different_int gecode_table_int gecode_regular gecode_circuit gecode_cumulatives cumulatives".split())


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Suite:
    def __init__(self, args, directory):
        self.args, self.directory = args, directory
        self.deadline = time.monotonic() + args.timeout
        self.checks, self.sources = [], {}
        self.msc = args.registration or directory / "gecode-optimize.msc"
        if args.registration is None:
            config = json.loads((ROOT / "tools/flatzinc/gecode-optimize.msc.in").read_text())
            config["version"] = "6.4.0-experimental-test"
            config["mznlib"] = str((ROOT / "tools/flatzinc/mznlib-optimize").resolve())
            config["executable"] = [str(args.binary), "--minizinc"]
            self.msc.write_text(json.dumps(config, indent=2) + "\n")
        # Read the actual artifact in place, preserving all relative paths.
        self.configuration_bytes = self.msc.read_bytes()
        config = json.loads(self.configuration_bytes)
        require(config.get("id") == IDENTITY, "Wrong experimental solver identity")
        executable = config.get("executable")
        require(isinstance(executable,list) and len(executable) == 2 and
                isinstance(executable[0],str) and executable[1] == "--minizinc",
                "Registration must invoke exactly the driver and --minizinc")
        def relative_path(value):
            require(isinstance(value,str) and value, "Registration path must be a nonempty string")
            path = Path(value)
            return (path if path.is_absolute() else self.msc.parent/path).resolve()
        executable_path = relative_path(executable[0])
        require(executable_path.is_file() and executable_path.samefile(args.binary),
                "Registration executable does not resolve to --binary")
        require(isinstance(config.get("mznlib"),str) and not config["mznlib"].startswith("-G"),
                "Registration must name its dedicated library directory, not a -G alias")
        self.library = relative_path(config["mznlib"])
        require(self.library.is_dir(), "Registration library directory does not exist")
        self.library_hashes = self.hash_library()
        require(self.library_hashes, "Registration library contains no .mzn files")
        # Only this process's environment changes; no system/user solver prefs.
        self.old_solver_path = os.environ.get("MZN_SOLVER_PATH")
        os.environ["MZN_SOLVER_PATH"] = str(self.msc.parent)

    def hash_library(self):
        return {str(path.relative_to(self.library)).replace(os.sep,"/"):digest(path)
                for path in sorted(self.library.rglob("*.mzn"))}

    def close(self):
        if self.old_solver_path is None:
            os.environ.pop("MZN_SOLVER_PATH", None)
        else:
            os.environ["MZN_SOLVER_PATH"] = self.old_solver_path

    def run(self, label, command, *, cwd=None):
        remaining = self.deadline - time.monotonic()
        require(remaining > 1, f"Aggregate deadline before {label}")
        start = time.monotonic()
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            process = None
            try:
                if os.name == "nt":
                    sys.path.insert(0, str(ROOT / "experiments/optimize"))
                    from process_containment import WindowsJobProcess
                    process = WindowsJobProcess()
                    process.start([str(x) for x in command], out, err, str(cwd or self.directory))
                else:
                    process = subprocess.Popen([str(x) for x in command], cwd=cwd or self.directory,
                                               stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                               start_new_session=True)
                code = process.wait(timeout=min(10, remaining - 1))
            finally:
                if process is not None:
                    if os.name == "nt":
                        process.cleanup(timeout=1)
                    else:
                        # MiniZinc starts the driver; terminate the whole group,
                        # even if MiniZinc exited while leaving a child behind.
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=1)
            require(out.tell() <= 1048576 and err.tell() <= 1048576, f"Excessive output: {label}")
            out.seek(0); err.seek(0)
            stdout, stderr = out.read().decode(), err.read().decode()
        require(time.monotonic() < self.deadline, f"Aggregate deadline after {label}")
        self.checks.append({"case": label, "returncode": code, "elapsed_seconds": time.monotonic()-start})
        return code, stdout, stderr

    def mzn(self, label, *options):
        return self.run(label, [self.args.minizinc, "--solver", self.msc, *options])

    def fixture(self, name):
        path = ROOT / "test/optimize/minizinc-fixtures" / ("mzn-"+name+".mzn")
        require(path.is_file(), f"Missing fixture: {path}")
        self.sources[path.name] = digest(path)
        return path

    def positive(self, name, allowed, *, mode="optimal", required=None):
        source = self.fixture(name)
        fzn = self.directory / (name+".fzn")
        code, stdout, stderr = self.mzn("compile-"+name, "--compile", "--output-fzn-to-file", fzn,
                                      "--output-ozn-to-file", self.directory/(name+".ozn"), source)
        require(code == 0 and not stderr, f"Compile {name}: {code} {stdout!r} {stderr!r}")
        text = fzn.read_text()
        emitted = set(re.findall(r"\bconstraint\s+(\w+)\s*\(", text))
        require(emitted <= PRIMITIVES, f"Unadmitted predicate lowering in {name}: {emitted-PRIMITIVES}")
        if required:
            require(required in emitted, f"Missing native lowering {required} in {name}")
        code, stdout, stderr = self.mzn("solve-"+name, source)
        require(code == 0 and not stderr, f"Solve {name}: {code} {stdout!r} {stderr!r}")
        lines = [line for line in stdout.splitlines() if line and not line.startswith("%")]
        if mode == "unsat":
            require(lines == ["=====UNSATISFIABLE====="], f"False completion in {name}: {lines}")
        else:
            markers = ["----------", "=========="] if mode == "optimal" else ["----------"]
            require(lines[1:] == markers, f"Wrong markers in {name}: {lines}")
            require(tuple(json.loads(lines[0])) in allowed, f"Original-model oracle failed in {name}: {lines[0]}")
            require("% guarantee: exact integer search" in stdout, f"Wrong backend provenance: {name}")

    def rejected(self, name, contains):
        code, stdout, stderr = self.mzn("reject-"+name, self.fixture(name))
        require(code != 0 and contains in stderr, f"Missing rejection {name}: {code} {stdout!r} {stderr!r}")
        require("----------" not in stdout and "=====UNSATISFIABLE=====" not in stdout,
                f"Rejected model published a witness/proof: {name}")


def regular(word, states, alphabet, transitions, initial, finals):
    for symbol in word:
        if not 1 <= symbol <= alphabet or not 1 <= initial <= states:
            return False
        initial = transitions[(initial-1)*alphabet+symbol-1]
        if initial == 0:
            return False
    return initial in finals


def circuit(values, offset):
    visited, node = set(), offset
    for _ in values:
        if node in visited or not offset <= node < offset+len(values):
            return False
        visited.add(node)
        node = values[node-offset]
    return node == offset and len(visited) == len(values)


def cumulative(starts, durations, heights, capacity):
    # Independent half-open integer-time oracle for these tiny source models.
    return all(sum(h for s,d,h in zip(starts,durations,heights) if s <= t < s+d) <= capacity
               for t in range(-2, 6))


def tests(s):
    code, stdout, stderr = s.run("compiler-version", [s.args.minizinc, "--version"])
    require(code == 0 and "version 2.10.1," in stdout and not stderr, "Required pinned MiniZinc 2.10.1 unavailable")
    code, stdout, stderr = s.run("solver-discovery", [s.args.minizinc, "--solvers-json"])
    require(code == 0 and not stderr, "Solver discovery failed")
    configs = [x for x in json.loads(stdout) if x["id"] == IDENTITY]
    require(len(configs) == 1, "Experimental solver identity absent or duplicated")
    require(configs[0]["stdFlags"] == ["-t"] and configs[0]["tags"] == ["cp","int","experimental"],
            "Registration overstates supported flags/types")
    require("default" not in configs[0]["tags"], "Experimental registration changed the default")
    a = [(x,y,2*x+y-4) for x,y in itertools.product(range(4),repeat=2) if x+y >= 3]
    s.positive("linear-min", {min(a,key=lambda p:p[2])})
    a = [(x,y,3*x-y+2) for x,y in itertools.product(range(-2,3),repeat=2) if x+y <= 1]
    s.positive("linear-max", {max(a,key=lambda p:p[2])})
    s.positive("satisfy", {(1,),(2,)}, mode="satisfy")
    s.positive("unsat", set(), mode="unsat", required="all_different_int")
    s.positive("alias-holes", {(3,3)})
    s.positive("all-different", {(1,2)}, required="all_different_int")
    s.positive("table", {(1,2)}, required="gecode_table_int")
    s.positive("table-alias", {(1,1)}, required="gecode_table_int")
    words = [x for x in itertools.product((1,2),repeat=2) if regular(x,3,2,[2,3,0,3,2,0],1,{3})]
    s.positive("regular", {min(words,key=lambda x:x[0])}, required="gecode_regular")
    words = [(x,x,x) for x in (1,2) if regular((x,x,x),2,2,[2,1,1,2],1,{1})]
    s.positive("regular-alias", set(words), required="gecode_regular")
    s.positive("regular-empty", {()}, mode="satisfy")
    s.positive("regular-dead", set(), mode="unsat", required="gecode_regular")
    for name,offset in (("negative",-2),("offset",2)):
        values = [x for x in itertools.product(range(offset,offset+3),repeat=3) if circuit(x,offset)]
        s.positive("circuit-"+name, {min(values,key=lambda x:x[0])}, required="gecode_circuit")
    s.positive("element-offset", {(0,2)}, required="array_int_element")
    starts = [(x,1) for x in range(3) if cumulative([x,1,1],[1,1,1],[1,1,1],2)]
    s.positive("cumulative-half-open", {min(starts)}, required="gecode_cumulatives")
    s.positive("cumulative-zero", {(0,)}, required="gecode_cumulatives")
    s.positive("cumulative-unsat", set(), mode="unsat", required="gecode_cumulatives")
    s.positive("cumulative-fixed-alias", {(0,1,1)}, required="gecode_cumulatives")
    s.positive("reified-le", {(1,1)})
    accepted = {x for x in itertools.product((1,2),repeat=2) if regular(x,1,2,[1,0],1,{1})}
    s.positive("regular-decomposed-reif", accepted, required="gecode_regular")
    rejected = [x for x in itertools.product((1,2),repeat=2) if not regular(x,1,2,[1,0],1,{1})]
    s.positive("regular-complement", {min(rejected,key=lambda x:2*x[0]+x[1])}, required="gecode_regular")
    for name,text in (("times","multiplication is unsupported"),("reif-eq","equality is unsupported"),
                      ("float","float and set variables"),("set","float and set variables"),("search","search annotations"),
                      ("variable-cumulative","original singleton")):
        s.rejected("reject-"+name,text)
    # Test flags through the actual MiniZinc parser, not only the .msc JSON.
    for flag in ("--all-solutions","--intermediate-solutions"):
        args = [flag]
        code, stdout, stderr = s.mzn("unadvertised-"+flag, *args, s.fixture("satisfy"))
        require(code != 0 and "Unrecognized option" in stderr, f"Unsupported standard flag accepted: {flag}")
    # MiniZinc owns compiler/output statistics and may consume --parallel even
    # when neither solver flag is advertised. Force forwarding to test the
    # driver's strict boundary without misrepresenting the outer compiler.
    for flag in ("-s", "-p"):
        code, stdout, stderr = s.mzn("forwarded-"+flag,"--fzn-flag",flag,s.fixture("satisfy"))
        require(code != 0 and "Unsupported MiniZinc protocol option" in stderr,
                f"Unsupported forwarded solver flag accepted: {flag}")
    for milliseconds in ("0","1000"):
        code, stdout, stderr = s.mzn("time-"+milliseconds,"--solver-time-limit",milliseconds,s.fixture("satisfy"))
        require(code == 0 and "----------" in stdout and not stderr, "MiniZinc time convention mismatch")
    # Filename ordering and zero semantics are isolated from direct CLI behavior.
    fzn = s.directory/"protocol.fzn"
    fzn.write_text("var 0..2: x :: output_var; solve minimize x;\n")
    for args in (("-t","0",str(fzn)),(str(fzn),"-t","0"),("--",str(fzn))):
        code, stdout, stderr = s.run("protocol-order",[s.args.binary,"--minizinc",*args])
        require(code == 0 and "x = 0;" in stdout and "==========" in stdout and not stderr, "Protocol option order/zero failed")
    for args in (("-t",),("-t","-1",str(fzn)),("-t","1.5",str(fzn)),("-t","18446744073709551616",str(fzn)),
                 ("-t","0","-t","1",str(fzn)),(str(fzn),str(fzn)),("--backend","highs",str(fzn)),("-a",str(fzn))):
        code, stdout, stderr = s.run("protocol-rejection",[s.args.binary,"--minizinc",*args])
        require(code == 2 and not stdout and stderr, f"Malformed protocol accepted: {args}")
    code, stdout, stderr = s.run("direct-zero",[s.args.binary,fzn,"--time-limit","0"])
    require(code == 1 and "=====UNKNOWN=====" in stdout, "Direct zero deadline changed")
    # A finite parser workload (no CP benchmark) makes a 1ms budget expire in
    # capture on supported CI machines, verifying UNKNOWN is normal exit0.
    large = s.directory/"capture-deadline.fzn"
    large.write_text("".join(f"var 0..1: x{i};\n" for i in range(20000))+"solve satisfy;\n")
    for prefix in ([s.args.binary,"--minizinc","-t","1"],
                   [s.args.minizinc,"--solver",s.msc,"--solver-time-limit","1"]):
        code, stdout, stderr = s.run("actual-timeout",[*prefix,large])
        require(code == 0 and "=====UNKNOWN=====" in stdout and "=====ERROR=====" not in stdout,
                f"Timeout became solver error: {code} {stdout!r} {stderr!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minizinc", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--registration", type=Path, help="Test this configured .msc in place without rewriting it")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    require(math.isfinite(args.timeout) and args.timeout > 0, "Finite positive suite timeout required")
    args.minizinc, args.binary = args.minizinc.resolve(), args.binary.resolve()
    args.registration = args.registration.resolve() if args.registration is not None else None
    require(args.minizinc.is_file() and args.binary.is_file(), "Required executable is missing")
    with tempfile.TemporaryDirectory(prefix="gecode-minizinc-") as tmp:
        suite = Suite(args,Path(tmp))
        try:
            tests(suite)
            require(suite.msc.read_bytes() == suite.configuration_bytes, "Registration artifact changed during the test")
            require(suite.hash_library() == suite.library_hashes, "Registration library changed during the test")
            report = {"status":"passed","compiler_version":"2.10.1","compiler_sha256":digest(args.minizinc),
                      "driver_sha256":digest(args.binary),"cases":len(suite.checks),"checks":suite.checks,
                      "configuration_sha256":hashlib.sha256(suite.configuration_bytes).hexdigest(),
                      "configuration_provided":args.registration is not None,
                      "library_files_sha256":suite.library_hashes,
                      "library_sha256":hashlib.sha256(json.dumps(suite.library_hashes,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                      "source_sha256":suite.sources}
            print(json.dumps(report,sort_keys=True))
        finally:
            suite.close()


if __name__ == "__main__":
    main()
