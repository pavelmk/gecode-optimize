#!/usr/bin/env python3
"""Generate reproducible CP benchmark instances, metadata and whitespace inputs.

Default suite: 6 dev + 6 test instances per family, 8 tiny checks per family,
and two controls. Scale and graph densities are exposed for later experiments.
No runtime measurements are performed here.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path

from validate import check_instance, exact_solve, validate_assignment, verify_infeasibility_certificate


FAMILIES = ("coloring", "scheduling", "vertex_cover")


def make_instance(family, split, seed, index=0, scale=1.0, coloring_density=0.24,
                  cover_density=0.16):
    # Independent local RNG: generation order and other families cannot affect it.
    rng = random.Random(seed)
    tiny = split == "tiny"
    base = {"id": f"{split}_{family}_{seed}", "family": family,
            "split": split, "seed": seed, "generator_version": 1,
            "label": "tiny-exact" if tiny else "moderate-random"}
    if family == "coloring":
        k = 2 + index % 2 if tiny else 3 + index % 2
        if not tiny and index % 6 == 5:
            k = 3
        n = 5 + index % 3 if tiny else max(k + 1, round((36 + 4 * (index % 3)) * scale))
        planted = [i % k for i in range(n)]
        rng.shuffle(planted)
        density = 0.30 if tiny else coloring_density
        edges = {(u, v) for u in range(n) for v in range(u + 1, n)
                 if planted[u] != planted[v] and rng.random() < density}
        base.update(n=n, colors=k, density=density)
        if index % 3 == 0 or index % 6 == 4:
            # One vertex per planted color preserves the witness. Reusing vertices
            # creates overlapping cliques, after the vertex IDs were randomized.
            groups = [[v for v in range(n) if planted[v] == color] for color in range(k)]
            for _ in range(n if not tiny else 3):
                clique = sorted(rng.choice(group) for group in groups)
                edges.update(itertools.combinations(clique, 2))
            base["label"] = "planted-overlapping-cliques"
        # Two of six medium cases have a short, independently checkable UNSAT proof.
        if not tiny and index % 6 == 5:
            wheel = rng.sample(range(n), 6)
            hub, rim = wheel[0], wheel[1:]
            edges.update(tuple(sorted((hub, v))) for v in rim)
            edges.update(tuple(sorted((rim[i], rim[(i + 1) % len(rim)]))) for i in range(len(rim)))
            base.update(label="unsat-odd-wheel", infeasibility_certificate={
                "type": "odd_wheel", "hub": hub, "rim": rim})
        elif index % 3 == 2:
            clique = sorted(rng.sample(range(n), k + 1))
            edges.update(itertools.combinations(clique, 2))
            base.update(label="unsat-clique-control", infeasibility_certificate={
                "type": "clique", "vertices": clique})
        else:
            base["reference"] = {"status": "optimal", "objective": 0,
                                 "assignment": planted, "certificate": "planted coloring witness"}
        base["edges"] = [list(e) for e in sorted(edges)]
    elif family == "scheduling":
        m = 2 + index % 2 if tiny else 3 + index % 3
        n = 6 + index % 3 if tiny else max(m, round((20 + 2 * (index % 3)) * scale))
        durations = [rng.randint(1, 12 if tiny else 100) for _ in range(n)]
        rng.shuffle(durations)
        base.update(n=n, machines=m, durations=durations,
                    lower_bound=max(max(durations), (sum(durations) + m - 1) // m))
    else:
        n = 7 + index % 3 if tiny else max(2, round((28 + 3 * (index % 3)) * scale))
        density = 0.30 if tiny else cover_density
        edges = [[u, v] for u in range(n) for v in range(u + 1, n)
                 if rng.random() < density]
        weights = [rng.randint(1, 15 if tiny else 30) for _ in range(n)]
        base.update(n=n, weights=weights, edges=edges, density=density)
    check_instance(base)
    if tiny:
        base["reference"] = exact_solve(base)
        if base["reference"]["status"] == "unknown":
            raise ValueError("tiny reference unexpectedly exceeds enumeration budget")
    elif "reference" in base:
        if not validate_assignment(base, base["reference"]["assignment"])["valid"]:
            raise ValueError("invalid generated witness")
    if "infeasibility_certificate" in base and not verify_infeasibility_certificate(base):
        raise ValueError("invalid generated clique certificate")
    return base


def to_text(instance):
    family, n = instance["family"], instance["n"]
    if family == "scheduling":
        return f"scheduling {n} {instance['machines']}\n" + " ".join(map(str, instance["durations"])) + "\n"
    if family == "coloring":
        lines = [f"coloring {n} {instance['colors']} {len(instance['edges'])}"]
    else:
        lines = [f"vertex_cover {n} {len(instance['edges'])}", " ".join(map(str, instance["weights"]))]
    lines += [f"{u} {v}" for u, v in instance["edges"]]
    return "\n".join(lines) + "\n"


def write_suite(out_dir, per_split=6, tiny_per_family=8, scale=1.0,
                coloring_density=0.24, cover_density=0.16):
    out_dir = Path(out_dir)
    instance_dir = out_dir / "instances"
    instance_dir.mkdir(parents=True, exist_ok=True)
    instances = []
    # Offsets separate every family and split, not just the top-level splits.
    for split, offset, count in (("tiny", 100_000, tiny_per_family),
                                 ("dev", 200_000, per_split), ("test", 300_000, per_split)):
        for family_index, family in enumerate(FAMILIES):
            for index in range(count):
                seed = offset + family_index * 10_000 + index
                instances.append(make_instance(family, split, seed, index, scale,
                                               coloring_density, cover_density))
    controls = [
        {"id": "control_scheduling_local_minimum", "family": "scheduling", "split": "control",
         "seed": None, "generator_version": 1, "label": "coordinated-move-example", "n": 6,
         "machines": 2, "durations": [8, 7, 6, 5, 4, 3], "initial_assignment": [0, 1, 0, 1, 0, 1]},
        {"id": "control_vertex_cover_triangle", "family": "vertex_cover", "split": "control",
         "seed": None, "generator_version": 1, "label": "weighted-triangle", "n": 3,
         "weights": [2, 3, 8], "edges": [[0, 1], [0, 2], [1, 2]]},
    ]
    for control in controls:
        control["reference"] = exact_solve(control)
        instances.append(control)
    records = []
    for instance in instances:
        json_path = instance_dir / (instance["id"] + ".json")
        txt_path = instance_dir / (instance["id"] + ".txt")
        json_path.write_text(json.dumps(instance, indent=2, sort_keys=True) + "\n")
        txt_path.write_text(to_text(instance))
        records.append({key: instance[key] for key in ("id", "family", "split", "seed", "label", "n")})
        records[-1].update(json=str(json_path.relative_to(out_dir)), txt=str(txt_path.relative_to(out_dir)))
    manifest = {"schema_version": 1, "generator_version": 1,
                "parameters": {"per_split": per_split, "tiny_per_family": tiny_per_family,
                               "scale": scale, "coloring_density": coloring_density,
                               "cover_density": cover_density},
                "notes": ["Dev/test seeds are disjoint; freeze policy before test timings.",
                          "Labels describe construction, not measured difficulty or expected speedup.",
                          "JSON references/certificates are for independent validation only; solver consumes TXT.",
                          "Tiny exact oracles and controls are correctness checks, not speed benchmarks.",
                          "Unsat coloring cases have short clique/odd-wheel proofs, not general hard UNSAT instances."],
                "instances": records}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--per-split", type=int, default=6)
    parser.add_argument("--tiny-per-family", type=int, default=8)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--coloring-density", type=float, default=0.24)
    parser.add_argument("--cover-density", type=float, default=0.16)
    args = parser.parse_args()
    if not 0 <= args.per_split < 10_000 or not 0 <= args.tiny_per_family < 10_000:
        parser.error("counts must be between 0 and 9999 to keep seed ranges disjoint")
    if args.scale <= 0 or not 0 <= args.coloring_density <= 1 or not 0 <= args.cover_density <= 1:
        parser.error("scale must be positive and densities must be in [0,1]")
    manifest = write_suite(args.out_dir, args.per_split, args.tiny_per_family, args.scale,
                           args.coloring_density, args.cover_density)
    print(json.dumps({"out_dir": str(args.out_dir), "instances": len(manifest["instances"]),
                      "timings_performed": False}))


if __name__ == "__main__":
    main()
