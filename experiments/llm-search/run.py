#!/usr/bin/env python3
"""Reproduce correctness checks, development selection, and held-out timings."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def run(command, log=None):
    print(" ".join(map(str,command)),flush=True)
    if log:
        with log.open("w") as output:
            subprocess.run(list(map(str,command)),check=True,stdout=output,stderr=subprocess.STDOUT)
    else:
        subprocess.run(list(map(str,command)),check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skip-build",action="store_true")
    p.add_argument("--skip-upstream",action="store_true",help="only if the upstream suite has already passed")
    p.add_argument("--repeats",type=int,default=7)
    p.add_argument("--limit-ms",type=int,default=1000)
    a=p.parse_args()
    if sys.version_info<(3,12): raise SystemExit("Use Python 3.12 or newer")
    results=HERE/"results"; results.mkdir(exist_ok=True)
    binary=ROOT/"build/llm-search/bin"
    if not a.skip_build: run([sys.executable,HERE/"build.py"],results/"build.log")
    run([sys.executable,HERE/"generator.py"])
    run([sys.executable,HERE/"generate_demos.py"])
    run([sys.executable,HERE/"test_validate.py"],results/"validator-tests.log")
    run([sys.executable,HERE/"certify.py"],results/"certify.log")
    for name in ["checkpoint","cliques"]:
        run([binary/("test-"+name)],results/(name+"-tests.log"))
    if not a.skip_upstream:
        (results/"upstream-search-status.json").write_text(json.dumps({"exit_code":None,"status":"running"})+"\n")
        run([binary/"test-upstream-search","-iter","1","-threads","1","-seed","1"],results/"upstream-search.log")
        (results/"upstream-search-status.json").write_text(json.dumps({"exit_code":0,"status":"passed"})+"\n")
    bench=[sys.executable,HERE/"bench.py","--bin",binary,"--limit-ms",a.limit_ms]
    run([*bench,"--split","tiny,control","--modes","stock,disabled,checkpoint,cliques,combined",
         "--cp","10","--repeats","1","--output",results/"correctness.jsonl"],results/"correctness.log")
    run([*bench,"--split","dev","--modes","stock,disabled,cp-1,cp-5,cp-10,cp-25,cp-100,stock-copy1,stock-copy32",
         "--repeats","5","--output",results/"development.jsonl"],results/"development.log")
    development=json.loads((results/"development.summary.json").read_text())
    eligible={name:entry["mean_par2_ms"] for name,entry in development.items() if name.startswith("cp-")}
    winner=min(eligible,key=eligible.get)
    cp=int(winner[3:])
    selection={"selected_cp":cp,"criterion":"lowest mean per-instance median PAR-2 on development set",
               "candidate_scores_ms":eligible,"test_instances_used_for_selection":False,
               "note":"Best experimental threshold; stock/tuned-stock may still be faster."}
    (results/"selection.json").write_text(json.dumps(selection,indent=2)+"\n")
    print(json.dumps(selection),flush=True)
    run([*bench,"--split","test","--cp",cp,"--repeats",a.repeats,
         "--output",results/"held-out.jsonl"],results/"held-out.log")
    run([*bench,"--manifest",HERE/"demo-manifest.json","--split","demo","--cp",cp,
         "--modes","stock,cliques,combined,stock-copy1","--repeats","5",
         "--output",results/"demonstrations.jsonl"],results/"demonstrations.log")
    run([sys.executable,HERE/"analyze.py"])


if __name__=="__main__": main()
