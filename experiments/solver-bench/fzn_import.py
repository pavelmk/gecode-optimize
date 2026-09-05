#!/usr/bin/env python3
"""Extract unchanged public FlatZinc regression models already bundled by Gecode.

This is a regression-scale compatibility track, not MiniZinc Challenge data or
an independent proof checker. Original annotated search and exact expected text
are preserved. Different valid solutions may fail exact-output comparison.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "test" / "flatzinc"
SOURCE_BASE = "https://github.com/Gecode/gecode/blob/release-6.4.0/test/flatzinc/"
STRING = re.compile(r'"(?:[^"\\]|\\.)*"', re.S)
RAW_STRING = re.compile(r'R"(?P<delimiter>[^ ()\\\t\r\n]{0,16})\((?P<body>.*?)\)(?P=delimiter)"', re.S)
GROUPS = {
    "geometry_cutting": {"2dpacking", "packing", "perfsq", "perfsq2", "cutstock"},
    "latin_magic_design": {"magicsq_3", "magicsq_4", "magicsq_5", "latin_squares_fd", "quasigroup_qg5", "sudoku"},
    "logic_battleships": {"battleships1", "battleships2", "battleships3", "battleships4", "battleships5", "battleships7", "battleships9", "battleships10"},
    "sequence_planning": {"blocksworld_instance_1", "blocksworld_instance_2", "wolf_goat_cabbage", "langford2", "knights", "photo"},
    "scheduling": {"jobshop", "jobshop2x2", "oss", "singHoist2", "timetabling", "trucking", "cumulatives"},
    "allocation_production": {"warehouses", "warehouses_small", "factory_planning_instance", "product_fd", "product_lp", "template_design", "multidim_knapsack_simple"},
    "other_mathematical": {"golomb", "radiation", "steiner_triples"},
}
SAT_SELECTED = set().union(*GROUPS.values())


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def arguments(source):
    """Split one constructor call without evaluating any C++ code."""
    source = RAW_STRING.sub(lambda match: json.dumps(match.group("body")), source)
    source = source.replace("\\\r\n", "").replace("\\\n", "")
    matches = list(re.finditer(r"\bnew\s+FlatZincTest\s*\(", source))
    if len(matches) != 1:
        raise ValueError("expected one FlatZincTest constructor")
    start = at = matches[0].end()
    depth = 0; quoted = False; escaped = False; parts = []
    while at < len(source):
        ch = source[at]
        if quoted:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': quoted = False
        elif ch == '"': quoted = True
        elif ch in "([{": depth += 1
        elif ch in ")]}":
            if ch == ")" and depth == 0:
                parts.append(source[start:at]); return parts
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(source[start:at]); start = at + 1
        at += 1
    raise ValueError("unterminated FlatZincTest constructor")


def literal_expression(expression):
    tokens = list(STRING.finditer(expression))
    if not tokens: raise ValueError("argument is not a literal string")
    remainder = STRING.sub("", expression)
    remainder = re.sub(r"std\s*::\s*string|[\s()+]", "", remainder)
    if remainder: raise ValueError("unsupported nonliteral expression")
    return "".join(ast.literal_eval(token.group(0)) for token in tokens)


def extract(path):
    path = Path(path); source = path.read_text(); parts = arguments(source)
    if len(parts) < 3: raise ValueError("missing source or expected output")
    name, model, expected = map(literal_expression, parts[:3])
    all_solutions = False
    if len(parts) > 3:
        if parts[3].strip() not in ("true", "false"):
            raise ValueError("custom all-solutions expression")
        all_solutions = parts[3].strip() == "true"
    if len(parts) > 4:
        raise ValueError("custom command-line/hooks require dedicated runner")
    solve = re.search(r"\bsolve\b(.*?);", re.sub(r"%[^\n]*", "", model), re.S)
    if not solve: raise ValueError("no FlatZinc solve item")
    direction = re.search(r"\b(satisfy|minimize|maximize)\b", solve.group(1))
    if not direction: raise ValueError("unknown solve mode")
    marker = source.find('#include "test/flatzinc.hh"')
    notice = source[:marker].strip() if marker >= 0 else ""
    if "Permission is hereby granted" not in notice:
        raise ValueError("source permission notice not found")
    actual_predicates = sorted(set(re.findall(r"\bconstraint\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(", model)))
    return {"upstream_test_name": name, "model": model, "expected": expected,
            "source_sha256": digest(source), "fzn_sha256": digest(model),
            "expected_sha256": digest(expected), "notice": notice,
            "solve": direction.group(1), "all_solutions": all_solutions,
            "constraint_predicates": actual_predicates,
            "requires_float": bool(re.search(r"\bfloat\b|\bfloat_", model)),
            "requires_set": bool(re.search(r"\bvar\s+set\b|^constraint\s+set_", model, re.M))}


def generate(source=SOURCE, output=HERE):
    source, output = Path(source), Path(output)
    directory = output / "fzn-instances"; directory.mkdir(parents=True, exist_ok=True)
    records, skipped = [], []
    for path in sorted(source.glob("*.cpp")):
        try: item = extract(path)
        except (ValueError, SyntaxError) as error:
            skipped.append({"source": path.name, "reason": str(error)}); continue
        if item["solve"] == "satisfy" and path.stem not in SAT_SELECTED:
            continue
        group = next((key for key, values in GROUPS.items() if path.stem in values), "solver_regression")
        identity = f"public_fzn_{path.stem}"
        stem = directory / identity
        stem.with_suffix(".fzn").write_text(item["model"])
        stem.with_suffix(".expected").write_text(item["expected"])
        stem.with_suffix(".NOTICE.txt").write_text(item["notice"] + "\n")
        record = {key: value for key, value in item.items() if key not in ("model", "expected", "notice")}
        record.update(id=identity, family=group, tier="regression", split="public", seed=None,
                      label=f"Gecode upstream FlatZinc regression {path.stem}", kind="flatzinc",
                      track="satisfaction_compatibility" if item["solve"] == "satisfy" else "optimization_regression",
                      source=str(path.relative_to(source.parent.parent)), source_url=SOURCE_BASE + path.name,
                      fzn=str(stem.with_suffix(".fzn").relative_to(output)),
                      expected=str(stem.with_suffix(".expected").relative_to(output)),
                      license_notice=str(stem.with_suffix(".NOTICE.txt").relative_to(output)),
                      provenance="unchanged model and expected output extracted from Gecode 6.4.0 regression source",
                      validation="upstream exact output under original search; not an independent mathematical oracle",
                      model_modified=False)
        records.append(record)
    manifest = {"schema_version": 1, "instances": records, "skipped_sources": skipped,
                "scale": "upstream regression fixtures; not MiniZinc Challenge competition instances",
                "validation_limit": "Exact expected output is useful with original search. Alternate valid solutions require semantic checking and must not be called invalid solely for differing text.",
                "reporting": "Keep SAT compatibility and optimization regression results separate from generated binary/native optimization headline metrics."}
    (output / "fzn-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args(); manifest = generate(args.source, args.output)
    counts = {}
    for item in manifest["instances"]: counts[item["track"]] = counts.get(item["track"], 0) + 1
    print(json.dumps({"extracted": len(manifest["instances"]), "tracks": counts,
                      "custom_or_unparsed_sources": len(manifest["skipped_sources"])}, sort_keys=True))


if __name__ == "__main__": main()
