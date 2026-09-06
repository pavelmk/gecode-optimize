# Add optional optimization APIs and automatic native strategies

Add `Gecode::Optimize` for applications that need owning optimization models,
explicit result guarantees and reusable solve workflows. Native integer solving
now chooses suitable strengthening automatically. An opt-in race can compare
that policy with ordinary Gecode search before committing the remaining budget.
Existing Gecode modeling, propagation and search interfaces remain available.

## Changes

- Add sparse models, starts, LP/MPS exchange, sessions, ordered objectives,
  diagnostics, repair, pools, scenarios and documented C/Python bindings.
  HiGHS supplies numerical LP/MILP and bounded weighted-square continuous QP;
  the native bridge retains its exact integer subset and supported globals.
- Add checked LP deductions, verified cover cuts, frontier search, reliability
  branching and bounded binary neighborhoods. Structural native selection uses
  compatible mechanisms without problem-family labels or reference objectives.
- Compose bounded exact presolve, independent components and symmetry constraints
  for identical columns. Restore original coordinates and objective offsets;
  incomplete component solutions never become full-model incumbents or proofs.
- Strengthen eligible binary knapsack models with exact DP, rolling value rows
  and packed traceback. Separate work, memory and local time caps provide a
  fallback to native search, with independently checked original witnesses.
- Add `NativeRaceOptions` and `solve_native_race` in C++. Two bounded sequential
  probes compare the automatic policy and ordinary BAB. Selection uses validated
  incumbents and valid bounds; the chosen strategy restarts under the same global
  time, node and cancellation budget. Keep the best original incumbent and bound
  even if restarting makes no progress.

Racing is opt-in: the ordinary automatic dispatcher does not silently enable it.
Exploration and restarting can increase total CPU work or solve time. Configurable
trials of several seconds or longer may pay off by finding a much better strategy
for the remaining solve. Early progress is a heuristic, not a speedup guarantee.
The new racing option is not exposed through MiniZinc/FlatZinc yet. No conflict
learning or parallel racing is added.

## Validation and measured limits

The complete isolated Release build passes **75/75 CTest entries**, including
FAST. Focused racing checks also pass without checked LP and without native
backends. Exhaustive min/max oracle checks cover strategy selection, shared node
limits, retained exact results, starts and interruption. Generator checks preserve
every historical input's JSON and text bytes and independently validate larger
feasible witnesses. Earlier sanitizer validation remains separately documented;
this racing change does not claim a new sanitizer run.

The [final benchmark](../../docs/solver-parity/FINAL-BENCHMARK.md) compares the
preserved pre-algorithm Gecode runtime, current automatic racing and frozen
family presets. Ten seconds includes all exploration and restarting. Each
configuration expands until an observed failed upper size, then refines the
bracket to adjacent sizes or approximately 2% for larger inputs. Both repetitions
and every knapsack variant must pass at the reported lower size. All initial
observations remain in the amended, uncapped study.

These are seeded-instance brackets, not mathematical maximum-size guarantees.
Original witnesses are independently checked; large-instance exact optimality is
backend-reported. The same families informed development and preset selection.
The comparison measures combined policies, not an ablation establishing that
racing alone caused the gains. Historical studies remain separate.

General MIQP/QCP/nonlinear optimization and production learning remain outside
scope. Remote platform CI and a rebuild of the older wheel are still pending.

## Review base

Compare `codex/solver-parity-pr` with `codex/solver-parity-base` (`e10562fd9`), the
preserved pre-project source snapshot. The review branch contains the same final
tree as `codex/solver-parity` in one commit over that base. The prerequisite base
must be available in the target repository before opening the upstream PR.
