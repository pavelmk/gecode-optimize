#!/usr/bin/env python3
"""Deliberately favorable and unfavorable examples, separate from random suite.

The pigeonhole examples encode k+1 mutually different variables with k values
as binary constraints. They expose missing Hall-set reasoning directly. They
are demonstrations of formulation strengthening, not representative workloads.
"""
import itertools
import json
from pathlib import Path
from generator import to_text

HERE=Path(__file__).resolve().parent


def main():
    directory=HERE/"demonstrations"
    directory.mkdir(exist_ok=True)
    records=[]
    for k in [8,9,10,11]:
        n=k+1
        item={"id":f"demo_pigeonhole_{n}_into_{k}","family":"coloring","n":n,"colors":k,
              "split":"demo","seed":None,"label":"deliberately-favorable-Hall-contradiction",
              "edges":[list(e) for e in itertools.combinations(range(n),2)],
              "infeasibility_certificate":{"type":"clique","vertices":list(range(n))}}
        path=directory/item["id"]
        path.with_suffix(".json").write_text(json.dumps(item,indent=2)+"\n")
        path.with_suffix(".txt").write_text(to_text(item))
        records.append({key:item[key] for key in ["id","family","split","seed","label","n"]})
        records[-1].update(json=str(path.with_suffix(".json").relative_to(HERE)),
                           txt=str(path.with_suffix(".txt").relative_to(HERE)))
    # Triangle-free easy graph: inference finds no clique and adds overhead.
    n=300
    item={"id":"demo_sparse_cycle","family":"coloring","n":n,"colors":3,
          "split":"demo","seed":None,"label":"unfavorable-no-cliques",
          "edges":[[i,i+1] for i in range(n-1)]+[[0,n-1]]}
    path=directory/item["id"]
    path.with_suffix(".json").write_text(json.dumps(item,indent=2)+"\n")
    path.with_suffix(".txt").write_text(to_text(item))
    records.append({key:item[key] for key in ["id","family","split","seed","label","n"]})
    records[-1].update(json=str(path.with_suffix(".json").relative_to(HERE)),
                       txt=str(path.with_suffix(".txt").relative_to(HERE)))
    (HERE/"demo-manifest.json").write_text(json.dumps({"instances":records},indent=2)+"\n")


if __name__=="__main__": main()
