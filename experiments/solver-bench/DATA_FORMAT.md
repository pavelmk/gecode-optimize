# Broad binary-linear benchmark suite

This suite contains **18 domain families**, each with two size tiers, three
development seeds per tier, and five held-out seeds per tier. That gives **288
benchmark cases**, plus **12 tiny controls**, for 300 saved instances. Every case
has a feasible constructive or greedy incumbent. No instance was selected or
removed based on solver performance.

`small` and `large` describe dimensions, not measured difficulty. Some large cases
may be easy, some small cases may time out, and LP relaxations need not help every
family. Auction and set packing share mathematical structure; these 18 labels are
domain/model families, not 18 unrelated complexity classes.

## Shared mathematical and file format

Every solver receives exactly the same binary linear model:

```text
minimize c*x
subject to a_r*x >= b_r for every row r
x_j in {0,1}
```

JSON contains `id`, `family`, `tier`, `split`, `seed`, `n`, `c`, `rows`,
`parameters`, `incumbent`, `incumbent_objective`, `incumbent_method`, `reference`,
and `generation_timing`. Sparse rows are represented by:

```json
{"a": [[0, 2], [4, -3]], "b": -1}
```

Variable indices are zero-based, unique and sorted within a row. Coefficients
are nonzero integers. Objective coefficients and right-hand sides may be negative.
Equalities are encoded as two inequalities. Duplicate/redundant rows are allowed.

The companion TXT is the same format as the LP-relaxation experiment:

```text
n number_of_rows
c0 c1 ... c(n-1)
b0 nnz0 j0 a0 j1 a1 ...
... one line per row ...
incumbent 1
x0 x1 ... x(n-1)
```

A general external input may instead end with `incumbent 0` and no bits. This
generated suite always supplies a feasible incumbent. The TXT omits reference
optima and construction metadata.

`manifest.json` lists every JSON/TXT pair, its mathematical input hash, dimensions,
split, family, tier, reference status and generation timing. Consume it only when
`generation_status` is `complete` and entries have `ready: true`. A manifest with
`in_progress` is a planning/progress artifact and may name files not yet written.

## Families, dimensions and original meanings

| Family | Small / large binary variables | Original feasibility and objective |
|---|---:|---|
| `set_cover` | 40 / 100 | Select sets covering each element at least once; minimize positive set costs. |
| `multicover` | 40 / 90 | Cover each element at least 2 / 3 times using distinct selected sets; minimize set costs. |
| `set_packing` | 40 / 100 | Select pairwise item-disjoint bundles; maximize profit, encoded as negative cost. |
| `knapsack` | 40 / 80 | Select items under one resource capacity; maximize profit. |
| `multidimensional_knapsack` | 40 / 80 | Select items under 3 / 5 simultaneous capacities; maximize profit. |
| `vertex_cover` | 40 / 100 | Select at least one endpoint per graph edge; minimize vertex weight. |
| `independent_set` | 40 / 100 | Select no two adjacent vertices; maximize selected weight. |
| `maxcut` | 44 / 114 | Vertex-side bits plus edge-cut bits; each cut bit equals endpoint XOR; maximize cut weight. |
| `facility_location` | 35 / 128 | Open facilities and assign each customer to exactly one open facility; minimize opening plus assignment cost. |
| `pmedian` | 35 / 128 | Open exactly 2 / 3 facilities and assign every customer; minimize assignment cost. |
| `assignment` | 36 / 144 | One-to-one worker/job assignment; minimize the cost matrix sum. |
| `generalized_assignment` | 36 / 140 | Assign every job to one machine, respecting machine-dependent resource capacities; minimize assignment cost. |
| `bin_packing` | 44 / 126 | Item/bin assignment bits plus bin-open bits; fit every item once within capacity; minimize open bins. |
| `coloring` | 36 / 126 | One-hot vertex colors plus enabled-color bits; adjacent vertices differ; minimize enabled colors. |
| `tsp` | 45 / 120 | One-hot city/position bits plus directed tour arcs; visit every city once and return to the start; minimize tour length. |
| `auction` | 40 / 120 | Choose compatible item bundles as winning bids; maximize bid value. |
| `rostering` | 40 / 144 | Employee/day/shift bits; cover shifts while respecting availability, workload and rest; minimize staffing cost. |
| `production` | 40 / 120 | Choose one production quantity per period, meet cumulative demand and storage bounds, end with zero inventory; minimize production plus holding cost. |

All maximization families minimize the negative of the stated profit/weight.
Knapsack `sum(w*x) <= capacity` becomes `sum(-w*x) >= -capacity`.

Layouts are explicit and also implemented independently in `validate.domain_check`:

- Facility and p-median: facility-open bits first, then customer-major assignment
  bits (`customer * facilities + facility`, offset by facility count).
- Assignment: worker-major square matrix. Generalized assignment: job-major
  machine choices.
- Bin packing: item-major bin choices, then bin-open bits. Enabled bins are
  constrained to form a prefix, a valid bin-label symmetry restriction.
- Coloring: vertex-major color choices, then enabled-color bits. Enabled colors
  form a prefix. Planted color classes guarantee feasibility but are not assumed
  to give the chromatic number.
- TSP: city-major position bits followed by the `parameters.arcs` order. City 0
  is fixed at position 0 to remove rotational symmetry. Arc implications, one
  outgoing/incoming arc per city, and the position assignment encode one complete
  tour; there is no missing subtour constraint.
- Maxcut: original vertex bits first, then one bit per `parameters.edges` entry.
  Four inequalities enforce XOR exactly.
- Rostering: index `(employee * days + day) * shifts + shift`. At most one shift
  per day, at least one employee per required shift, a total-workday cap, at most
  two workdays in any three-day window, no last-shift/next-first-shift pairing,
  and availability exclusions are all enforced.
- Production: period-major quantity choices, including quantity zero. Inventory
  is cumulative production minus cumulative demand. The linear objective differs
  from physical production-plus-holding cost by a fixed constant;
  `physical_cost = c*x + parameters.objective_constant`. This offset does not
  affect the optimum and is checked independently.

The original parameter arrays are retained so validators can check the domain
meaning directly, independently of the generated sparse coefficient lists.

## Incumbents and timing accounting

Witnesses use ordinary deterministic rules: coverage greedy, profit/resource
greedy, independent-set degree greedy, single-vertex maxcut improvement, greedy
facility opening, cheapest remaining assignment, planted feasible job allocation
with a local reassignment pass, first-fit decreasing, greedy coloring with planted
fallback, nearest-neighbor tour, cyclic roster, or just-in-time production.

The generalized-assignment capacities and roster availability are constructed
around feasible planted assignments. Bin capacity is increased if necessary to
admit its constructive packing. These are feasibility constructions, not searches
for instances on which a particular solver wins. Exact references are computed
only after the incumbent is fixed and never feed it.

`generation_timing` records:

- `construction_seconds`: random data, model coefficients and feasibility
  construction work;
- `incumbent_seconds`: the shared incumbent procedure;
- `reference_seconds`: optional independent oracle work;
- `total_seconds`: all case generation and validation work before serialization.

The manifest separately records total suite generation time, including tiny
encoding checks. Timings vary across runs; mathematical inputs and witnesses use
fixed local `random.Random(seed)` streams. Timing fields should never be included
in mathematical identity checks. Both baseline and enhanced solvers get the same
incumbent in the primary experiment. Any no-incumbent comparison must disable it
for both.

If a driver searches only for `cost < incumbent_objective`, exhausting that search
proves the original optimum equals the retained incumbent. Report an optimal
original solution and its witness, not original-instance infeasibility.

## Independent references and encoding checks

The initial suite has **119 exact references and 181 explicitly unknown references**.
Available inexpensive oracles are complete binary enumeration for tiny inputs,
one-dimensional knapsack DP, assignment subset DP, enumeration of facility
subsets, Held-Karp TSP DP, production inventory DP, and a matching capacity lower
bound for some bin-packing instances. These run without Gecode or an LP/MIP solver.
No incumbent objective is relabeled an optimum merely because it is feasible.

All 18 templates have separate tiny models whose **every binary assignment** is
checked for equivalence between sparse linear feasibility and independently
written domain semantics, including the stated symmetry restrictions. Feasible
assignment objectives must match as well. Results and assignment counts are
stored in `manifest.encoding_checks`. These in-memory checks cover all 18 families;
12 additional tiny files are saved as harness controls so the suite stays at 300.

An unknown reference does not make a model invalid. It means an optimality claim
requires later evidence, such as a completed independent exact solver, an exact
small-instance oracle, or a checked certificate. Agreement between two heuristic
incumbents alone is not an optimality proof.

Reference hashes cover canonical compact JSON of exactly `n`, `c`, and `rows`.
The validator rejects a stale reference. External exact references can be passed
as a separate object with `status`, `objective`, `input_sha256`, and preferably an
assignment plus provenance. These are algorithmic references, not formal proof
logs by themselves.

## Commands and API

```sh
python3 generator.py
python3 generator.py --out-dir alternate-suite --dev-seeds 3 --test-seeds 5
python3 validate.py instance.json result.json
python3 validate.py instance.json result.json --reference independent-reference.json
python3 validate.py tiny-instance.json --enumerate
python3 validate.py instance.json --certify
```

`--no-references` leaves medium references unknown. `--skip-encoding-checks` is
available for explicitly requested generation-only runs; the delivered default
suite ran the checks. Alternate data should go in a separate directory. Generation
does not delete older files; select through the manifest, not a wildcard.

Useful imports, with no dependency on another experiment directory:

```python
from validate import validate_assignment, validate_result, input_hash, exact_reference
from generator import to_text
```

Solver statuses are `optimal`, `feasible`, `infeasible`, or `unknown`. Assignments
contain `n` binary integers, excluding Python booleans. Reported objectives are
recomputed. `valid` covers mathematical/domain feasibility and data consistency;
`optimality_verified` and `claims_verified` separately identify established
claims. A feasible incumbent can be valid while its optimality remains unknown.
An infeasible status is rejected for every delivered case because each has a
known feasible witness.

Freeze implementation and heuristic choices after development experiments, then
retain all held-out cases, including timeouts and regressions. The fixed seed
scheme gives five held-out seeds per family and size tier without overlap with
the three development seeds.
