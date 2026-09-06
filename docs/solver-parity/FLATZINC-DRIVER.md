# Explicit FlatZinc optimization frontend

`fzn-gecode-optimize` is built and installed when both native FlatZinc and the
Optimize component are enabled. It captures the whole input before compilation,
solves only a fully admitted model, and checks every original source relation
before publishing buffered output. The existing `fzn-gecode` executable and
MiniZinc solver configuration are unchanged.

```sh
fzn-gecode-optimize model.fzn --backend native --time-limit 10
fzn-gecode-optimize model.fzn --backend highs --node-limit 1000
fzn-gecode-optimize - --backend native < model.fzn
```

Native is the default and requests exact integer search. HiGHS is explicitly
numerical, requests zero absolute/relative MIP gaps, and prints that attribution
in a FlatZinc comment. Exact feasible-point checking does not certify a numerical
optimal bound or infeasibility claim. An unavailable selected backend fails
explicitly. There is no automatic backend or legacy-parser fallback.

See [the compiler](FLATZINC-COMPILER.md) for the admitted signatures and
[the capture layer](FLATZINC-CAPTURE.md) for grammar and lifecycle boundaries.
Unknown predicates, search annotations, unsupported domains and output types
prevent the entire solve. All-solution, intermediate-output, fixed-search and
other unimplemented flags are rejected. No `.msc` advertises this experimental
subset as a general MiniZinc solver.

Output and exit status:

- A checked satisfaction point prints assignments and `----------`, with no
  enumeration-completion marker. A completed optimization also prints
  `==========`; an exact route requires a matching objective/bound.
- Definite infeasibility prints `=====UNSATISFIABLE=====` only when no complete
  raw backend assignment independently establishes source feasibility.
- Interrupted solves may print a checked incumbent without a completion marker;
  without a point they print `=====UNKNOWN=====`. Exit status is 1.
- Completed results exit 0. Invalid input, unsupported features, malformed
  backend results and operational errors exit 2 with an explanation on stderr
  and no solution text. A claimed unbounded result is inconsistent with this
  finite discrete subset and is an error, never an UNSAT result.
- Optional bounds/gaps must be finite, ordered and internally consistent.
  Every published solution must have the correct model identity, revision,
  complete variable mask and original objective. Source output aliases retain
  their names and repeated positions; hidden variables are checked too.

`--time-limit` covers input reading, capture, compilation, solving and output
formatting through one outer elapsed-time calculation. Each next stage receives
only the remaining time, and a point newly returned after that deadline is
excluded. These are cooperative checks: stream reads, parser actions and some
backend calls may overrun before returning. This is not process containment or
a hard wall-clock deadline. The external FAST harness retains its own process
containment. Time 0 returns UNKNOWN before parsing. `--node-limit` is passed to
the selected solver and does not count parsing or compilation operations.

Input defaults to the capture limit of 16 MiB; `--max-input-bytes` can lower or
raise it within the parser's signed index range. Other capture/compiler resource
limits use their documented defaults. No signal-handler cancellation or arbitrary
memory-allocation recovery guarantee is added by this CLI.

The C++ driver test links the real capture/compiler and uses both real backends
when available. Its independent fake backend exercises contradictory status,
wrong identity/mask, invalid raw/claimed witnesses, absent or invalid bounds,
inconsistent gaps, unsupported routes, argument errors and exhausted budgets.
Subprocess tests separately check the actual file/stdin executable and output
contract. Legacy parser compatibility remains a separate regression gate.
