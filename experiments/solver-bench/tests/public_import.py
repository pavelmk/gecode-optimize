#!/usr/bin/env python3
"""Check public extraction, provenance, serial witnesses, and result validation."""
import copy
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native
import public_instances as public


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="gecode-public-import-") as temporary:
        output = Path(temporary)
        instances = public.generate(output=output)
        require(len(instances) == 6, "wrong number of public cases")
        manifest = json.loads((output / "public-manifest.json").read_text())
        require(len(manifest["instances"]) == 6, "incomplete public manifest")
        require("Permission is hereby granted" in (output / manifest["license_notice"]).read_text(),
                "source permission notice was not preserved")
        for p in instances:
            require(p["split"] == "public" and p["seed"] is None, "public case was classified as generated")
            require(p["reference"]["input_sha256"] == native.mathematical_hash(p), "stale imported reference")
            require(p["provenance"]["source_array_sha256"] == public.VERIFIED[p["provenance"]["source_array"]][1],
                    "source array hash mismatch")
            require(p["reference"]["objective"] == public.VERIFIED[p["provenance"]["source_array"]][0],
                    "wrong published optimum")
            result = {"status": "feasible", "assignment": p["incumbent"], "objective": p["incumbent_objective"]}
            checked = native.validate_result(p, result)
            require(checked["valid"] and checked["claims_verified"], "serial witness rejected")
            result["status"] = "optimal"
            require(not native.validate_result(p, result)["valid"], "serial schedule falsely certified optimal")
            encoded = list((output / "public-instances" / (p["id"] + ".txt")).read_text().split())
            require(encoded[0] == "job_shop", "wrong native family")
            numbers = list(map(int, encoded[1:]))
            require(numbers[:3] == [p["size"], p["machines"], p["n"]], "wrong job/machine dimensions")
            require(numbers[3:3 + 2 * p["n"]] == [v for row in p["data"] for v in row], "source data changed in encoding")
            require(numbers[3 + 2 * p["n"]:] == p["incumbent"], "serial witness changed in encoding")
            changed = copy.deepcopy(p)
            changed["data"][0][1] += 1
            require(not native.validate_result(changed, {"status": "unknown", "assignment": [], "objective": None})["valid"],
                    "stale reference accepted after input change")
        source = public.SOURCE.read_text()
        changed = source.replace("2, 1, 0, 3, 1, 6, 3, 7, 5, 3, 4, 6", "2, 2, 0, 3, 1, 6, 3, 7, 5, 3, 4, 6", 1)
        try:
            public.extract_array(changed, "ft06")
        except ValueError:
            pass
        else:
            raise AssertionError("modified public source accepted its old published optimum")
    print("PASS six public imports: source hashes, MIT notice, rectangular encoding, witnesses, stale references, optimum isolation")


if __name__ == "__main__":
    main()
