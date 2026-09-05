#!/usr/bin/env python3
"""Serial, randomized paired benchmarks; validate every returned solution."""
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
from certify import instance_hash

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def configuration(name, cp):
    configs={
        "stock":("stock",0,0,8,"size"),
        "disabled":("modified",0,0,8,"size"),
        "checkpoint":("modified",0,cp,8,"size"),
        "cliques":("modified",1,0,8,"size"),
        "combined":("modified",1,cp,8,"size"),
        "stock-copy1":("stock",0,0,1,"size"),
        "stock-copy32":("stock",0,0,32,"size"),
        "stock-afc":("stock",0,0,8,"afc"),
    }
    if name.startswith("cp-"): return ("modified",0,int(name[3:]),8,"size")
    return configs[name]


def completed(row):
    return row["status"] in ("optimal","infeasible") or (
        row["family"]=="coloring" and row["status"]=="feasible")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bin",type=Path,default=ROOT/"build/llm-search/bin")
    p.add_argument("--manifest",type=Path,default=HERE/"manifest.json")
    p.add_argument("--split",default="test")
    p.add_argument("--modes",default="stock,disabled,checkpoint,cliques,combined,stock-copy1,stock-afc")
    p.add_argument("--cp",type=int,default=10)
    p.add_argument("--limit-ms",type=float,default=1000)
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--ids",default="")
    a=p.parse_args()
    data_dir=a.manifest.parent
    records=json.loads(a.manifest.read_text())["instances"]
    records=[r for r in records if r["split"] in a.split.split(",")]
    if a.ids: records=[r for r in records if r["id"] in a.ids.split(",")]
    if not records: raise ValueError("No matching instances")
    modes=a.modes.split(",")
    certificate_path=HERE/"results/wvc-certificates.json"
    certificates={}
    if certificate_path.exists():
        certificates={r["id"]:r for r in json.loads(certificate_path.read_text())["results"]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    metadata={"platform":platform.platform(),"split":a.split,"cp":a.cp,
              "repeats":a.repeats,"limit_ms":a.limit_ms,"modes":modes,
              "manifest_sha256":hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
              "timing":"model construction + engine initialization + search + engine teardown; excludes input parsing/process startup/output serialization",
              "binaries":{name:hashlib.sha256((a.bin/name).read_bytes()).hexdigest() for name in ["stock","modified"]}}
    a.output.with_suffix(".meta.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rng=random.Random(984517)
    rows=[]
    optimum={}
    with a.output.open("w") as out:
        for repetition in range(a.repeats):
            order=list(records); rng.shuffle(order)
            for record in order:
                instance=json.loads((data_dir/record["json"]).read_text())
                if record["id"] in certificates:
                    if certificates[record["id"]]["input_sha256"]!=instance_hash(instance):
                        raise RuntimeError("Stale independent optimum reference")
                    instance["reference"]=certificates[record["id"]]
                mode_order=list(modes); rng.shuffle(mode_order)
                for mode in mode_order:
                    # A clique-only run is redundant for problems without disequalities.
                    if mode=="cliques" and instance["family"]!="coloring": continue
                    binary,cliques,cp,cd,branching=configuration(mode,a.cp)
                    command=[str(a.bin/binary),str(data_dir/record["txt"]),str(cliques),str(cp),
                             str(cd),branching,str(a.limit_ms),"1"]
                    start=time.perf_counter()
                    result=subprocess.run(command,text=True,capture_output=True,timeout=a.limit_ms/1000+30,check=True)
                    wall_ms=(time.perf_counter()-start)*1000
                    row=json.loads(result.stdout)
                    validation=validate_result(instance,row)
                    if not validation["valid"]: raise RuntimeError((record["id"],mode,validation,row))
                    if row["status"]=="optimal":
                        prior=optimum.setdefault(record["id"],row["objective"])
                        if prior!=row["objective"]: raise RuntimeError("Optimum mismatch across variants")
                    row.update(id=record["id"],split=record["split"],label=record["label"],mode=mode,
                               repetition=repetition,process_wall_ms=wall_ms,validation=validation,
                               cp=cp,copy_distance=cd,branching=branching)
                    rows.append(row)
                    out.write(json.dumps(row,separators=(",",":"))+"\n"); out.flush()
            print(f"Finished repetition {repetition+1}/{a.repeats}: {len(rows)} validated runs",flush=True)
    summary={}
    for mode in modes:
        group=[r for r in rows if r["mode"]==mode]
        if not group: continue
        by_instance={}
        for r in group: by_instance.setdefault(r["id"],[]).append(r)
        entries=[]
        for name,runs in by_instance.items():
            entries.append({"id":name,"family":runs[0]["family"],"completed":all(completed(r) for r in runs),
                            "median_ms":statistics.median(r["elapsed_ms"] for r in runs),
                            "median_nodes":statistics.median(r["nodes"] for r in runs),
                            "median_propagations":statistics.median(r["propagations"] for r in runs),
                            "objectives":[r["objective"] for r in runs],
                            "par2_ms":statistics.median(min(r["elapsed_ms"],a.limit_ms) if completed(r) else 2*a.limit_ms for r in runs)})
        summary[mode]={"instances":entries,"completed":sum(e["completed"] for e in entries),
                       "count":len(entries),"mean_par2_ms":statistics.mean(e["par2_ms"] for e in entries)}
    a.output.with_suffix(".summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({mode:{k:v for k,v in result.items() if k!="instances"} for mode,result in summary.items()},indent=2))


if __name__=="__main__": main()
