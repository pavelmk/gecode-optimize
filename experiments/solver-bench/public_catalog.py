#!/usr/bin/env python3
"""Import complete small OR-Library optimization instances into binary Ax>=b.

Reads local, hash-pinned official downloads only. mknap1 and gap1 are both
maximization collections: our objective is their negative profit. Published
optima are validation metadata and never guide common incumbent construction.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time

import validate

HERE = Path(__file__).resolve().parent
CACHE = HERE / "public-cache"
FILES = {
    "mknap1.txt": "727c5f90b6acafa0896ce4b5b5559e2995303b735ee083a07e9b724738fac283",
    "gap1.txt": "3395ba9f775d5a608ad107e946021a89688bc0d62b5a5c07585744ea98b1d706",
}
BASE = "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/"
GAP_OPTIMA = [336, 327, 339, 341, 326]


def sha(data): return hashlib.sha256(data).hexdigest()


class Integers:
    def __init__(self, raw):
        self.values = raw.decode("ascii").split()
        self.at = 0
    def take(self, n=1):
        if n < 0 or self.at + n > len(self.values): raise ValueError("truncated public source")
        result = [int(value) for value in self.values[self.at:self.at+n]]; self.at += n
        return result[0] if n == 1 else result
    def array(self, n):
        result = self.take(n)
        return [result] if n == 1 else result
    def rationals(self, n):
        if n < 0 or self.at+n > len(self.values): raise ValueError("truncated public rational data")
        result = [Fraction(value) for value in self.values[self.at:self.at+n]]
        self.at += n; return result
    def finish(self):
        if self.at != len(self.values): raise ValueError("unconsumed public source values")


def parse_mknap(raw):
    tokens = Integers(raw); records = []
    for ordinal in range(tokens.take()):
        start = tokens.at
        n, m = tokens.array(2)
        original_optimum = tokens.rationals(1)[0]
        if not 1 <= n <= 10000 or not 1 <= m <= 10000: raise ValueError("mknap dimensions")
        original_profits = tokens.rationals(n)
        scale = math.lcm(*(value.denominator for value in original_profits))
        profits = [int(value*scale) for value in original_profits]
        if (original_optimum*scale).denominator != 1: raise ValueError("optimum not on scaled objective lattice")
        optimum = int(original_optimum*scale)
        weights = [tokens.array(n) for _ in range(m)]
        capacities = tokens.array(m)
        if min(profits + capacities + [w for row in weights for w in row]) < 0:
            raise ValueError("negative mknap data")
        records.append(dict(n=n, profits=profits, weights=weights, capacities=capacities,
                            optimum=optimum, objective_scale=scale,
                            original_profit_values=[str(value) for value in original_profits], ordinal=ordinal+1,
                            source_instance_sha256=sha(json.dumps(tokens.values[start:tokens.at], separators=(",", ":")).encode())))
    tokens.finish(); return records


def parse_gap(raw):
    tokens = Integers(raw); records = []
    for ordinal in range(tokens.take()):
        start = tokens.at; agents, jobs = tokens.array(2)
        if not 1 <= agents <= 100 or not 1 <= jobs <= 1000: raise ValueError("gap dimensions")
        profits = [tokens.array(jobs) for _ in range(agents)]
        resources = [tokens.array(jobs) for _ in range(agents)]
        capacities = tokens.array(agents)
        if min(capacities + [v for row in profits + resources for v in row]) < 0:
            raise ValueError("negative gap data")
        records.append(dict(agents=agents, jobs=jobs, profits=profits, resources=resources,
                            capacities=capacities, ordinal=ordinal+1,
                            source_instance_sha256=sha(json.dumps(tokens.values[start:tokens.at], separators=(",", ":")).encode())))
    tokens.finish(); return records


def knapsack_incumbent(p):
    # A fixed profit/resource ranking uses only actual problem coefficients.
    n = p["n"]; remaining = list(p["capacities"]); chosen = [0] * n
    order = sorted(range(n), key=lambda j: (-Fraction(p["profits"][j], 1 + sum(row[j] for row in p["weights"])), j))
    for j in order:
        if all(row[j] <= capacity for row, capacity in zip(p["weights"], remaining)):
            chosen[j] = 1
            remaining = [capacity - row[j] for row, capacity in zip(p["weights"], remaining)]
    return chosen


def gap_incumbent(p):
    # Bounded deterministic greedy attempts; no search engine or reference used.
    agents, jobs = p["agents"], p["jobs"]
    resource, profit = p["resources"], p["profits"]
    orders = [list(range(jobs)),
              sorted(range(jobs), key=lambda j: (-min(resource[a][j] for a in range(agents)), j)),
              sorted(range(jobs), key=lambda j: (-max(profit[a][j] for a in range(agents)), j))]
    for ranking in orders:
        for shift in range(jobs):
            remaining = list(p["capacities"]); assignment = [-1] * jobs
            for j in ranking[shift:] + ranking[:shift]:
                available = [a for a in range(agents) if resource[a][j] <= remaining[a]]
                if not available: break
                a = min(available, key=lambda a: (Fraction(resource[a][j], max(1, remaining[a])), -profit[a][j], a))
                assignment[j] = a; remaining[a] -= resource[a][j]
            if all(a >= 0 for a in assignment):
                return [int(assignment[j] == a) for j in range(jobs) for a in range(agents)]
    return None


def sparse(coefficients): return [[j, value] for j, value in enumerate(coefficients) if value]


def formulate_knapsack(p):
    return {"n": p["n"], "c": [-v for v in p["profits"]],
            "rows": [{"a": sparse([-v for v in weights]), "b": -capacity}
                     for weights, capacity in zip(p["weights"], p["capacities"])]}


def formulate_gap(p):
    m, jobs = p["agents"], p["jobs"]
    model = {"n": m*jobs, "c": [-p["profits"][a][j] for j in range(jobs) for a in range(m)], "rows": []}
    for j in range(jobs):
        model["rows"].append({"a": [[j*m+a, 1] for a in range(m)], "b": 1})
        model["rows"].append({"a": [[j*m+a, -1] for a in range(m)], "b": -1})
    for a in range(m):
        model["rows"].append({"a": [[j*m+a, -p["resources"][a][j]] for j in range(jobs) if p["resources"][a][j]],
                              "b": -p["capacities"][a]})
    return model


def encode(p):
    lines = [f"{p['n']} {len(p['rows'])}", " ".join(map(str, p["c"]))]
    for row in p["rows"]:
        lines.append(" ".join(map(str, [row["b"], len(row["a"])] + [v for pair in row["a"] for v in pair])))
    lines.append("incumbent " + str(int("incumbent" in p)))
    if "incumbent" in p: lines.append(" ".join(map(str, p["incumbent"])))
    return "\n".join(lines) + "\n"


def generate(cache=CACHE, output=HERE):
    cache, output = Path(cache), Path(output)
    raw_files = {name: (cache/name).read_bytes() for name in FILES}
    for name, raw in raw_files.items():
        if sha(raw) != FILES[name]: raise ValueError(f"Changed {name}: published references are not transferable")
    license_page = (cache/"or-library-license.html").read_text()
    if "Permission is hereby granted" not in license_page: raise ValueError("OR-Library license missing")
    directory = output/"public-binary-instances"; directory.mkdir(parents=True, exist_ok=True)
    (directory/"OR-Library-LICENSE.html").write_text(license_page)
    manifest, instances = [], []
    for collection, records in (("mknap1", parse_mknap(raw_files["mknap1.txt"])), ("gap1", parse_gap(raw_files["gap1.txt"]))):
        expected_count = 7 if collection == "mknap1" else 5
        if len(records) != expected_count: raise ValueError("unexpected official collection size")
        for source in records:
            started = time.perf_counter(); is_knapsack = collection == "mknap1"
            p = (formulate_knapsack if is_knapsack else formulate_gap)(source)
            witness = (knapsack_incumbent if is_knapsack else gap_incumbent)(source)
            identity = f"public_{collection}_{source['ordinal']}"
            p.update(id=identity, family="multidimensional_knapsack" if is_knapsack else "generalized_assignment",
                     kind="binary", tier="public", split="public", seed=None,
                     label=f"OR-Library {collection} complete instance {source['ordinal']}")
            if witness is not None:
                checked = validate.validate_assignment(p, witness)
                if not checked["valid"]: raise AssertionError("invalid common greedy witness")
                p.update(incumbent=witness, incumbent_objective=checked["objective"])
            p.update(incumbent_method="bounded deterministic coefficient-only greedy construction",
                     construction_ms=(time.perf_counter()-started)*1000)
            optimum = source["optimum"] if is_knapsack else GAP_OPTIMA[source["ordinal"]-1]
            p["reference"] = {"status": "optimal" if optimum else "unknown",
                              "input_sha256": validate.input_hash(p),
                              "source_url": BASE + ("mknapinfo.html" if is_knapsack else "gapinfo.html"),
                              "method": "official OR-Library optimum in original maximization convention, sign reversed",
                              "used_for_solver_initialization": False}
            objective_scale = source.get("objective_scale", 1)
            if optimum: p["reference"].update(objective=-optimum,
                original_maximization_objective=str(Fraction(optimum, objective_scale)),
                objective_scale=objective_scale)
            p["provenance"] = {"source_url": BASE+"files/"+collection+".txt", "collection": collection,
                               "source_file_sha256": FILES[collection+".txt"],
                               "source_instance_sha256": source["source_instance_sha256"],
                               "source_instance_ordinal": source["ordinal"], "whole_original_instance": True,
                               "objective_transform": "minimize negative original profit times objective_scale", "objective_scale": objective_scale,
                               "row_transform": "negate <= resource rows; equality becomes two >= rows",
                               "column_mapping": "original item order" if is_knapsack else "job-major, then agent: column=job*agents+agent",
                               "license_url": BASE+"legal.html", "license_notice": "public-binary-instances/OR-Library-LICENSE.html"}
            p["original_data"] = {key: value for key, value in source.items() if key not in ("optimum", "source_instance_sha256")}
            validate.check_instance(p)
            if witness is not None and optimum and p["incumbent_objective"] < -optimum:
                raise AssertionError("greedy witness contradicts official optimum")
            stem = directory/identity; stem.with_suffix(".json").write_text(json.dumps(p, indent=2)+"\n")
            stem.with_suffix(".txt").write_text(encode(p))
            manifest.append({key:p[key] for key in ("id", "family", "tier", "split", "seed", "label", "kind")}
                            | {"json":str(stem.with_suffix(".json").relative_to(output)), "txt":str(stem.with_suffix(".txt").relative_to(output))})
            instances.append(p)
    (output/"public-binary-manifest.json").write_text(json.dumps({"schema_version":1, "instances":manifest,
        "selection":"all7 mknap1 and all5 gap1 complete instances; source/size chosen before any solver timing",
        "references":"official maximization optima negated for common minimization convention; references excluded from solver inputs"}, indent=2)+"\n")
    return instances


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE); parser.add_argument("--output", type=Path, default=HERE)
    args=parser.parse_args(); instances=generate(args.cache,args.output)
    print(json.dumps({"imported":len(instances), "greedy_witnesses":sum("incumbent" in p for p in instances),
                      "dimensions":[[p["id"],p["n"],len(p["rows"])] for p in instances]}))
