# Persistent solve sessions

`SolveSession` owns a HiGHS instance across calls and supports numerical LP/MILP
reoptimization. `Backend::Auto` within a session selects HiGHS; active globals
are unsupported there. The one-shot `solve` uses the same numerical pipeline
for linear models, and routes active native globals to the native compiler.

```cpp
#include <gecode/optimize.hh>
namespace O = Gecode::Optimize;
O::Model model;
auto x = model.add_continuous(0, 100);
auto demand = model.add_row({{x, 1}}, 4, 100);
model.minimize({{x, 2}}, -3);
O::SolveSession session;
auto before = session.solve(model);  // objective 5
model.set_bounds(demand, 8, 100);
auto after = session.solve(model);   // objective 13, compatible LP basis retained
auto statistics = session.statistics();
```

Every call validates the original snapshot, compiles it, and compares actual
content. A caller cannot bypass invalidation by editing a public snapshot
without incrementing its revision. Model identity, active variable/row slots,
original variable types and the sparse matrix determine compatibility. Changes
to any of those reload the backend. Compatible column bounds, row sides,
objective costs, sense and offset changes use HiGHS update methods. Pure naming
changes have no mathematical effect and leave the backend names internal.

LP updates retain the available basis; HiGHS decides how to use it. MIP search
trees and cuts are discarded on every call. A previous MIP incumbent is a hint
only after the independent validator checks it against the new original model,
including its logical indicators. An explicit user start takes precedence.
Changing model identity or structure discards the old hint. Limits never make
an invalid old assignment a feasible incumbent.

Each call receives a fresh monotonic budget. Backend timers, optional node
limits, gaps, tolerances and seed are set for that call. Callbacks are detached
on normal completion and exception paths, before their local data is destroyed.
Invalid conversion or backend/numerical failure discards cached backend state;
invalid options rejected before conversion leave it unused. Budget expiry before
conversion likewise does not run the cached model. Deadline/cancellation checks
remain cooperative and may overrun inside backend calls.

Statistics distinguish successful model loads, compatible updates, unchanged
models, runs entered with a valid retained LP basis, and submitted revalidated
MIP hints. A retained basis or submitted hint is not a claim of a speedup.
`reset()` discards state and counters. Moving transfers ownership; a moved-from
session rejects solves until reset. Historical `SolveResult` values remain valid
after either operation. Concurrent use of one session is not supported;
independent sessions have separate model state and use one HiGHS worker each.

Persistent native Gecode sessions, basis import/export, LP sensitivity/dual
records, action callbacks, interrupted MIP-tree reuse and mixed worker counts
are still unsupported. Set `SolveOptions::backend = Backend::Native` for the explicit native
one-shot bridge described in [NATIVE.md](NATIVE.md).

`test/optimize/session.cpp` compares edited sessions with cold solves, checks
seeded bounded-integer edits against exhaustive enumeration, and covers type,
matrix and identity changes, tombstones, historical results, infeasible and
unbounded revisions, malformed input, start precedence, moving and reset.
The complete sanitizer build instruments the adapter and HiGHS together.
