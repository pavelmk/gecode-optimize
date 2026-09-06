# Regular constraints through C and Python

`gecode_opt_v1_model_add_regular` and Python `Model.add_regular` construct the [typed sparse Regular global](REGULAR.md). They add one ordinary `GlobalConstraint` identity, so existing global naming/removal APIs apply. The versioned C record is `gecode_opt_regular_transition_v1`: `struct_size`, zero `reserved`, unsigned 64-bit `from`, signed 64-bit `symbol`, and unsigned 64-bit `to`. The call also receives an exact transition element size, independent array counts, state count, initial state, and final-state array.

State count is positive; state IDs lie in `[0, state_count)`. Zero is a real state and a real symbol. Symbols must be exactly representable integers within ±2^53 in the shared model; the native solver admits a narrower range, as described in the C++ contract. Missing transitions reject the word. Duplicate `(from, symbol)` keys are invalid even when their targets match. Duplicate final states are harmless. There are no epsilon transitions. The empty word is accepted exactly when the initial state is final. Repeated variables in the word retain equality and are not copied into independent decisions. Huge sparse state numbers do not allocate a dense state-count array.

The C boundary validates pointers, address/vector count limits, the exact element size, every record's exact size and zero reserved field, entity kind, and UTF-8 name before posting. The C++ model validates source ownership, deleted handles, discrete variable types, automaton ranges, exact symbols, and deterministic transition keys. A failure leaves the model and revision unchanged and clears a provided output ID. Successful posting advances the revision once. Arrays and names are copied; changing caller buffers afterward cannot change the model. No exception crosses the C boundary, and solver `Unsupported` remains distinct from API/model-building errors.

Python accepts ordinary variable, transition, and final-state sequences without NumPy. Each transition is a frozen `RegularTransition(from_state, symbol, to_state)` value. It rejects booleans, fractional numbers, and out-of-range integers before ctypes can truncate them. `None` or a tuple is not a transition record. Entities from another loaded ABI instance are rejected in Python; foreign or deleted source identities are rejected by C++.

```python
from gecode_optimize import (
    Model, Options, Guarantee, VariableType, RegularTransition as Edge,
)

with Model() as model:
    word = [model.add_variable(VariableType.INTEGER, -1, 1) for _ in range(3)]
    model.add_regular(
        word, state_count=2, initial_state=0,
        transitions=[Edge(0, -1, 0), Edge(0, 1, 1),
                     Edge(1, -1, 1), Edge(1, 1, 0)],
        final_states=[0], name="even number of +1 symbols",
    )
    model.set_objective([(variable, 1) for variable in word])
    with model.solve(Options(guarantee=Guarantee.EXACT)) as result:
        print(result.termination)
```

An active Regular global makes the one-shot `Auto` route select Native. A build without Native still constructs the record, and solving returns `Unsupported`. Explicit HiGHS and persistent sessions reject the complete model; they never omit its Regular constraint. Native solves preserve original result identities, both objective senses, offsets, other admitted globals, and linear rows. Closing a model or removing a global cannot alter an already owned historical result. A variable still referenced by an active Regular global cannot be removed.

The actual C99 consumer `test/optimize/regular_c_api.c` uses an independent parity language oracle and mixed all-different/linear constraints, both objective senses, source-buffer mutation, historical results, and malformed count/size/reserved/state/symbol/owner cases. `python/tests/test_regular.py` first enumerates accepted labeled paths and then exhausts independent variable assignments, covering missing transitions, signed symbols, empty words, repeated variables, duplicate finals, huge sparse state IDs, min/max, mixed constraints, backend routing, atomic rejection, and semi-integer zero semantics. The facade and C wrapper must both be recompiled after this C++ `GlobalPayload` variant change; old facade objects are not binary-compatible merely because the C ABI remains version 1.
