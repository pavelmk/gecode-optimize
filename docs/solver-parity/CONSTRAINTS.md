# Bounded logical modeling helpers

`gecode/optimize/constraints.hpp` adds numerical linear formulations to
`Gecode::Optimize::Model`. It does not change the native Gecode `Space` API or
introduce backend-native indicators. All handles must belong to the model, and
logical variables must have `VariableType::Binary`; an integer with bounds
`[0,1]` is not accepted as a substitute.

```cpp
#include <gecode/optimize/constraints.hpp>
#include <limits>

using namespace Gecode::Optimize;
Model model;
auto enabled = model.add_binary("enabled");
auto amount = model.add_continuous(0.0, 100.0, "amount");
auto condition = add_indicator(model, enabled, true,
                               {{amount, 1.0}}, 20.0,
                               std::numeric_limits<double>::infinity(),
                               "minimum_when_enabled");
// enabled == 1 implies amount >= 20; enabled == 0 imposes no such lower bound.
```

`add_indicator(model, b, active_value, terms, lower, upper)` means
`b == active_value => lower <= sum(terms) <= upper`. It supports either activation
value, one-sided or ranged rows, negative coefficients, terms containing the
activator, and constant rows. Duplicate terms use the same deterministic
coalescing as ordinary model rows. Both infinite bounds represent a tautology.

## Formulation and numerical semantics

The helper computes separate lower and upper relaxation constants from the
variable bounds captured when it is called. For each original term, it selects
the appropriate signed endpoint of the inactive domain. The activator is fixed
to its inactive value in this calculation. A semi-continuous or semi-integer
variable's domain includes zero, even when its stored nonzero lower bound is
positive. Only endpoints needed by the finite row bounds must be finite.
Constraints elsewhere in the model are not used to infer tighter endpoints.

Multiplication and summation bounds are rounded outwards with `nextafter`;
relaxation constants enclose the resulting violation of each finite row bound.
Unbounded required endpoints, NaNs, nonfinite coefficients, or arithmetic that
cannot be enclosed by finite doubles throw `ModelError` with a domain-tightening
or rescaling suggestion. The implementation never guesses or silently clamps M.
It conservatively rejects some extreme but representable models rather than
underestimating a relaxation constant.

When either M is positive, an auxiliary binary `g` represents inactivity:

| Activation condition | Gate equality |
| --- | --- |
| `b == 1` | `g + b = 1` |
| `b == 0` | `g - b = 0` |

The finite lower side becomes `sum(terms) + M_lower*g >= lower`; the finite
upper side becomes `sum(terms) - M_upper*g <= upper`. This preserves the original
stored coefficients and bounds on the active side, including a small coefficient
on `b` that could otherwise be lost when combined with a large M. At exactly
integral activation and gate values, the linear formulation has the specified
logical meaning. This is a numerical double model, not exact rational arithmetic
or a proof certificate.

The result exposes the `Indicator` handle, optional auxiliary gate, generated row
handles, and each optional M. A one-sided indicator adds one original-side row;
a ranged indicator adds two. A needed gate adds one binary variable and one
equality row. If all M values are zero, no gate is added. A tautology adds no
variables or rows but still retains its original indicator metadata.

Large M values can weaken relaxations and interact poorly with floating point
solver tolerances. Backend coefficient limits and numerical validation still
apply; successful modeling does not promise that every backend can safely solve
the resulting scale. The independent validator rounds the activator to decide
whether the implication is active, then evaluates the original row with the
submitted values and requested feasibility tolerance. It reports
`max_indicator_violation` separately. Thus an almost-integral gate cannot hide a
large original-row violation behind an otherwise numerically feasible M row.
The result must pass the original check to be marked solution-validated.

## Mutation, snapshots, and removal

Posting any helper succeeds as one revision or leaves the model unchanged,
including when construction of a later generated row fails. The transaction is
an internal staging operation, not a public callback API.

An active indicator captures the domains that justify its lowering. Bounds may
be tightened and later widened within the captured domain. Widening beyond that
domain is rejected; remove and rebuild the indicator to use new bounds. Original
variables referenced by an active indicator cannot be removed. Generated row
coefficient/bound edits and individual generated-row removals are rejected, as
are changes to an active gate's `[0,1]` bounds. Renaming is allowed.

`remove_indicator(model, condition.indicator)` atomically deactivates the logical
metadata and all its generated rows. This releases its domain guards. The gate
remains an ordinary model variable because other rows or the objective may use
it; callers can remove it explicitly after removing any remaining references.
Handles and slots are never reused. Removed indicator records remain tombstones.

Snapshots own `IndicatorData`, original terms, captured domains, and generated
row/gate origin tags. Moving a model and copying snapshots preserves this
metadata. Structural validation checks the lowering against its original
meaning, rederives safe M values, and rejects stale domains, missing metadata,
aliased gates, inconsistent lifecycle flags, and changed generated rows. Code
that constructs or edits public snapshots must preserve this structure.

An LP/MPS serialization of only the lowered rows cannot preserve the original
logical validation contract. Exporters must reject active original indicators
unless their format and reader explicitly preserve this metadata; no native
indicator interchange is provided by this helper slice.

## Boolean AND and OR

```cpp
auto a = model.add_binary("a");
auto b = model.add_binary("b");
auto all = model.add_binary("all");
auto any = model.add_binary("any");
auto and_rows = add_boolean_and(model, all, {a, b});
auto or_rows = add_boolean_or(model, any, {a, b});
```

These functions encode equality with the Boolean AND/OR of the inputs. Empty
AND is true; empty OR is false. One input produces an equality. Duplicate inputs
are idempotent, and the result may also appear among the inputs. For two or more
distinct inputs they add one row per input plus one aggregate row, without an
auxiliary variable. They return ordinary row handles that can be edited or
removed using the normal model API. Boolean helpers need no large constants;
ordinary numerical row and integrality validation applies.

## Correctness checks

`test/optimize/constraints.cpp` exhaustively compares tiny integral assignments
with an independent logical oracle for both activation values, signed terms,
activator terms, and one-sided/ranged bounds. It also checks semi-variable zero
domains, redundant and impossible rows, empty/single/multiple Boolean inputs,
aliases and duplicates, failure atomicity, invalid/foreign handles, unsupported
unbounded domains, mutation guards, hostile snapshot edits, small active
coefficients with large M, and near-integral gate loopholes. Tests compile and
run without a numerical backend, including address/undefined sanitizer builds.
