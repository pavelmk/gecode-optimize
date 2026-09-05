#!/usr/bin/env python3
"""Serial paired native FlatZinc compatibility and optimization regression runs.

Models, annotations and all-solutions flags are preserved. Output is compared
exactly with upstream regression text after removing only the documented
statistics suffix. A text mismatch can be another valid solution; it is not
an independent mathematical refutation. This track does not use the LP module.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import statistics
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BINARIES={"stock":"stock-fzn","enhanced":"enhanced-fzn"}
STAT_BLOCK=re.compile(r"\n(?:%%%mzn-stat: [^\n]*\n)+%%%mzn-stat-end\n\n?")


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def as_text(value): return value.decode(errors="replace") if isinstance(value,bytes) else value or ""


def output_and_statistics(stdout):
    """Preserve every byte of model output outside the known suffix format."""
    matches=list(STAT_BLOCK.finditer(stdout))
    if len(matches)!=1 or matches[0].end()!=len(stdout):
        return stdout,{},False
    match=matches[0];values={}
    for key,value in re.findall(r"^%%%mzn-stat: ([A-Za-z_][A-Za-z_0-9]*)=([^\n]*)$",match.group(),re.M):
        try:
            number=int(value) if re.fullmatch(r"-?\d+",value) else float(value)
            values[key]=number if math.isfinite(number) else value
        except ValueError:
            values[key]=value
    return stdout[:match.start()],values,True


def objective_identifier(model):
    model=re.sub(r'"(?:[^"\\]|\\.)*"','""',model)
    model=re.sub(r"%[^\n]*","",model)
    solve=re.search(r"\bsolve\b([^;]*);",model,re.S)
    if not solve: return None
    match=re.search(r"\b(?:minimize|maximize)\s+([A-Za-z_][A-Za-z_0-9]*)\s*$",solve.group(1))
    return match.group(1) if match else None


def scalar_objective(output,identifier):
    if identifier is None: return None
    values=re.findall(r"^"+re.escape(identifier)+r"\s*=\s*(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*;\s*$",output,re.M)
    if not values: return None
    value=values[-1]
    number=int(value) if re.fullmatch(r"-?\d+",value) else float(value)
    return number if math.isfinite(number) else None


def classify(record,comparison,expected,returncode,hard_timeout):
    if hard_timeout: return "timeout","external process time limit"
    if returncode!=0: return "error","nonzero process exit"
    if comparison==expected: return "passed","exact upstream output match"
    complete="==========" in comparison or "=====UNSATISFIABLE=====" in comparison
    first_solution="----------" in comparison
    requires_exhaustion=record["solve"]!="satisfy" or record["all_solutions"]
    if "=====UNKNOWN=====" in comparison or (not complete and (requires_exhaustion or not first_solution)):
        return "timeout","no completion/first-solution marker under solver time limit"
    return "failed","upstream text differs; alternate valid solutions are possible"


def summarize(rows):
    groups=defaultdict(list)
    for row in rows: groups[(row["track"],row["config"])].append(row)
    summary=[]
    for (track,config),items in sorted(groups.items()):
        passed=[r for r in items if r["status"]=="passed"]
        summary.append({"track":track,"config":config,"runs":len(items),
                        "outcomes":dict(Counter(r["status"] for r in items)),
                        "median_passed_process_wall_ms":statistics.median(r["process_wall_ms"] for r in passed) if passed else None,
                        "independent_mathematical_validation":False})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin",type=Path,default=ROOT/"build/solver-bench/bin")
    parser.add_argument("--manifest",type=Path,default=HERE/"fzn-manifest.json")
    parser.add_argument("--configs",default="stock,enhanced")
    parser.add_argument("--ids",default="")
    parser.add_argument("--tracks",default="")
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--limit-ms",type=float,default=1000)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--wall-budget",type=float,default=0,help="Pause between runs after this many seconds")
    args=parser.parse_args();configs=args.configs.split(",")
    if any(c not in BINARIES for c in configs) or len(set(configs))!=len(configs): parser.error("Unknown/duplicate configurations")
    if args.repeats<1 or not math.isfinite(args.limit_ms) or args.limit_ms<=0: parser.error("Positive finite cutoff/repeats required")
    if not math.isfinite(args.wall_budget) or args.wall_budget<0: parser.error("Nonnegative finite wall budget required")
    manifest=json.loads(args.manifest.read_text());directory=args.manifest.resolve().parent
    records=manifest["instances"]
    if args.ids: records=[r for r in records if r["id"] in args.ids.split(",")]
    if args.tracks: records=[r for r in records if r["track"] in args.tracks.split(",")]
    if not records or len({r["id"] for r in records})!=len(records): parser.error("No matching fixtures or duplicate IDs")
    fixtures={};inputs={}
    for record in records:
        model=directory/record["fzn"];expected=directory/record["expected"]
        if sha(model)!=record["fzn_sha256"] or sha(expected)!=record["expected_sha256"]:
            raise ValueError(f"Fixture bytes disagree with manifest: {record['id']}")
        if record["solve"] not in ("satisfy","minimize","maximize") or type(record["all_solutions"]) is not bool:
            raise ValueError("Invalid solve/all-solutions metadata")
        fixtures[record["id"]]=(model,expected.read_text(),objective_identifier(model.read_text()))
        inputs[record["id"]]={"fzn":sha(model),"expected":sha(expected),
                              "source":record.get("source_sha256"),"all_solutions":record["all_solutions"],"solve":record["solve"]}
    protocol={"schema_version":1,"runner_sha256":sha(Path(__file__)),"manifest_sha256":sha(args.manifest),"inputs":inputs,
              "binaries":{c:{"name":BINARIES[c],"sha256":sha(args.bin/BINARIES[c])} for c in configs},
              "configs":configs,"repeats":args.repeats,"limit_ms":args.limit_ms,
              "order_seed":614921,"threads":1,"preserve_annotations":True,
              "lp_extension_used":False,"platform":platform.platform(),"machine":platform.machine(),
              "timing":"Process wall time includes startup, parsing, initialization, search, teardown and output; separate solver-reported initTime/solveTime are retained. One subprocess runs at a time.",
              "validation":"Exact upstream regression text after stripping only the statistics suffix; not an independent mathematical oracle. SAT and optimization tracks remain separate."}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    meta_path=args.output.with_suffix(".meta.json");summary_path=args.output.with_suffix(".summary.json")
    rows=[];done=set()
    if args.output.exists():
        if not args.resume: parser.error("Output exists; use --resume or a new output")
        old=json.loads(meta_path.read_text())
        if old["protocol"]!=protocol: raise ValueError("Resume protocol/input/binary mismatch")
        for line in args.output.read_text().splitlines():
            row=json.loads(line);key=(row["id"],row["config"],row["repetition"])
            if key in done: raise ValueError("Duplicate stored run")
            done.add(key);rows.append(row)
    metadata={"protocol":protocol,"started_utc":utc(),"completed":False,
              "expected_runs":len(records)*len(configs)*args.repeats,"previous_runs":len(done)}
    meta_path.write_text(json.dumps(metadata,indent=2)+"\n")
    randomizer=random.Random(protocol["order_seed"]);started=time.perf_counter();last_progress=started
    try:
        with args.output.open("a") as stream:
            for repetition in range(args.repeats):
                order=list(records);randomizer.shuffle(order)
                for record in order:
                    config_order=list(configs);randomizer.shuffle(config_order)
                    for config in config_order:
                        key=(record["id"],config,repetition)
                        if key in done: continue
                        if args.wall_budget and time.perf_counter()-started>=args.wall_budget:
                            metadata["stop_reason"]="session wall budget";return
                        model,expected,identifier=fixtures[record["id"]]
                        command=[str((args.bin/BINARIES[config]).resolve()),"-p","1","-time",str(args.limit_ms),"-s"]
                        if record["all_solutions"]: command.append("-a")
                        command.append(str(model));start=time.perf_counter();hard_timeout=False
                        try:
                            result=subprocess.run(command,capture_output=True,text=True,timeout=args.limit_ms/1000+5)
                            stdout,stderr,code=result.stdout,result.stderr,result.returncode
                        except subprocess.TimeoutExpired as error:
                            hard_timeout=True;stdout,stderr,code=as_text(error.stdout),as_text(error.stderr),None
                        except OSError as error:
                            stdout,stderr,code="",str(error),-1
                        wall_ms=(time.perf_counter()-start)*1000
                        comparison,stats,statistics_parsed=output_and_statistics(stdout)
                        status,reason=classify(record,comparison,expected,code,hard_timeout)
                        row={"id":record["id"],"family":record["family"],"track":record["track"],
                             "kind":"flatzinc","solve":record["solve"],"all_solutions":record["all_solutions"],
                             "config":config,"repetition":repetition,"status":status,"reason":reason,
                             "process_wall_ms":wall_ms,"limit_ms":args.limit_ms,"returncode":code,
                             "external_timeout":hard_timeout,"stdout":stdout,"stderr":stderr,
                             "stdout_sha256":hashlib.sha256(stdout.encode()).hexdigest(),
                             "stderr_sha256":hashlib.sha256(stderr.encode()).hexdigest(),
                             "comparison_output":comparison,"matches_expected":comparison==expected,
                             "statistics":stats,"statistics_parsed":statistics_parsed,
                             "argv":command,"binary_sha256":protocol["binaries"][config]["sha256"],
                             "fzn_sha256":inputs[record["id"]]["fzn"],"expected_sha256":inputs[record["id"]]["expected"],
                             "independent_mathematical_validation":False}
                        if isinstance(stats.get("initTime"),(int,float)) and isinstance(stats.get("solveTime"),(int,float)):
                            row["solver_elapsed_ms"]=(stats["initTime"]+stats["solveTime"])*1000
                        objective=scalar_objective(comparison,identifier)
                        if objective is not None:
                            row.update(objective_identifier=identifier,objective=objective)
                            expected_objective=scalar_objective(expected,identifier)
                            if expected_objective is not None: row["upstream_expected_objective"]=expected_objective
                        stream.write(json.dumps(row,separators=(",",":"))+"\n");stream.flush()
                        rows.append(row);done.add(key)
                        if time.perf_counter()-last_progress>=20:
                            print(f"FlatZinc: {len(done)}/{metadata['expected_runs']} runs",flush=True);last_progress=time.perf_counter()
        metadata["completed"]=True
    finally:
        metadata.update(finished_utc=utc(),completed_runs=len(done))
        meta_path.write_text(json.dumps(metadata,indent=2)+"\n")
        summary_path.write_text(json.dumps({"protocol":protocol,"groups":summarize(rows)},indent=2)+"\n")
        print(json.dumps({"completed":metadata["completed"],"runs":len(done),"outcomes":dict(Counter(r["status"] for r in rows))}),flush=True)


if __name__=="__main__": main()
