#!/usr/bin/env python3
"""Paired serial LP/CP benchmarks with independent exact-result validation."""
import argparse
import hashlib
import json
import platform
import random
import statistics
import subprocess
import time
from pathlib import Path
from validate import validate_result

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CONFIGS={"stock-afc":("stock","none","afc"),"disabled-afc":("lp","none","afc"),
         "root-afc":("lp","root","afc"),"node-afc":("lp","node","afc"),
         "stock-size":("stock","none","size"),"root-size":("lp","root","size"),
         "node-size":("lp","node","size")}

def complete(row): return row["status"] in ("optimal","infeasible")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin",type=Path,default=ROOT/"build/lp-relaxation/bin")
    parser.add_argument("--manifest",type=Path,default=HERE/"manifest.json")
    parser.add_argument("--split",default="test")
    parser.add_argument("--configs",default=",".join(CONFIGS))
    parser.add_argument("--limit-ms",type=float,default=3000)
    parser.add_argument("--repeats",type=int,default=5)
    parser.add_argument("--warm",type=int,choices=[0,1],default=1)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ids",default="")
    args=parser.parse_args()
    records=json.loads(args.manifest.read_text())["instances"]
    records=[r for r in records if r["split"] in args.split.split(",")]
    if args.ids: records=[r for r in records if r["id"] in args.ids.split(",")]
    if not records: raise ValueError("No matching inputs")
    configs=args.configs.split(",")
    metadata={"platform":platform.platform(),"split":args.split,"warm_start":bool(args.warm),
              "limit_ms":args.limit_ms,"repeats":args.repeats,"configs":configs,
              "manifest_sha256":hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              "binaries":{n:hashlib.sha256((args.bin/n).read_bytes()).hexdigest() for n in ["stock","lp"]},
              "timing":"Includes LP model/workspace construction, CP construction, search, and LP/engine teardown. Excludes input parsing, offline common incumbent generation, output serialization, and process startup.",
              "highs_mip_used":False,"prior_checkpoint_feature_enabled":False,
              "prior_clique_feature_enabled":False}
    args.output.parent.mkdir(exist_ok=True,parents=True)
    args.output.with_suffix(".meta.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rows=[]; rng=random.Random(839741)
    with args.output.open("w") as out:
        for rep in range(args.repeats):
            instances=list(records);rng.shuffle(instances)
            for record in instances:
                item=json.loads((args.manifest.parent/record["json"]).read_text())
                order=list(configs);rng.shuffle(order)
                for config in order:
                    binary,mode,branching=CONFIGS[config]
                    command=[str(args.bin/binary),str(args.manifest.parent/record["txt"]),mode,branching,
                             str(args.limit_ms),str(args.warm),"1"]
                    start=time.perf_counter()
                    result=subprocess.run(command,check=True,text=True,capture_output=True,
                                          timeout=args.limit_ms/1000+30)
                    wall=(time.perf_counter()-start)*1000
                    row=json.loads(result.stdout)
                    validation=validate_result(item,row)
                    if not validation["valid"]: raise RuntimeError((record["id"],config,validation,row))
                    row.update(id=record["id"],family=record["family"],split=record["split"],
                               label=record["label"],config=config,repetition=rep,
                               process_wall_ms=wall,validation=validation,
                               reference_objective=item.get("reference",{}).get("objective"),
                               initial_objective=item.get("incumbent_objective") if args.warm else None)
                    rows.append(row);out.write(json.dumps(row,separators=(",",":"))+"\n");out.flush()
            print(f"Completed {rep+1}/{args.repeats} repetitions; {len(rows)} validated runs",flush=True)
    summary={}
    for config in configs:
        groups={}
        for row in rows:
            if row["config"]==config: groups.setdefault(row["id"],[]).append(row)
        entries=[]
        for name,runs in groups.items():
            entry={"id":name,"family":runs[0]["family"],"completed_runs":sum(complete(r) for r in runs),
                   "runs":len(runs),"objectives":[r["objective"] for r in runs],
                   "par2_ms":statistics.median(r["elapsed_ms"] if complete(r) else 2*args.limit_ms for r in runs)}
            for field in ["elapsed_ms","nodes","lp_calls","lp_ms","build_ms","peak_rss_kb","process_wall_ms"]:
                entry["median_"+field]=statistics.median(r[field] for r in runs)
            entries.append(entry)
        summary[config]={"instances":entries,"completed":sum(e["completed_runs"]==e["runs"] for e in entries),
                         "count":len(entries),"mean_par2_ms":statistics.mean(e["par2_ms"] for e in entries)}
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({name:{k:v for k,v in value.items() if k!="instances"} for name,value in summary.items()},indent=2))

if __name__=="__main__":main()
