#!/usr/bin/env python3
"""Correctness-only CLI checks; reported elapsed times are deliberately ignored."""
import argparse
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lp", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path)
    args = parser.parse_args()
    lp, native = args.lp.resolve(), args.native.resolve()
    rng = random.Random(291125)
    cases = [
        ([1, 1, 1], [(0, 3)] * 3, [(3, [1, 1, 0]), (3, [0, 1, 1]), (3, [1, 0, 1])]),
        ([-1, -1, -1], [(-3, 1)] * 3, [(1, [-1, -1, 0]), (1, [0, -1, -1]), (1, [-1, 0, -1])]),
        ([-3, 2], [(-2, 2), (-3, 1)], []),
        ([0, 1], [(-1, 1), (-2, 2)], [(1, [0, 0])]),
        ([2, -3], [(-2, -2), (3, 3)], [(-5, [1, -1])]),
    ]
    for _ in range(5):
        costs = [rng.randrange(-4, 5) for _ in range(3)]
        domains = [(lo, lo + rng.randrange(1, 4)) for lo in [rng.randrange(-3, 1) for _ in range(3)]]
        rows = [(rng.randrange(-5, 6), [rng.randrange(-3, 4) for _ in range(3)]) for _ in range(3)]
        cases.append((costs, domains, rows))

    def feasible(costs, domains, rows):
        return [(sum(c * v for c, v in zip(costs, x)), x)
                for x in itertools.product(*(range(lo, hi + 1) for lo, hi in domains))
                if all(sum(a * v for a, v in zip(row, x)) >= rhs for rhs, row in rows)]

    def serialize(costs, domains, rows, witness, integer):
        text = [f"{len(costs)} {len(rows)}", " ".join(map(str, costs))]
        if integer:
            text.append("bounds " + " ".join(f"{lo} {hi}" for lo, hi in domains))
        for rhs, row in rows:
            terms = [(j, a) for j, a in enumerate(row) if a]
            text.append(f"{rhs} {len(terms)} " + " ".join(f"{j} {a}" for j, a in terms))
        text.append("incumbent 0" if witness is None else "incumbent 1 " + " ".join(map(str, witness)))
        return "\n".join(text) + "\n"

    runs = 0
    with tempfile.TemporaryDirectory(prefix="gecode-integer-lp-") as directory:
        path = Path(directory) / "model.txt"
        for index, (costs, domains, rows) in enumerate(cases):
            witnesses = feasible(costs, domains, rows)
            optimum = min((cost for cost, _ in witnesses), default=None)
            # Deliberately use a feasible but usually suboptimal warm start.
            start = max(witnesses)[1] if witnesses else None
            path.write_text(serialize(costs, domains, rows, start, True))
            for executable, modes in [(native, ["none"]), (lp, ["none", "root", "node", "root-tight", "node-tight"])]:
                for mode, branch, warm in itertools.product(modes, ["size", "afc"], ["0", "1"]):
                    result = subprocess.run([str(executable), str(path), mode, branch, "10000", warm, "1", "--integer"],
                                            capture_output=True, text=True, timeout=20, check=True)
                    record = json.loads(result.stdout)
                    assert record["status"] == ("infeasible" if optimum is None else "optimal"), (index, mode, record)
                    assert record["objective"] == optimum and not record["stopped"], (index, mode, record)
                    assert record["matrix_storage"] == "csr" and record["variable_domain"] == "bounded-integer"
                    if optimum is not None:
                        assert (record["objective"], tuple(record["assignment"])) in witnesses
                    runs += 1

        # The existing binary default and opt-in CSR inputs still have identical semantics.
        costs, domains, rows = [1, 1, 1], [(0, 1)] * 3, [(1, [1, 1, 0]), (1, [0, 1, 1]), (1, [1, 0, 1])]
        path.write_text(serialize(costs, domains, rows, (1, 1, 1), False))
        for executable, modes in [(native, ["none"]), (lp, ["none", "root", "node"])]:
            for mode, flag in itertools.product(modes, [[], ["--sparse"]]):
                record = json.loads(subprocess.run([str(executable), str(path), mode, "size", "10000", "1", "1"] + flag,
                                                   capture_output=True, text=True, timeout=20, check=True).stdout)
                assert record["status"] == "optimal" and record["objective"] == 2
                assert record["variable_domain"] == "binary"
                runs += 1

        # Never silently interpret unsupported fractional/infinite/malformed input.
        good = serialize([1], [(-2, 2)], [], None, True)
        invalid = [good.replace("bounds -2 2", "bounds -2 2.5"),
                   good.replace("bounds -2 2", "bounds -2 inf"),
                   good.replace("bounds -2 2", "bounds 3 2"),
                   good.replace("bounds -2 2", "bounds -2 2147483648"),
                   good.replace("\n1\nbounds", "\n1000000000\nbounds"),
                   good.replace("incumbent 0", "incumbent 1 3"),
                   good.replace("incumbent 0", "incumbent 1 1.5"),
                   good + "ignored mathematical content\n"]
        for bad in invalid:
            path.write_text(bad)
            result = subprocess.run([str(lp), str(path), "node", "size", "10000", "0", "1", "--integer"],
                                    capture_output=True, text=True, timeout=20)
            assert result.returncode != 0 and not result.stdout, (bad, result.stdout, result.stderr)
    print(f"PASS {runs} integer/native/LP and binary compatibility CLI oracle checks; {len(invalid)} invalid input rejections (timings ignored)")


if __name__ == "__main__":
    main()
