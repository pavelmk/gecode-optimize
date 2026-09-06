# Gecode - Generic Constraint Development Environment

![Gecode](images/gecode-logo-100.png "Gecode")

Gecode is an open source C++ toolkit for developing
constraint-based systems and applications. Gecode provides a
constraint solver with state-of-the-art performance while being
modular and extensible.

[![CI](https://github.com/Gecode/gecode/actions/workflows/build.yml/badge.svg)](https://github.com/Gecode/gecode/actions/workflows/build.yml)

## Getting All the Info You Need...

You can find lots of information on
[Gecode's webpages](https://gecode.github.io),
including how to download, compile, install, and use it.

In particular,
Gecode comes with
[extensive tutorial and reference documentation](https://gecode.github.io/documentation.html).

## Optional optimization API

The [adaptive size-boundary study](docs/solver-parity/ADAPTIVE-BOUNDARIES.md)
searches each native version separately under ten-second limits, stopping
expansion after a failed size and confirming sampled boundaries. It checks
original witnesses; it does not independently recompute reference optima.

The [seven-category native scaling study](docs/solver-parity/CATEGORY-SCALING.md)
records 132 fixed ten-second comparisons with independent original-model checks.
It reports tested sizes and unfinished cases; it is not a general solver-capacity
or commercial-parity claim.

`Gecode::Optimize` adds a sparse owning model API, numerical HiGHS LP/MILP
solving, checked solution starts, bounded logical constraints, ordered
objectives, persistent sessions, numerical conflict diagnostics and strict
LP/MPS exchange. Owning LP observations, basis starts, numerical rays/Farkas
evidence and selected-basis sensitivity retain original-model coordinates.
Scenario batches and bounded continuous convex/concave quadratic models have
explicit separate contracts. A bounded exact-integer bridge compiles sparse
models and typed globals to native Gecode; explicit checked LP/frontier search
and one bounded incumbent neighborhood are also available.
The numerical component builds independently; both routes build
through `-DGECODE_ENABLE_OPTIMIZE=ON`. Existing native interfaces remain available.
See the [build and API guide](docs/solver-parity/README.md),
[validation record](docs/solver-parity/VALIDATION.md), and
[implementation roadmap](docs/solver-parity/IMPLEMENTATION.md) for supported
scope and the native-solver work that remains.
The native reference documentation includes an Optimize task group and guide
from [doxygen/optimize.hh](doxygen/optimize.hh). The
[current integrated checkpoint](docs/solver-parity/NINTH-CHECKPOINT.md) records
the completed scope; the [benchmark report](docs/solver-parity/BENCHMARKS.md)
separates correctness, common-workload timing and remaining limitations.
The [fast regression gate](docs/solver-parity/FAST-REGRESSION.md) checks 35
required cases within a 28-second whole-command budget using prebuilt binaries.
These additions do not establish commercial-solver parity. Further feature
implementation is on hold after the current checkpoint.

## CMake Build Options

CMake exposes options aligned with the Autoconf build switches.
The minimum required CMake version is 3.21.
`configure.ac` is the canonical autoconf source, and `configure` is generated
from it.
Version metadata shared by autoconf and CMake lives in `gecode-version.m4`.
`build/` is reserved for generated build outputs.

| Autoconf switch | CMake option / mechanism | Status | Notes |
|---|---|---|---|
| `--enable-shared` | `GECODE_BUILD_SHARED` | Supported directly | Default `ON` |
| `--enable-static` | `GECODE_BUILD_STATIC` | Supported directly | Default `OFF` |
| `--enable-thread` | `GECODE_ENABLE_THREAD` | Supported directly | Default `ON` |
| `--enable-osx-unfair-mutex` | `GECODE_ENABLE_OSX_UNFAIR_MUTEX` | Supported directly | Default `ON` |
| `--enable-qt` | `GECODE_ENABLE_QT` | Supported directly | `AUTO` by default; Qt 6 preferred; Qt 5.15+ supported |
| `--enable-gist` | `GECODE_ENABLE_GIST` | Supported directly | `AUTO` by default except macOS; disabled automatically if Qt GUI support is unavailable |
| `--enable-cpprofiler` | `GECODE_ENABLE_CPPROFILER` | Supported directly | Default `ON` |
| `--enable-cbs` | `GECODE_ENABLE_CBS` | Supported directly | Default `OFF` |
| `--enable-examples` | `GECODE_ENABLE_EXAMPLES` | Supported directly | Default `ON` for top-level builds, `OFF` for subprojects |
| `--enable-search` | `GECODE_ENABLE_SEARCH` | Supported directly | Default `ON` |
| `--enable-int-vars` | `GECODE_ENABLE_INT_VARS` | Supported directly | Default `ON` |
| `--enable-set-vars` | `GECODE_ENABLE_SET_VARS` | Supported directly | Default `ON` |
| `--enable-float-vars` | `GECODE_ENABLE_FLOAT_VARS` | Supported directly | Default `ON` |
| `--enable-minimodel` | `GECODE_ENABLE_MINIMODEL` | Supported directly | Default `ON` |
| None | `GECODE_ENABLE_OPTIMIZE` | CMake-only | Optional numerical optimization component; default `OFF`; standalone build also available |
| `--enable-driver` | `GECODE_ENABLE_DRIVER` | Supported directly | Default `ON` |
| `--enable-flatzinc` | `GECODE_ENABLE_FLATZINC` | Supported directly | Default `ON` |
| `--enable-mpfr` | `GECODE_ENABLE_MPFR` | Supported directly | Default `ON`; uses `find_package(MPFR)` |
| `--enable-allocator` | `GECODE_ENABLE_ALLOCATOR` | Supported directly | Default `ON` |
| `--enable-audit` | `GECODE_ENABLE_AUDIT` | Supported directly | Default `OFF` |
| None | `GECODE_ENABLE_FAULT_INJECTION` | CMake-only | Test-only, process-global failpoints in an isolated single-threaded `check-fault` suite; default `OFF` |
| None | `GECODE_SANITIZER` | CMake-only | `address`, `undefined`, `address-undefined`, or `thread`; currently requires GCC/Clang-style flags |
| `--enable-gcc-visibility` | `GECODE_ENABLE_GCC_VISIBILITY` | Supported directly | Default `ON` |
| `--with-freelist32-size-max` | `GECODE_FREELIST32_SIZE_MAX` | Supported directly | Cache string |
| `--with-freelist64-size-max` | `GECODE_FREELIST64_SIZE_MAX` | Supported directly | Cache string |
| `--with-vis` | `GECODE_WITH_VIS` | Supported directly | Comma-separated list |
| `--with-lib-prefix` | `GECODE_LIB_PREFIX` | Supported directly | Prefixes generated library basenames |
| `--with-lib-suffix` | `GECODE_LIB_SUFFIX` | Supported directly | Suffixes generated library basenames |
| `--enable-debug` | `CMAKE_BUILD_TYPE=Debug` (or multi-config `Debug`) | Mapped to native CMake mechanism | Use standard CMake build-type workflows |
| `--enable-small-codesize` | `CMAKE_BUILD_TYPE=MinSizeRel` or compiler size flags | Mapped to native CMake mechanism | Use standard size-optimized build settings |
| `--enable-leak-debug` | None | Not supported in CMake | No CMake option enables the `GECODE_HAS_MTRACE` test hook |
| `--enable-profile` | Toolchain/CMake compile+link flags | Mapped to native CMake mechanism | Configure profiling via standard compiler flags |
| `--enable-gcov` | Toolchain/CMake coverage flags | Mapped to native CMake mechanism | Configure coverage instrumentation via compiler/linker flags |
| `--with-mpfr-include`, `--with-mpfr-lib` | `CMAKE_PREFIX_PATH`, `MPFR_ROOT`, toolchain include/link paths | Mapped to native CMake mechanism | Use CMake package and toolchain discovery |
| `--with-gmp-include`, `--with-gmp-lib` | Toolchain include/link paths | Mapped to native CMake mechanism | GMP is resolved through MPFR/toolchain linkage |
| `--with-host-os` | None | Not supported in CMake | Generator/toolchain already determine host/target platform |
| `--with-compiler-vendor` | None | Not supported in CMake | Compiler is selected through toolchain and generator |
| `--with-sdk`, `--with-macosx-version-min`, `--with-architectures` | None | Not supported in CMake | Use native CMake/macOS toolchain settings |
| `--enable-framework` | None | Not supported in CMake | No framework-bundle generator path is implemented |
| `--enable-resource` | None | Not supported in CMake | No autoconf-style resource toggle in CMake |
| `--enable-peakheap` | None | Not supported in CMake | No CMake option defines the peak-heap tracking macros |
| `--enable-doc-dot`, `--enable-doc-search`, `--enable-doc-tagfile` | `GECODE_DOC_DOT`, `GECODE_DOC_SEARCH`, `GECODE_DOC_TAGFILE` | Supported by `doc` target | Requires Doxygen 1.17.0 or newer; helper pages require `uv` |

By default, CMake uses checked-in `gecode/kernel/var-type.hpp` and
`gecode/kernel/var-imp.hpp`; regeneration is opt-in via
`-DGECODE_REGENERATE_VARIMP=ON`. A nonempty `GECODE_WITH_VIS` list enables
regeneration automatically and validates every specification during
configuration; relative paths are resolved from the source directory.
Build-time script execution uses `uv run --script ...` and requires Python
3.11 or newer. Autoconf builds require `uv` on `PATH`; CMake requires it only
for generated-script paths such as `-DGECODE_REGENERATE_VARIMP=ON` and the
`doc` target. Documentation generation requires Doxygen 1.17.0 or newer.

Autoconf `make check` deliberately does not build or run the CMake-only
failpoint sources. Its ordinary test executable therefore never mixes
process-global fault cases into the multi-threaded check run.

When changing generated-source inputs, run `make regenerate` after configuring
the project. This uses the same version-checked workflow as CI and caches the
Autoconf 2.72 bootstrap locally; Bison 3.8.2, Flex 2.6.4, and `uv` must be
available. Ordinary C++ changes do not require regeneration.

`GECODE_ENABLE_QT` and `GECODE_ENABLE_GIST` accept `AUTO`, `ON`, and `OFF`.
Use `ON` to require the dependency and fail configuration if it is missing or
too old, `OFF` to disable it, and `AUTO` to use it when the local toolchain
provides a supported Qt.

Deprecated compatibility aliases are accepted for the Gecode 6.x line:
`ENABLE_THREADS`, `ENABLE_GIST`, `BUILD_EXAMPLES`, `ENABLE_CPPROFILER`.

For a Visual Studio + vcpkg workflow (including preset-based commands for
MPFR), see [`docs/cmake-build.md`](docs/cmake-build.md).

Qt 6 is the preferred Qt line for Gecode builds. Qt 5.15 or newer remains
supported for legacy environments, but older Qt releases are ignored unless
`GECODE_ENABLE_QT=ON`, in which case configuration fails. On macOS, use a Qt
build that supports the active macOS SDK; recent Qt 6 releases are the safest
choice. Gist is opt-in for CMake builds on macOS. Use `-DGECODE_ENABLE_GIST=ON`
when Qt is installed and its framework link interface is usable.

## CMake Package Consumption

For CMake build/install workflows and downstream `find_package(Gecode)` usage,
see [`docs/cmake-build.md`](docs/cmake-build.md).

Minimal downstream example:

```cmake
find_package(Gecode CONFIG REQUIRED)
target_link_libraries(my_target PRIVATE Gecode::gecode)
```

Use `Gecode_VERSION` from package config for version checks.

## Download Gecode

Gecode 6.4.0 is distributed as source code. Source archives can be downloaded from
[GitHub](https://github.com/Gecode/gecode/releases)
or
[Gecode's webpages](https://gecode.github.io/download.html).

## Contributing to Gecode

We happily accept smaller contributions and fixes, please provide them as pull requests against the main branch. For larger contributions, please get in touch.

## Gecode License

Gecode is licensed under the
[MIT license](https://github.com/Gecode/gecode/blob/main/LICENSE).
