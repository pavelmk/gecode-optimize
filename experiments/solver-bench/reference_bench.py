#!/usr/bin/env python3
"""Build/run a separate HiGHS native-MIP reference competitor.

This is not the enhanced Gecode proof engine. MIP optimality is numerical;
returned original-model binary witnesses are checked with exact integers.
Build and run are explicit subcommands. No dependency is downloaded or built
implicitly. Run only when no other benchmark, build or correctness test runs.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time
import bench
import build as common
import validate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEFAULT_BINARY=ROOT/"build/solver-bench/bin/highs-mip-reference"


def utc():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def text(value):return value.decode(errors="replace") if isinstance(value,bytes) else value or ""


def build(args):
    args.highs_source=args.highs_source.resolve();args.highs_build=args.highs_build.resolve();args.out=args.out.resolve()
    if not args.highs_source.is_dir():raise ValueError("Build the main suite's pinned HiGHS dependency first; this command does not download it")
    compiler=shutil.which("clang++") or shutil.which("c++")
    if not compiler:raise ValueError("C++17 compiler missing")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    metadata={"status":"building","track":"highs_mip_reference","highs_commit":common.HIGHS_COMMIT,
              "started_utc":utc(),"commands":[],"gecode_linked":False,"highs_mip_used":True}
    run=common.Runner(metadata)
    try:
        metadata["compiler"]=run([compiler,"--version"],True).decode()
        metadata["dependency_source_verification"]=common.prepare_highs(args.highs_source,args.highs_build,run)
        options={"CMAKE_BUILD_TYPE":"Release","BUILD_SHARED_LIBS":"OFF","BUILD_SHARED_EXTRAS_LIB":"OFF",
                 "BUILD_CXX":"ON","BUILD_CXX_EXE":"OFF","BUILD_TESTING":"OFF","BUILD_EXAMPLES":"OFF","HIPO":"OFF","ZLIB":"OFF"}
        flags=[compiler,"-std=c++17","-O3","-DNDEBUG"]
        if platform.system()=="Darwin":
            options["CMAKE_OSX_DEPLOYMENT_TARGET"]="15.7";flags.append("-mmacosx-version-min=15.7")
        metadata["library_cache"]=common.verify_cache(args.highs_build,args.highs_source,options)
        libraries=[args.highs_build/"lib/libhighs.a",args.highs_build/"lib/libhighs_extras.a"]
        metadata["library_hashes"]={str(p):sha(p) for p in libraries}
        source=HERE/"highs-mip-driver.cpp";snapshot=args.out.with_suffix(".source.cpp")
        shutil.copy2(source,snapshot);metadata["source_sha256"]=sha(snapshot);metadata["source_snapshot"]=str(snapshot)
        run([*flags,"-I"+str(args.highs_build),"-I"+str(args.highs_source/"highs"),snapshot,*libraries,"-pthread","-o",args.out])
        if sha(source)!=metadata["source_sha256"]:raise ValueError("Reference source changed during compilation")
        metadata.update(status="built",binary_sha256=sha(args.out),binary=str(args.out),compiler_flags=flags)
    except Exception as error:
        metadata.update(status="failed",error=f"{type(error).__name__}: {error}");raise
    finally:
        metadata["finished_utc"]=utc();args.out.with_suffix(".build.json").write_text(json.dumps(metadata,indent=2)+"\n")


def check_result(instance,result,limit,warm):
    if result.get("status") not in ("optimal","feasible","unknown","infeasible"):
        return {"valid":False,"error":"reference solver error"}
    if not result.get("highs_mip_used") or result.get("gecode_used") or result.get("exact_dual_certificate"):
        return {"valid":False,"error":"incorrect reference provenance"}
    checked=validate.validate_result(instance,result)
    if not checked["valid"]:return checked
    within=result.get("assignment_at_limit",[]);within_cost=result.get("objective_at_limit")
    if within:
        at_limit=validate.validate_assignment(instance,within)
        if not at_limit["valid"] or at_limit["objective"]!=within_cost:
            return {"valid":False,"error":"invalid within-budget witness"}
    elif within_cost is not None:return {"valid":False,"error":"within-budget objective has no witness"}
    elapsed=result.get("elapsed_ms")
    if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<0:
        return {"valid":False,"error":"invalid elapsed time"}
    initial=instance.get("incumbent_objective") if warm and instance.get("incumbent") else None
    previous=initial;at_limit_cost=initial;last_time=0
    for stamp,cost in result.get("improvements",[]):
        if not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or stamp<last_time or stamp>elapsed+1e-6:
            return {"valid":False,"error":"invalid trajectory time"}
        if not validate.integer(cost) or (previous is not None and cost>=previous):
            return {"valid":False,"error":"nonimproving trajectory"}
        previous=cost;last_time=stamp
        if stamp<=limit:at_limit_cost=cost
    if at_limit_cost!=within_cost:return {"valid":False,"error":"within-budget witness disagrees with trajectory"}
    checked["numerical_mip_optimality_only"]=result["status"]=="optimal"
    checked["exact_dual_certificate"]=False
    return checked


def run_reference(args):
    if args.repeats<1 or not math.isfinite(args.limit_ms) or not 0<args.limit_ms<=86400000:raise ValueError("Invalid cutoff/repeats")
    if not math.isfinite(args.wall_budget) or args.wall_budget<0:raise ValueError("Invalid session wall budget")
    args.bin=args.bin.resolve();build_path=args.bin.with_suffix(".build.json")
    built=json.loads(build_path.read_text())
    if built.get("status")!="built" or built["binary_sha256"]!=sha(args.bin):raise ValueError("Reference build metadata/binary mismatch")
    paths=args.manifest or [HERE/"public-binary-manifest.json",HERE/"miplib-manifest.json"]
    records=[];instances={};input_hashes={}
    for path in paths:
        directory=path.resolve().parent;manifest=json.loads(path.read_text())
        if manifest.get("ready") is False or manifest.get("generation_status")=="in_progress":raise ValueError("Incomplete manifest")
        for item in manifest["instances"]:
            if item.get("kind","binary")!="binary" or item.get("split") not in args.split.split(","):continue
            if args.ids and item["id"] not in args.ids.split(","):continue
            if item["id"] in instances:raise ValueError("Duplicate instance ID")
            instance=json.loads((directory/item["json"]).read_text());validate.check_instance(instance)
            bench.binary_txt_matches(instance,directory/item["txt"])
            if instance.get("incumbent"):
                checked=validate.validate_assignment(instance,instance["incumbent"])
                if not checked["valid"] or checked["objective"]!=instance.get("incumbent_objective"):raise ValueError("Invalid common start")
            record=dict(item,_directory=directory);records.append(record);instances[item["id"]]=instance
            input_hashes[item["id"]]={kind:sha(directory/item[kind]) for kind in ("json","txt")}
    if not records:raise ValueError("No matching binary instances")
    protocol={"schema_version":1,"track":"highs_mip_reference","runner_sha256":sha(Path(__file__)),
              "validator_sha256":sha(HERE/"validate.py"),"schema_helper_sha256":sha(HERE/"bench.py"),
              "binary_sha256":sha(args.bin),"build_metadata_sha256":sha(build_path),"source_sha256":built["source_sha256"],
              "highs_commit":built["highs_commit"],"manifests":{str(p.resolve()):sha(p) for p in paths},"inputs":input_hashes,
              "split":args.split,"warm":args.warm,"repeats":args.repeats,"limit_ms":args.limit_ms,"order_seed":771052,
              "threads":1,"requested_mip_rel_gap":0,"requested_mip_abs_gap":0,"candidate_tolerance":1e-7,
              "highs_mip_used":True,"gecode_used":False,"exact_dual_certificate":False,
              "platform":platform.platform(),"machine":platform.machine(),
              "validation":"Exact integer original-row/objective checks for final and within-budget witnesses; optimality/infeasibility is HiGHS numerical MIP status, not a certified exact dual proof.",
              "timing":"Input parse and common-start validation excluded, matching Gecode. Model construction, start injection, callbacks, exact witness checking, search and teardown included; full process wall time also retained."}
    args.output.parent.mkdir(parents=True,exist_ok=True);meta_path=args.output.with_suffix(".meta.json");summary_path=args.output.with_suffix(".summary.json")
    rows=[];done=set()
    if args.output.exists():
        if not args.resume:raise ValueError("Output exists; use --resume or a new path")
        old=json.loads(meta_path.read_text())
        if old["protocol"]!=protocol:raise ValueError("Resume protocol mismatch")
        for line in args.output.read_text().splitlines():
            row=json.loads(line);key=(row["id"],row["repetition"])
            if key in done:raise ValueError("Duplicate stored run")
            done.add(key);rows.append(row)
    metadata={"protocol":protocol,"started_utc":utc(),"completed":False,"expected_runs":len(records)*args.repeats,"previous_runs":len(done)}
    meta_path.write_text(json.dumps(metadata,indent=2)+"\n");randomizer=random.Random(protocol["order_seed"]);start_all=time.perf_counter();last_progress=start_all
    try:
        with args.output.open("a") as stream:
            for rep in range(args.repeats):
                order=list(records);randomizer.shuffle(order)
                for record in order:
                    key=(record["id"],rep)
                    if key in done:continue
                    if args.wall_budget and time.perf_counter()-start_all>=args.wall_budget:
                        metadata["stop_reason"]="session wall budget";return
                    instance=instances[record["id"]];command=[str(args.bin),str(record["_directory"]/record["txt"]),str(args.limit_ms),str(args.warm),"1"]
                    started=time.perf_counter();hard_timeout=False
                    try:
                        process=subprocess.run(command,capture_output=True,text=True,timeout=args.limit_ms/1000+5)
                        stdout,stderr,code=process.stdout,process.stderr,process.returncode
                    except subprocess.TimeoutExpired as error:
                        stdout,stderr,code=text(error.stdout),text(error.stderr),None;hard_timeout=True
                    except OSError as error:stdout,stderr,code="",str(error),-1
                    wall_ms=(time.perf_counter()-started)*1000
                    try:
                        if code!=0:raise ValueError("external timeout" if hard_timeout else "nonzero process exit")
                        row=json.loads(stdout);checked=check_result(instance,row,args.limit_ms,args.warm)
                    except (ValueError,KeyError,TypeError) as error:
                        row={"status":"timeout" if hard_timeout else "error"};checked={"valid":False,"error":str(error)}
                    row.update(id=record["id"],family=record["family"],split=record["split"],kind="binary",track="highs_mip_reference",
                               repetition=rep,warm=bool(args.warm),limit_ms=args.limit_ms,process_wall_ms=wall_ms,
                               stdout=stdout,stderr=stderr,returncode=code,external_timeout=hard_timeout,argv=command,
                               binary_sha256=protocol["binary_sha256"],validation=checked,
                               stdout_sha256=hashlib.sha256(stdout.encode()).hexdigest(),stderr_sha256=hashlib.sha256(stderr.encode()).hexdigest(),
                               initial_objective=instance.get("incumbent_objective") if args.warm else None,
                               numerical_completion_within_budget=checked["valid"] and row["status"] in ("optimal","infeasible") and row.get("elapsed_ms",math.inf)<=args.limit_ms)
                    stream.write(json.dumps(row,separators=(",",":"))+"\n");stream.flush();rows.append(row);done.add(key)
                    if time.perf_counter()-last_progress>=20:
                        print(f"HiGHS MIP reference: {len(done)}/{metadata['expected_runs']} runs",flush=True);last_progress=time.perf_counter()
        metadata["completed"]=True
    finally:
        metadata.update(finished_utc=utc(),completed_runs=len(done));meta_path.write_text(json.dumps(metadata,indent=2)+"\n")
        summary={"protocol":protocol,"runs":len(rows),"outcomes":dict(Counter(r["status"] for r in rows)),
                 "valid_runs":sum(r["validation"]["valid"] for r in rows),
                 "numerical_completions_within_budget":sum(r["numerical_completion_within_budget"] for r in rows)}
        summary_path.write_text(json.dumps(summary,indent=2)+"\n");print(json.dumps({k:v for k,v in summary.items() if k!="protocol"}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest="command",required=True)
    builder=commands.add_parser("build",help="Link the standalone reference with an existing pinned HiGHS build")
    builder.add_argument("--highs-source",type=Path,default=ROOT/"build/solver-bench/deps/HiGHS")
    builder.add_argument("--highs-build",type=Path,default=ROOT/"build/solver-bench/deps/HiGHS-build")
    builder.add_argument("--out",type=Path,default=DEFAULT_BINARY)
    runner=commands.add_parser("run",help="Run a separate serial numerical-MIP reference cohort")
    runner.add_argument("--bin",type=Path,default=DEFAULT_BINARY)
    runner.add_argument("--manifest",type=Path,action="append")
    runner.add_argument("--split",default="public");runner.add_argument("--ids",default="")
    runner.add_argument("--limit-ms",type=float,default=1000);runner.add_argument("--repeats",type=int,default=3)
    runner.add_argument("--warm",type=int,choices=(0,1),default=1);runner.add_argument("--output",type=Path,required=True)
    runner.add_argument("--resume",action="store_true");runner.add_argument("--wall-budget",type=float,default=0)
    args=parser.parse_args()
    if sys.version_info<(3,12):parser.error("Python 3.12+ required")
    build(args) if args.command=="build" else run_reference(args)


if __name__=="__main__":main()
