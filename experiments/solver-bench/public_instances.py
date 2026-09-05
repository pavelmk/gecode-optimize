#!/usr/bin/env python3
"""Import six unchanged public job-shop instances already distributed by Gecode.

No optimizer or network request is run. Published optima are validation metadata;
the solver's common initial witness is only a serial schedule. Source arrays are
hash-pinned so an edited instance cannot silently inherit a published optimum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import native

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "examples" / "job-shop-instances.hpp"
SOURCE_URL = "https://github.com/Gecode/gecode/blob/release-6.4.0/examples/job-shop-instances.hpp"
LAWRENCE_REFERENCE = "https://home.hiroshima-u.ac.jp/mkatsumi/open/HUGE/data/robust.html"
FT_REFERENCE = "https://github.com/ScheduleOpt/benchmarks/blob/main/jobshop/README.md#fisher-and-thompson-1963"
OR_LIBRARY = "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/jobshopinfo.html"
VERIFIED = {
    "ft06": (55, "40c023778613c9eb7524fddfee6f307917255d218f3d14d96e899476b7a59a46"),
    "la01": (666, "a0c7f3a1e1050ae055dd2315a57e0a2981bcdd4210c01bee2cb4d891937a8f06"),
    "la02": (655, "09671d640692cc721be90450ce611a49f4fdd17a3ac5e2f8a99823a913505c75"),
    "la03": (597, "9d6869b300331d303722d02652dad19e354bdfda5b2fb2d6788a7c2cc8487e99"),
    "la04": (590, "f899415c55ca5dbfdddfeea0d5b01ec268560a75190e58f6eebabfc77edcb25b"),
    "la05": (593, "2673bb752f814bc06fb8c92396520601f07c949e0dfd85432f7859a4d920c705"),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def extract_array(source, name):
    if name not in VERIFIED:
        raise ValueError(f"No hash-pinned public reference for {name}")
    expression = r"\bconst\s+int\s+" + re.escape(name) + r"\[\]\s*=\s*\{(.*?)\};"
    matches = list(re.finditer(expression, source, re.S))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one source array for {name}")
    raw = matches[0].group(0)
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", matches[0].group(1), flags=re.S)
    if re.sub(r"-?\d+|[,\s]", "", body):
        raise ValueError(f"Unsupported source expression in {name}")
    values = list(map(int, re.findall(r"-?\d+", body)))
    digest = sha256(json.dumps(values, separators=(",", ":")).encode())
    if digest != VERIFIED[name][1]:
        raise ValueError(f"Public source array {name} changed; published optimum is not transferable")
    return values, digest, sha256(raw.encode())


def make(source, name, source_file_sha256):
    started = time.perf_counter()
    values, array_sha, text_sha = extract_array(source, name)
    jobs, machines = values[:2]
    if not (1 <= jobs <= 100 and 1 <= machines <= 100) or len(values) != 2 + jobs * machines * 2:
        raise ValueError(f"Invalid rectangular job-shop dimensions for {name}")
    data = [values[i:i + 2] for i in range(2, len(values), 2)]
    for job in range(jobs):
        operations = data[job * machines:(job + 1) * machines]
        if sorted(machine for machine, _ in operations) != list(range(machines)):
            raise ValueError(f"Expected each machine once per job in {name}")
    if any(not 1 <= duration <= 100000 for _, duration in data):
        raise ValueError(f"Invalid duration for {name}")
    clock = 0
    witness = []
    for _, duration in data:
        witness.append(clock)
        clock += duration
    p = {
        "id": f"public_job_shop_{name}", "family": "job_shop", "kind": "native",
        "tier": "public", "split": "public", "seed": None,
        "label": f"public job_shop {name} ({jobs} jobs x {machines} machines)",
        "size": jobs, "machines": machines, "n": jobs * machines, "data": data,
        "incumbent": witness, "incumbent_objective": clock,
        "incumbent_method": "serial schedule in original job/operation order; no optimum used",
        "provenance": {
            "source": "Gecode 6.4.0 bundled examples/job-shop-instances.hpp",
            "source_url": SOURCE_URL, "source_array": name,
            "source_file_sha256": source_file_sha256,
            "source_array_sha256": array_sha,
            "source_array_hash_format": "SHA256 of compact JSON integer array including dimensions",
            "source_array_text_sha256": text_sha,
            "instance_origin": "Fisher and Thompson (1963)" if name == "ft06" else "Lawrence (1984)",
            "or_library_url": OR_LIBRARY, "license": "MIT notice in bundled Gecode source",
            "license_notice_file": "public-instances/NOTICE.txt",
            "source_arrays_modified": False,
        },
    }
    checked = native.validate_assignment(p, witness)
    if not checked["valid"] or checked["objective"] != clock:
        raise AssertionError(f"Invalid serial witness for {name}: {checked}")
    optimum = VERIFIED[name][0]
    if clock < optimum:
        raise AssertionError(f"Serial schedule contradicts published optimum for {name}")
    p["construction_ms"] = (time.perf_counter() - started) * 1000
    p["reference"] = {
        "status": "optimal", "objective": optimum,
        "input_sha256": native.mathematical_hash(p),
        "method": "published minimum makespan; not recomputed by this importer",
        "source_url": FT_REFERENCE if name == "ft06" else LAWRENCE_REFERENCE,
        "source_checked_date": "2026-09-04",
        "evidence": "published matching lower/upper bounds (55/55)" if name == "ft06"
                    else "researcher table of minimum makespans and minimum-makespan schedules",
        "used_for_solver_initialization": False,
    }
    return p


def generate(source_path=SOURCE, names=None, output=HERE):
    source_path, output = Path(source_path), Path(output)
    names = list(VERIFIED) if names is None else list(names)
    if len(names) != len(set(names)):
        raise ValueError("Public instance names must be unique")
    source_bytes = source_path.read_bytes()
    source = source_bytes.decode()
    marker = source.find("namespace {")
    if marker < 0 or "Permission is hereby granted" not in source[:marker]:
        raise ValueError("Bundled source MIT notice not found")
    instances = [make(source, name, sha256(source_bytes)) for name in names]
    directory = output / "public-instances"
    directory.mkdir(parents=True, exist_ok=True)
    notice = ("The public job-shop data in this directory were extracted unchanged from\n"
              "Gecode's examples/job-shop-instances.hpp. The source file carries the\n"
              "following complete copyright and permission notice.\n\n" + source[:marker].strip() + "\n")
    (directory / "NOTICE.txt").write_text(notice)
    records = []
    for p in instances:
        stem = directory / p["id"]
        stem.with_suffix(".json").write_text(json.dumps(p, indent=2) + "\n")
        flat = [value for operation in p["data"] for value in operation]
        encoded = (f"job_shop {p['size']} {p['machines']} {len(p['data'])}\n"
                   + " ".join(map(str, flat)) + "\n"
                   + " ".join(map(str, p["incumbent"])) + "\n")
        stem.with_suffix(".txt").write_text(encoded)
        records.append({key: p[key] for key in ("id", "family", "tier", "split", "seed", "label", "kind")}
                       | {"json": str(stem.with_suffix(".json").relative_to(output)),
                          "txt": str(stem.with_suffix(".txt").relative_to(output))})
    manifest = {"schema_version": 1, "instances": records,
                "note": "Public holdout instances: never development/training input. Optima are validation metadata only.",
                "license_notice": "public-instances/NOTICE.txt"}
    (output / "public-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return instances


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--names", nargs="+", choices=list(VERIFIED), default=list(VERIFIED))
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    instances = generate(args.source, args.names, args.output)
    print(f"Imported {len(instances)} hash-pinned public job-shop instances; no optimizer called")


if __name__ == "__main__":
    main()
