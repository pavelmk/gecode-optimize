# Expose native optimization strategies through MiniZinc

MiniZinc users can now select automatic, racing, ordinary or explicitly
configured native solving through the experimental Gecode Optimize registration.
The default remains structural automatic selection. Solver flags expose the
existing improvements without requiring C++ integration or search annotations.

MiniZinc often emits binary decisions as integer `0..1` variables and wraps a
linear objective in an auxiliary variable. Preserve the source types and checks
while recognizing those binary domains internally. Bounded automatic presolve
eliminates one safely defined affine objective auxiliary, preserves any
restrictive auxiliary bounds, and reconstructs/checks its original value. This
lets ordinary MiniZinc knapsack models reach the existing exact DP route.

## Changes

- Advertise 21 namespaced MiniZinc controls for automatic feature switches,
  racing allowances, checked LP frequency/tightening, root covers, search order,
  reliability probes, Hamming neighborhoods, resource caps and diagnostics.
- Add `NativeAutoSettings` / `solve_native_auto_configured` and race
  automatic-candidate settings. Disabled mechanisms remain disabled in reduced
  and independent component solves. Explicit settings reject incompatible modes
  or missing dependencies before solving.
- Dispatch every strategy with the remaining frontend time and shared solver
  node budget. Optional diagnostics distinguish requested settings from actual
  policy, LP/cut/probe activity, and neighborhood completion or skip reasons.
- Document supported combinations, executable examples and racing overhead.
  Sequential exploration/restarting can increase CPU work or solve time;
  several seconds or longer may find a much better strategy for a long solve.
- Track registration inputs in CMake so rebuilds update installed flags as well
  as build-tree flags; verify the installed relative registration in place.

The experimental native integer scope is unchanged. This does not add numerical
LP/MILP/QP MiniZinc model support, conflict learning or parallel racing. The
benchmark dashboard is outside this PR.

## Validation

All **75 CTest entries pass**, as do **135 real MiniZinc checks** against each of
the build registration, installed registration and a checked-LP-disabled harness.
Three backend-free native coordinator tests also pass.

See [the QA walkthrough](../../docs/solver-parity/MINIZINC-CONTROLS-QA.md) for
the actual MiniZinc 2.10.1 commands, independent objective/witness checks,
algorithm activity and regression results. Tests also cover strict flag
forwarding, zero/finite budgets, output/proof markers, original domain and
objective reconstruction, and unavailable checked LP.

## Review base

This is a separate incremental PR: `codex/minizinc-native-controls` targets
`codex/solver-parity-pr` (`884795c874174fd293bab554ee8a544fe45580c1`). That
prerequisite branch contains the earlier optimization contribution. Its tree
matches integration checkpoint `b11a57c1d`; the new branch is based directly on
the review commit so the comparison contains only this MiniZinc work.

The repository's configured remote is a local checkout. Publish the prerequisite
review branch and this branch to the chosen GitHub fork before opening the
stacked pull request. No remote PR or merge is implied by this local preparation.
