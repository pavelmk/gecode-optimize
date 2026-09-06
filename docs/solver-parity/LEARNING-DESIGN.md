# W10 explanation and learning architecture

Status: source/interface investigation and an independently checked protocol
experiment. No production learning solver, Gecode explanation hook or learning
default is implemented by this slice. The eighth integrated checkpoint remains
the last completed product gate.

## Decision and evidence

Develop a checked, solver-independent integer-row reason kernel before selecting
the search architecture. Compare a reason-aware clone/recompute path with a
private trailed propagation engine controlled by a maintained SAT solver. Keep
existing Space, Propagator, variable and search layouts unchanged during this
comparison. The current ordinary/native solver routes remain available for
models outside the explanation pilot.

Local code supports this separation. `gecode/kernel/core.hpp` declares
`Propagator::propagate` as an execution-status operation, without a reason
history for each domain update. `gecode/search/nogoods.hh` implements path
nogoods; `gecode/search/seq/path.hpp` manages cloned Spaces and Choices for
recomputation. These mechanisms alone do not explain arbitrary propagation.
The existing exact integer presolve arithmetic is a useful reference, but its
change records omit the antecedent box needed for reusable conditional reasons.

The foundational CP-controlled design uses linked integer and Boolean views;
its experiments also show that encoding and search choices affect learning's
benefit. That motivates a matched comparison rather than an implicit switch of
every Gecode model. [Feydy and Stuckey, CP 2009](https://people.eng.unimelb.edu.au/pstuckey/papers/cp09-lc.pdf).

A recent modular architecture places SAT in control and reports integer-domain
assignments/backtracks through external propagation. Its interface restriction
on introducing literals while explaining deductions favors storing complete
reasons eagerly in our first pilot. [Dekker et al., CP 2025](https://doi.org/10.4230/LIPIcs.CP.2025.42).

Trail-only explanations, historical explanation reconstruction and proof logging
have different requirements. A learned clause is not by itself an independently
checked proof of the original CP problem. Vocabulary and explanation cost must
be measured as well as node reduction. [Ohrimenko, Stuckey and Codish, 2026](https://doi.org/10.1007/s10601-026-09390-9).

## Pinned external-propagation experiment

The candidate library is CaDiCaL 3.0.1, MIT, commit
`c60730422e758ef1cebe7aeddf2dda31c996bf04`. It is a separate workspace dependency,
not linked into Gecode, packaged, downloaded at build time or selected by Auto.
The public header's version macros lag its VERSION/build header; the experiment
checks the exact source commit. See `tools/research/cadical-dependency.json`.
[Pinned upstream source](https://github.com/arminbiere/cadical/tree/c60730422e758ef1cebe7aeddf2dda31c996bf04),
[IPASIR-UP paper](https://doi.org/10.4230/LIPIcs.SAT.2023.8).

The audited paths are `src/cadical.hpp`, `src/external_propagate.cpp`,
`src/external.cpp`, `src/solver.cpp` and the upstream
`test/api/example_propagators.cpp`. The latter is explicitly a demonstration
with simplified behavior and documented pitfalls, not a performance benchmark.
The API and callback implementation establish the following obligations:

| Contract | Pilot requirement |
| --- | --- |
| Connect one propagator, then observe its variables | Explicit ownership and destruction ordering; disconnect before releasing reason storage |
| Variables can also be introduced internally by the solver | Use explicit variable declaration and retain the returned mapping; never guess the next ID |
| Assignment notifications may be batched | Maintain a level-aware assignment trail; preserve root assignments across backtracks |
| Reasons can be requested later | Store immutable clauses while their deductions are live; no fresh literals during explanation |
| Reasons contain the propagated literal and only observed variables | Check IDs, sign, terminator and consequence before exposing a stream |
| External clauses are trusted as input by SAT | Independently validate row/domain derivations before any clause can prune |
| A rejected complete model requires a clause or new observed variables | Always provide a checked explanation; never repeatedly reject without progress |
| Empty/root-falsified clauses establish UNSAT | Missing explanation, cancellation and allocation failure must never become an empty clause |
| API contract violations can abort the process | Check all states before calls; contain C++ exceptions inside production callbacks and discard results after errors |
| Reason forgettability is configurable | Set it explicitly: comments disagree, while the implementation reads `are_reasons_forgettable` |

`tools/research/cadical_protocol.cpp` is an independent bounded fixture for
signed at-most-k constraints plus ordinary CNF. It enumerates every assignment
of the original external constraint before emitting each lemma. An independent
enumerator checks SAT/UNSAT and returned witnesses for every query. The same
solver handles all 81 partial assignments of four variables twice, in opposite
orders, across three sign patterns, five cardinalities, three CNF sets, eager
and model-check-only propagation, and two chronological-backtracking settings.
It also interrupts and resumes a fresh eight-variable solve.

The fixture uses fixed-capacity callback records with assertions and no callback
allocation. It is not a reusable production bridge and does not establish
exception/allocation-failure containment for such a bridge. Its counters
distinguish supplied propagations, streamed reasons, checked lemmas and rejected
complete models. A level drop greater than one includes query resets, so that
counter is not evidence that every such event is a learned conflict backjump.
The delayed-reason counter measures intervening notification/decision events,
not elapsed time or an assertion that a reason crossed a backtrack.

Build this experiment separately after explicitly building the pinned library:

```sh
cmake -S tools/research -B build/w10-protocol \
  -DGECODE_LCG_CADICAL_SOURCE="$(cd ../deps/CaDiCaL-3.0.1 && pwd)" \
  -DGECODE_LCG_CADICAL_LIBRARY="$(cd ../deps/CaDiCaL-3.0.1/build-optimize-spike && pwd)/libcadical.a"
cmake --build build/w10-protocol -j2
ctest --test-dir build/w10-protocol --output-on-failure
```

The configure records source-header and supplied-library SHA-256 values. A
prebuilt library hash identifies the bytes but does not prove how they were
compiled; retain the dependency's configure/build logs as well. For sanitizer
validation, instrument the entire dependency and the fixture with matching
AddressSanitizer/UndefinedBehaviorSanitizer flags.

## First implementation boundary: checked conditional row reasons

Keep this boundary private until the architecture and budgets are reviewed. It
is an explanation utility, not a solve or a proof-certificate API.

1. Admission owns a historical `ModelSnapshot` and validates every original
   handle/reference. Admit finite Integer/Binary domains and ordinary linear
   rows with integral domain endpoints, coefficients and finite row sides of
   magnitude at most 2^53. Fractional bounds on Integer/Binary IR variables are
   unsupported in this slice. Reject active globals,
   indicators, continuous/semi domains and unsupported provenance. Unsupported
   constraints cannot be silently omitted when this becomes a search engine.
   Objective data has no role in this feasibility-reason utility; the eventual
   SAT pilot initially requires a constant objective.
2. Compile original row sides and domains once into checked int64 data. A
   successful compiled owner is immutable. Model/revision fields alone cannot
   authenticate a forged public snapshot, so reason checking retains that exact
   owner rather than reopening a live model with matching IDs.
3. Bound literals mean `x >= k` or `x <= k`, over original stable variable IDs.
   Complement uses checked integer arithmetic: `not(x <= k)` is `x >= k+1`.
   Root facts, decisions and deductions are distinct. A missing deduction reason
   is an error/unsupported case, never a root fact.
4. A row reason records its source owner, original row and finite side, immutable
   antecedent bound facts, and either a consequence or contradiction. Every
   antecedent is conditional: the source model plus those facts entails the
   consequence. Such a record does not assert that its antecedents hold globally.
5. Reconstruct the input box from original domains and explicit antecedent facts;
   never use an unexplained stronger input box. Generate implications from that
   unchanged box using signed row extrema
   and exact floor/ceiling division. Emit only strict tightenings; retain all
   relevant selected bound facts in the first implementation. Reason
   minimization comes later, after correctness and size measurements.
6. Independently verify each candidate by intersecting original domains with its
   antecedents and the negated consequence, then checking a contradiction with
   the named original row side. The checker does not trust cached activities,
   copied coefficients, an alleged deduction bound or generation intermediates.
   Check antecedent consistency before adding the negated consequence. Reject
   root-implied/redundant consequences whose complement alone contradicts a root
   domain, rather than accidentally attributing a domain tautology to a row.
   Reject malformed, inconsistent or irrelevant provenance rather than relying
   on accidental vacuity. Threshold complements at int64 MIN/MAX use checked
   rejection in this slice. Any later explicit RootFact tag must be checked
   against the frozen original domain before it can be omitted. Exact arithmetic
   overflow yields no accepted reason.
7. Bound construction, copying, traversal and output storage must be budgeted.
   Return a complete bounded batch or a clearly interrupted/rejected batch;
   no partially exposed unverified clauses. Counter increments, products, sums,
   subtraction and division all use checked operations without signed overflow.
8. Tiny finite-grid tests independently enumerate the original domains and row
   predicate. Corrupt owner, revision, side, bound, variable and antecedents;
   invalid claims must be rejected, while valid weaker reasons may remain valid.
   Include negative domains/coefficient signs, equality/ranged sides, constants,
   fixed variables, tombstones, exact-limit arithmetic and overflow rejection.

This kernel does not claim explanations for existing Gecode propagators. Later
constraints require their own valid reasons or a supported explained
decomposition, with an independent original-constraint predicate.

## Competing search integration experiments

| Question | Clone/recompute candidate | Trailed external-SAT candidate |
| --- | --- | --- |
| State | Reason-aware bounded propagators in cloned/replayed Spaces | Explicit integer domains and a reversible trail owned by one external propagator |
| Identity | Stable original IDs independent of Space/VarImp addresses | Stable original IDs mapped to explicitly declared SAT bound literals |
| Replay | Recompute consequences and check/reuse reasons under the replayed facts | Assignment/backtrack notifications restore domains and subscriptions |
| Clause handling | Requires a maintained clause engine and integration with replay/backjumping | SAT owns watched clauses, analysis, backtracking and database management |
| Coverage | Existing arbitrary propagators still lack reasons | Only explicitly supported explained constraints enter the pilot |
| Main risk | Reason ownership, clone size and replay overhead | Boolean encoding size, notification/history cost and loss of strong native globals |

Use the same admitted row models, branch order where controllable, and original
witness checker. Measure reason generation/storage, clones/replay or trail
updates, literal count, callback traffic, learned-clause reuse, first solution,
proof time and peak memory. Compare compiled-but-disabled overhead as well as
learning enabled. Boolean templates establish protocol correctness only;
bounded general-integer rows and at least one table and one scheduling family
are required before concluding that the architecture improves Gecode.

Fresh pilot solves own private learned state. Optimization follows satisfaction
only after cutoff literals, assumptions and clause scope are designed. Clauses
derived under an objective cutoff must be guarded; relaxing a cutoff or editing
a model cannot reuse those clauses unconditionally. Unknown/interrupted search
cannot become global UNSAT or optimality. A full proof route additionally needs
an original-constraint proof format and independent checker; the SAT library's
proof treating external lemmas as new inputs is insufficient.

## Remaining research and acceptance

- Pin and audit Chuffed and Huub source before describing source-level behavior.
  Their papers/README are evidence for candidate architecture, not a completed
  implementation audit. Huub's CP 2025 paper archives code as
  `swh:1:dir:b28854946ae60e86a37051ea89465cce8b84b7ed`.
- Examine CP-SAT's integer trail, reason storage, conditional bounds and
  scheduling explanations at a pinned release; record transferable contracts
  separately from performance claims.
- Freeze the reason utility's resource and failure semantics after independent
  review; implement it and its finite-grid checker before connecting it to SAT.
- Exercise delayed reasons, same-level and multi-level backtracking, restart,
  replay, assumptions, cancellation and destruction. Fault injection must show
  that a failed explanation cannot escape as a trusted clause.
- Compare the complete supported models with Chuffed/CP-SAT and unchanged native
  Gecode using identical inputs and shared limits. Report unavailable competitor
  binaries as missing evidence. Preserve a holdout by family and include
  learning-disabled regressions.
- Add a bounded representative case to FAST once an actual pilot exists. The
  standalone protocol fixture does not substitute for original-model solver
  correctness or a measurable native performance improvement.

W10 remains incomplete until the learned search, reason coverage, lifecycle,
original-model correctness and representative benefit gates are met.
