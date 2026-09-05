#!/usr/bin/env python3
"""Plan or run focused correctness checks, never a performance benchmark.

Default: print the exact test commands without running them. Pass --execute
only outside a benchmark timing window. No builds, downloads, performance
batches or policy training are launched. Native checks create six tiny local
test inputs. Tests run serially and all outcomes are saved.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
SUITE=HERE.parent
ROOT=SUITE.parents[1]
CPP=("certificate","backend","propagator","reduced-cost","strengthening","primal")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin",type=Path,default=ROOT/"build/solver-bench/bin")
    parser.add_argument("--legacy-bin",type=Path,help="Optional prior native binaries for exact default-mode controls")
    parser.add_argument("--groups",default="cpp,python,controller",help="Comma-separated cpp,python,controller")
    parser.add_argument("--output",type=Path,default=SUITE/"results/correctness-checks.json")
    parser.add_argument("--execute",action="store_true",help="Run the printed checks; ensure no benchmark is active")
    parser.add_argument("--timeout-seconds",type=int,default=120,help="Maximum time for each test subprocess")
    args=parser.parse_args();groups=args.groups.split(",")
    if any(g not in ("cpp","python","controller") for g in groups) or len(groups)!=len(set(groups)):
        parser.error("Unknown/duplicate groups")
    if args.timeout_seconds<1:parser.error("Positive timeout required")
    if not __debug__:parser.error("Correctness tests require assertions; remove -O/PYTHONOPTIMIZE")
    args.bin=args.bin.resolve();args.output=args.output.resolve()
    if args.legacy_bin is not None:args.legacy_bin=args.legacy_bin.resolve()
    checks=[]
    if "cpp" in groups:
        checks.extend(("cpp-"+name,[str(args.bin/("test-"+name))],ROOT) for name in CPP)
    if "python" in groups:
        checks.extend(("python-"+name,[sys.executable,str(HERE/(name+".py"))],ROOT)
                      for name in ("public_import","rcpsp","public_catalog","miplib_import"))
        checks.append(("python-schema-policy",[sys.executable,"-m","unittest","-q","test_analyze","test_train_policy"],SUITE))
    if "controller" in groups:
        details=args.output.with_name(args.output.stem+"-native-controller.json")
        command=[sys.executable,str(HERE/"native_controller.py"),"--bin",str(args.bin),"--output",str(details)]
        if args.legacy_bin is not None:command += ["--legacy-bin",str(args.legacy_bin)]
        checks.append(("native-controller",command,ROOT))
    for name,command,cwd in checks:
        print(f"{name}: (cwd {cwd}) {shlex.join(command)}",flush=True)
    if not args.execute:
        print("Plan only. Pass --execute outside benchmark timing windows to run correctness checks.")
        return 0
    metadata={"started_utc":datetime.now(timezone.utc).isoformat(),"kind":"correctness-only",
              "benchmark_launched":False,"groups":groups,"python":sys.version,
              "runner_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"tests":[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        for name,command,cwd in checks:
            start=time.perf_counter();timeout=False
            try:
                result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=args.timeout_seconds)
                code,stdout,stderr=result.returncode,result.stdout,result.stderr
            except subprocess.TimeoutExpired as error:
                code=None;timeout=True
                stdout=error.stdout.decode(errors="replace") if isinstance(error.stdout,bytes) else error.stdout or ""
                stderr=error.stderr.decode(errors="replace") if isinstance(error.stderr,bytes) else error.stderr or ""
            except OSError as error:
                code=-1;stdout="";stderr=str(error)
            row={"name":name,"argv":command,"cwd":str(cwd),"returncode":code,
                 "timeout":timeout,"passed":code==0,"stdout":stdout,"stderr":stderr,
                 "elapsed_seconds":time.perf_counter()-start}
            for path in [Path(command[0]),*[Path(x) for x in command[1:] if x.endswith(".py")]]:
                if path.is_file():row.setdefault("input_hashes",{})[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            metadata["tests"].append(row)
            print(f"{name}: {'PASS' if row['passed'] else 'FAIL'}",flush=True)
    finally:
        metadata.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                        passed=len(metadata["tests"])==len(checks) and all(x["passed"] for x in metadata["tests"]))
        args.output.write_text(json.dumps(metadata,indent=2)+"\n")
    return 0 if metadata["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
