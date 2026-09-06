# Numerical LP/MPS I/O

`read_model` and `write_model` implement a bounded, documented linear LP/free-MPS dialect. They do not use the HiGHS parser or writer and are available in builds without that backend. They preserve the numerical `double` model; they do not provide exact rational parsing, proof certificates, or support for every vendor extension.

The reason for a separate implementation is semantic correctness. The pinned HiGHS 1.15.1 sources have several relevant paths:

- `highs/io/HMPSIO.cpp` writes numerical values using `%.15g`, which can merge distinct `double` values.
- `highs/io/FilereaderLp.cpp` assigns objective coefficients by variable index; repeated LP objective terms from `filereaderlp/reader.cpp` can overwrite instead of add.
- The LP expression parser records constants on constraint left sides, while the adapter copies its constraint bounds without subtracting those constants.
- LP export can omit zero-cost, otherwise unused columns and lose semi-integer declarations.
- MPS `BV` establishes both binary bounds. The free-MPS parser ignores following `LO`/`UP` records as duplicates, so that encoding cannot portably express tighter binary domains.

These findings motivated replacement, rather than a claim that a successful backend import proves faithful conversion. No dependency source was changed.

## Import contract

Only uncompressed `.lp` and `.mps` suffixes are accepted, case-insensitively. Unknown formats, unreadable files, malformed records, NaN, coefficient infinities, numeric overflow/underflow and unsupported constructs produce `ModelError`. Tiny nonzero coefficients are preserved here; the numerical solving adapter can subsequently reject unsupported magnitudes explicitly.

Names in the supported external dialect are identifiers beginning with an ASCII letter or underscore and continuing with letters, digits or underscores. Fixed-column files using ordinary whitespace-separated identifiers are supported; names containing embedded spaces, quoted names, omitted repeated column names and SIF extensions are outside this initial dialect. The five unchanged local MIPLIB 3.0 files `p0033`, `lseu`, `p0201`, `p0282` and `p0548` pass import tests.

LP supports:

- One `Minimize`/`Maximize` objective, a `Subject To` section, optional `Bounds`, `Binary`, `General` and `Semi` sections, and required `End`. Common aliases such as `min`, `max`, `st`, `binaries`, `generals` and `semi-continuous` are accepted.
- Signed linear terms, decimal/scientific numbers, repeated terms combined additively, objective offsets and constants on constraint left sides. Constant accumulation retains compensation through RHS subtraction before conversion to the final `double` bound; for example, `x + 1 - 1e16 >= -1e16` becomes `x >= -1`. Numeric coefficients and variable names require separating whitespace. Bounds and expressions use the original numerical units.
- One `<=`, `>=` or `=` comparison with numeric RHS per constraint. Objective expressions can wrap across lines. Constraints can wrap before their comparison/RHS; complete constraints must start separate lines. Multi-comparison ranged expressions are rejected; export uses equivalent paired inequalities instead.
- Bounds `lower <= x <= upper`, `x <= upper`, `x >= lower`, `x = value`, `lower <= x`, and `x free`, with explicit signed infinity where appropriate. Repeated definitions of the same bound side are rejected.
- Semi-continuous variables and semi-integer variables declared in both `General` and `Semi`. Semi domains are `{0} union [lower,upper]`; the initial model requires a strictly positive finite lower bound. Default undeclared LP variables are continuous on `[0,+infinity)`.
- Backslash comments. SOS, indicators, quadratic expressions, piecewise-linear sections, strict comparisons and other unsupported syntax are rejected.

MPS supports:

- `NAME`, optional `OBJSENSE` on the same or next line, `ROWS`, `COLUMNS`, optional `RHS`, `RANGES`, `BOUNDS`, and required `ENDATA`.
- First `N` row as objective; later `N` rows remain free constraints. `L`, `G` and `E` rows, one or two row/value pairs per COLUMNS/RHS/RANGES record, decimal/scientific values and `D` exponent notation.
- Integer markers `INTORG`/`INTEND`. A marker-only integer column with no explicit bounds defaults to `[0,1]`; the writer always emits explicit bounds. `LO`, `UP`, `FX`, `FR`, `MI`, `PL`, `BV`, `LI`, `UI`, `SC`, and `SI` bounds are supported. Ambiguous overlapping bound definitions and conflicting type declarations are rejected. `BV` sets both bounds and cannot be combined with other bounds for that variable. `SC` on an already integral column (integer marker, `LI` or `UI`) is rejected; use `SI` to explicitly preserve integrality. `SI` accepts an integer marker or preceding `LI`, but cannot be combined with `BV`/`SC`. Ordinary `LO` plus `SC`/`SI` remains supported.
- One RHS vector, one range vector and one bound vector. Multiple vectors, unknown row/column references, duplicate RHS/range records and unsupported sections fail explicitly. Repeated COLUMNS coefficients are summed, including objective coefficients.
- Standard range signs and the objective RHS offset convention: an objective RHS value `b` represents offset `-b`.
- Asterisk comments. Quadratic/SOS/indicator sections, `OBJNAME` objective selection, multiobjective extensions, SIF, compression and ambiguous dialects are rejected.

Import creates a new `ModelId`, fresh handles and a new revision history. Never reuse handles from the exporting model against an imported model.

## Export and names

The writer uses `max_digits10` (17 significant digits for `double`) for coefficients, bounds, costs and offsets. Every active variable is emitted, including otherwise unreferenced zero-cost variables. Variable types, fixed/free/infinite bounds, row relations, sense and objective constant are checked on the subsequent round trip. Deleted slots compact; no tombstone or old handle survives import.

File identifiers are deterministic `x0`, `x1`, … and `r0`, `r1`, …, avoiding illegal names, collisions, reserved words and syntax injection. Original display names, including duplicate/empty names, Unicode, quotes and newlines, are preserved in hex-encoded `GECODE_NAME` comments and restored by this reader. Other solvers see the canonical identifiers while retaining the same mathematics. Comments are parsed as data, with unknown entity references and malformed metadata rejected.

LP ranged rows are written as two ordinary inequalities plus a `GECODE_RANGE` comment. On reimport, both rows must have matching canonical expressions and the expected bounds before they are recombined. Other readers see the equivalent pair of inequalities. MPS uses its native RANGES section. If a range width cannot be represented and reread without changing the original bounds, MPS export fails; use LP's paired inequalities in that case. MPS semi-variable export currently requires a finite upper bound; LP can represent the abstract infinite-upper-bound semi domain.

MPS binary export currently requires the original bounds to be exactly `[0,1]` and emits a single `BV` record without redundant `LO`/`UP` records. Tighter binary bounds, including fixed binaries, fail before any destination mutation; use LP in that case. LP exports of fractional and fixed binary bounds are checked independently with HiGHS 1.15.1. This restriction avoids a known disagreement between MPS readers rather than silently widening a domain.

Original indicator semantics and their bound guards cannot be encoded by these linear formats. Export of a snapshot containing active indicator metadata is rejected; silently writing only the derived big-M rows would lose that contract.

## Destination safety and verification

Export first validates and compacts the source, serializes to a newly created exclusive temporary file in the destination directory, and closes it with checked write/flush/close results. It then imports that temporary file and compares **every** active variable type, bound and display name; row count, bounds, terms and names; and objective sense, terms and offset. Only an exact numerical match permits same-directory atomic replacement.

An existing destination remains unchanged if structural checks, serialization, reimport, semantic comparison, writing or replacement fails. Temporary files are removed on all ordinary failure paths. Replacement uses `rename` on POSIX and `MoveFileExW(..., MOVEFILE_REPLACE_EXISTING)` on Windows. This provides atomic visibility, not a promise of power-loss durability on every filesystem. The writer does not retain the old destination's inode, permissions or ACLs.

## Tests

`test/optimize/io.cpp` includes:

- Both formats: all five variable types, integer versus binary distinction, unused columns, free/fractional bounds, ranged/equality/free/constant rows, offsets, maximization, display names and tombstone compaction. LP additionally checks fixed and fractional binary bounds; MPS rejects these while preserving the existing destination.
- Precision regression `a=100000000000000.125`, `b=100000000000000.25`, with `a*x >= b` and integer `x`: exact round-trip coefficients retain minimum `2`; 15-digit rounding can incorrectly make it `1`.
- Duplicate objective terms, LHS constants and cancellation across the RHS in all three row relations, wrapped LP rows, both `General`/`Semi` declaration orders, MPS range signs, conflicting MPS type declaration orderings and tiny nonzero coefficients.
- Unsupported features, malformed files, ambiguous bounds, missing files, unsupported extensions, preexisting destinations, failed replacement, a post-write semantic rejection and temporary-file cleanup.
- Optional conventional public MPS imports and complete LP/MPS re-export checks when their directory is supplied as the first command argument. These are parsing/domain/round-trip checks; they do not claim performance or optimality.
- With `GECODE_OPTIMIZE_IO_TEST_HIGHS` defined and HiGHS linked, an independent parser compares every exported variable domain and objective coefficient, row bounds and sparse coefficients, objective sense and offset. Fixtures include all five variable types, unused columns, the precision regression, tighter binary LP bounds and both-format re-exports of the five public inputs. Private display names and the API distinction between binary and integer `[0,1]` are checked by the native round trip; HiGHS represents both as integer. HiGHS' free-MPS parser discards unconstrained `N` rows, which the cross-reader comparison permits because they do not change the feasible set or objective. Tiny coefficients outside the backend's accepted numerical range remain covered by the native I/O tests rather than this backend comparison.

Normal and address/undefined sanitizer builds are run separately from any timing benchmark. The current test run is recorded in the implementation handoff; cross-platform behavior requires the project's platform CI before a Windows support claim.
