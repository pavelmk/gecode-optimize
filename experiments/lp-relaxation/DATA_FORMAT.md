# Binary linear instances and independent validation

All models minimize `c*x` subject to sparse rows `a*x >= b`, with every variable
binary. Python generation and exact reference algorithms use only the standard
library; they never call Gecode or an LP solver.

The default suite has **52 instances**: four development and four held-out
instances for each of three families, eight tiny cases per family, and four
controls. All 48 random seeds are distinct across family and split. The four
controls are fixed constructions. Variable and row sizes describe construction;
they do not promise a particular runtime or performance gain.

## Families

- **Weighted set cover:** 32–44 binary set choices, 14–20 required elements;
  unit positive coefficients, row right-hand sides 1, positive costs. Two tiny
  cases use requirement 2 to exercise multicover. Medium exact optima use a
  dynamic program over remaining uncovered-element subsets. Tiny multicover
  references use complete binary enumeration.
- **Two-resource zero-one knapsack:** 28–40 item choices. Profits become negative
  objective coefficients; each capacity `sum(w*x) <= capacity` becomes
  `sum(-w*x) >= -capacity`. Exact references use descending two-capacity dynamic
  programming with assignment witnesses.
- **Weighted bipartite vertex cover:** 26–38 vertices, shuffled variable IDs,
  positive costs, one row `x_u+x_v >= 1` per edge. Exact references infer a
  bipartition from the original rows and compute an integral-capacity minimum
  cut. This family's LP relaxation is integral, making it a mechanism-focused
  example where a joint objective bound can be especially useful.

Controls include four disjoint triangles (fractional LP optimum 6 versus integer
optimum 8), no-constraint nonnegative costs, a direct infeasible binary bound,
and an unconstrained signed objective. They expose integrality gaps, overhead,
infeasibility, and negative-coefficient handling.

## Input format

Each manifest record names a JSON file and a TXT input. JSON includes mathematical
data, generation metadata, a greedy incumbent where feasible, and an independently
computed exact reference. TXT contains no optimum reference.

```text
n number_of_rows
c0 c1 ... c(n-1)
b0 nnz0 variable_index coefficient variable_index coefficient ...
b1 nnz1 variable_index coefficient variable_index coefficient ...
... remaining rows ...
incumbent 1
x0 x1 ... x(n-1)
```

The incumbent trailer is `incumbent 0` with no assignment for an infeasible
control. Indices are zero-based, unique and increasing within a row. Coefficients
are nonzero integers; right-hand sides and objective coefficients can be negative.
An empty row has `nnz=0`. The JSON representation is:

```json
{
  "n": 3,
  "c": [2, 3, 4],
  "rows": [{"a": [[0, 1], [2, 1]], "b": 1}],
  "incumbent": [1, 0, 0]
}
```

## Warm starts and fair comparison

Cover incumbents use cost per newly covered row, followed by removal of redundant
selected columns. Knapsack incumbents use profit per normalized resource load.
These procedures run **before** exact reference computation and never inspect
an optimum. Both baseline and LP-enabled drivers must receive the same incumbent.
An optional no-incumbent comparison should disable it for both drivers.

Some deterministic greedy incumbents already attain the optimum: 6/8 medium set
covers, 1/8 knapsacks, and 4/8 bipartite covers in the default generated suite.
These cases measure proof effort. No case was selected or removed based on whether
its greedy solution is optimal. `incumbent_matches_optimum` is descriptive
validation metadata populated only after the reference is computed.

If a driver posts `cost < incumbent_cost` to search for improvement, exhausting
that restricted search proves the *original* instance optimal with the saved
incumbent. It must report that optimum and witness, rather than report the original
feasible instance as infeasible.

## Generation and exact references

```sh
python3 generator.py
python3 generator.py --out-dir alternate-data --scale 1.5 --stress-per-family 2
python3 validate.py instances/test_knapsack_710000.json --certify
python3 validate.py instances/tiny_knapsack_510000.json --exhaustive
```

Counts, scale, set-cover density, bipartite density, capacity ratio and oracle
budgets are configurable. Larger stress cases use a separate split and are
excluded by default. Do not overwrite the main data after timing begins. Alternate
data should go in a separate directory. Generation does not delete older files;
always select instances through `manifest.json`, not a wildcard.

Every default reference completes. Specialized tiny algorithms are compared
against exhaustive enumeration: 22 independent comparisons. The other two tiny
multicover references already use enumeration. Every reference witness is checked
against the original sparse rows, and objective values are recomputed. Reference
hashes cover canonical compact JSON of exactly `n`, `c`, and `rows`, preventing
reuse after mathematical input changes. The exact oracle results are independent
algorithmic references, not formal proof logs.

## Result validation

```json
{"status":"optimal","objective":-514,"assignment":[0,1,0,1]}
```

Supply exactly `n` assignment entries; the short example above is schematic.
Statuses are `feasible`, `optimal`, `infeasible`, or `unknown`. A timed-out result
may include its best assignment, which is still validated. An infeasible result
must not contain an assignment.

```sh
python3 validate.py instance.json result.json
```

`validate_assignment(instance, assignment)` checks binary domains, every original
constraint and the objective. `validate_result(instance, result)` additionally
checks the reference hash and optimality/infeasibility claims. `valid` describes
data and feasibility checks; `claims_verified` separately records independent
verification of the claimed status. False optimality, wrong objective values and
stale references are rejected. Non-optimal feasible incumbents remain valid.

Oracle state counts are not solver search nodes and should not enter solver
timing comparisons. Freeze implementation and heuristic choices after development
runs, then retain every held-out instance, including regressions and timeouts.
