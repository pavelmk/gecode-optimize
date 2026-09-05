#!/usr/bin/env python3
"""Validate OR-Library parsing, exact scaling, matrix translation, and FZN extraction."""
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import public_catalog as public
import fzn_import
import validate


def require(condition,text):
    if not condition: raise AssertionError(text)


def main():
    rng=random.Random(7129)
    with tempfile.TemporaryDirectory(prefix="gecode-public-catalog-") as temporary:
        instances=public.generate(output=temporary)
        require(len(instances)==12,"wrong public instance count")
        for p in instances:
            source=p["original_data"]
            require(p["split"]=="public" and p["provenance"]["whole_original_instance"],"partial/development import")
            require(validate.validate_assignment(p,p["incumbent"])["valid"],"invalid warm start")
            require(p["reference"]["input_sha256"]==validate.input_hash(p),"stale reference")
            for _ in range(50):
                if p["family"]=="multidimensional_knapsack":
                    x=[rng.randrange(2) for _ in range(p["n"])]
                    feasible=all(sum(v*w for v,w in zip(x,row))<=cap for row,cap in zip(source["weights"],source["capacities"]))
                    objective=-sum(v*w for v,w in zip(x,source["profits"]))
                else:
                    m,jobs=source["agents"],source["jobs"]
                    assigned=[rng.randrange(m) for _ in range(jobs)]
                    x=[int(assigned[j]==a) for j in range(jobs) for a in range(m)]
                    feasible=all(sum(source["resources"][a][j] for j in range(jobs) if assigned[j]==a)<=source["capacities"][a] for a in range(m))
                    objective=-sum(source["profits"][a][j] for j,a in enumerate(assigned))
                matrix_feasible,matrix_objective=validate.linear_check(p,x)
                require(feasible==matrix_feasible and objective==matrix_objective,"original domain/matrix translation mismatch")
        # Independent complete references for the two smallest original cases,
        # including the source's decimal-profit instance and exact scaling.
        for p in instances[:2]:
            best=min(sum(c*x for c,x in zip(p["c"],assignment))
                     for assignment in itertools.product((0,1),repeat=p["n"])
                     if all(sum(a*assignment[j] for j,a in row["a"])>=row["b"] for row in p["rows"]))
            require(best==p["reference"]["objective"],"published small optimum or sign/scaling mismatch")
        require(instances[1]["provenance"]["objective_scale"]==10,"decimal source profits were rounded")
        require(instances[1]["reference"]["objective"]==-87061,"wrong scaled optimum")
    # Literal extraction covers escaped-newline strings, concatenation, and
    # modern C++ raw-string fixtures without ever evaluating C++ source.
    raw='(void)new FlatZincTest("x",R"FZN(var 1..2: x; solve minimize x;)FZN",std::string("x = 1;\\n")+"----------\\n");'
    args=fzn_import.arguments(raw)
    require(fzn_import.literal_expression(args[1])=="var 1..2: x; solve minimize x;","raw literal extraction mismatch")
    require(fzn_import.literal_expression(args[2])=="x = 1;\n----------\n","concatenated literal extraction mismatch")
    manifest=json.loads((public.HERE/"fzn-manifest.json").read_text())
    for p in manifest["instances"]:
        model=(public.HERE/p["fzn"]).read_text(); expected=(public.HERE/p["expected"]).read_text()
        require(hashlib.sha256(model.encode()).hexdigest()==p["fzn_sha256"],"FZN payload hash mismatch")
        require(hashlib.sha256(expected.encode()).hexdigest()==p["expected_sha256"],"upstream output hash mismatch")
        source=fzn_import.extract(public.HERE.parents[1]/p["source"])
        require(source["model"]==model and source["expected"]==expected,"saved fixture differs from upstream literal")
    print(f"PASS12 whole OR-Library instances,600 original/matrix comparisons,2 exhaustive optima,exact decimal scaling,and{len(manifest['instances'])} unchanged FlatZinc payloads")


if __name__=="__main__":main()
