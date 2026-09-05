# Reproducible instances and independent validation

`generator.py` uses only Python's standard library. Each instance has its own
`random.Random(seed)`; generation order does not affect its random stream.
Version 1 defaults produce 62 instances: 6 development and 6 test cases for each
of 3 families, 8 tiny cases for each family, and 2 explicit controls. Tiny cases
and controls carry references computed by independent exhaustive enumeration.
Development, test, and tiny seeds are disjoint, including across families.

```sh
python3 generator.py
python3 generator.py --out-dir alternate-data --scale 1.5 --cover-density 0.2
python3 -m unittest test_validate.py
```

`--per-split`, `--tiny-per-family`, `--scale`, `--coloring-density`, and
`--cover-density` are adjustable. Generate alternate sizes in a separate output
directory: overwriting an existing suite does not remove older instance files.
Always select instances using that directory's `manifest.json`, not a glob.

The default medium sizes are 36–44 graph vertices for coloring, 20–24 jobs on
3–5 machines for scheduling, and 28–34 vertices for weighted vertex cover.
These are construction labels, not measurements of hardness or predicted gains.

## Solver input

Every manifest entry names a JSON metadata file and a whitespace TXT solver input.
Read only the TXT in the solver: JSON contains references for validation.
All indices are zero-based. The first token is the family name.

```
coloring n number_of_colors number_of_edges
u v
... one canonical undirected edge per line ...
```

```
scheduling n number_of_machines
d0 d1 ... d(n-1)
```

```
vertex_cover n number_of_edges
w0 w1 ... w(n-1)
u v
... one canonical undirected edge per line ...
```

Coloring seeks any feasible assignment of colors. Its reporting objective is 0.
Scheduling assigns each whole job to exactly one identical machine, minimizing
maximum total machine load. Weighted vertex cover minimizes selected vertex
weight subject to at least one selected endpoint per edge.

The JSON fields mirror the TXT (`family`, `n`, `colors`, `machines`, `durations`,
`weights`, `edges`) with `id`, `split`, `seed`, `label`, and optional validation
metadata. Only family-relevant mathematical fields are present.

## Solver result and validation

```json
{"status":"optimal","assignment":[0,1,0,1,1,0],"objective":17}
```

Statuses are `feasible`, `optimal`, `infeasible`, or `unknown`. Assignments contain
one integer per variable: color indices, machine indices, or 0/1 vertex selection
flags. `objective` is optional but checked if present. An unknown result can
omit its assignment, or include an incumbent that will be checked. Infeasible
results must not contain an assignment.

```sh
python3 validate.py instances/control_scheduling_local_minimum.json result.json
python3 validate.py instances/control_scheduling_local_minimum.json --brute-force
python3 validate.py instance.json result.json --brute-force --max-states 1000000
```

`validate_assignment(instance, assignment)` independently evaluates the original
constraints and recomputes the objective. `validate_result(instance, result)`
also checks claimed objectives and available exact references. A feasible result
is not proof of optimality: `valid` refers to checked data/feasibility, while
`claims_verified` reports whether an optimality or infeasibility claim has been
independently substantiated. `--require-verified-claims` exits with code 2 when a
claim remains unverified; invalid data exits with code 1. A scheduling solution
meeting `max(max_duration, ceil(total_duration / machines))` proves optimality.

Without an exact reference or verified certificate, a medium optimization
result's `optimal` status is trusted only as a solver report, not independently
proved by this validator. `--brute-force` recomputes small references instead of
reading stored ones; it returns `unknown` before enumeration when its budget
would be exceeded. Enumeration counts are not solver node counts or timings.

## Coloring construction

Each split includes ordinary planted graphs, planted overlapping cliques, an
overlarge-clique contradiction, and a three-color contradiction containing an
odd wheel (five-cycle plus a universal hub). The odd-wheel obstruction needs
four colors without containing a four-clique within that obstruction. Additional
mixed graph edges can create other obstructions. Planted color classes are
shuffled across vertex IDs before edge generation; this prevents vertex index
from directly revealing the planted color. Every planted clique contains one
vertex per color class, preserving a valid witness.

These explicit UNSAT constructions have short certificates and are controls,
not a representative sample of difficult infeasible coloring problems. The
validator checks the certificate edges directly. Freeze heuristic choices after
development measurements and before inspecting test timing results.
