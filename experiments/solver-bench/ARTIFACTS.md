# Reproduction and packaging checklist

This is a source/dependency audit of the current experiment. It does not certify a copied package: no package was copied, built, or executed during this audit. A final package needs its own file inventory and relocation check.

## Files required outside this experiment directory

Copying `experiments/solver-bench/` alone is insufficient to rebuild the six focused C++ tests. [build.py](build.py) resolves the Gecode root as two directories above itself and uses these additional paths:

| Path relative to the Gecode root | Why it is needed |
| --- | --- |
| Complete upstream source tree, including `gecode/`, `CMakeLists.txt`, `cmake/`, `misc/`, and files included by their build rules | Builds the native and modified static libraries. Preserve the whole source checkout rather than guessing a minimal subset of upstream build inputs. |
| `gecode/minimodel/lp-model.hpp` | Shared exact native model builder; also included by the stock driver after stock headers take precedence. |
| `gecode/minimodel/lp-certificate.hpp` | Exact rational bound/conditional deduction implementation. |
| `gecode/minimodel/lp-backend.hpp` | Continuous HiGHS workspace and certificate interface. |
| `gecode/minimodel/lp-relaxation.hpp` | Gecode bound/fixing propagator. |
| `gecode/minimodel/lp-strengthening.hpp` | Binary normalization, conflict/clique/cover generation. |
| `gecode/minimodel/lp-primal.hpp` | LP-guided primal heuristic and exact candidate checking. |
| `gecode/minimodel/experimental-cliques.hpp` | Earlier graph-strengthening addition. It is not included by the current four benchmark drivers, but belongs in a package claiming to deliver all software additions. |
| `gecode/search.hh`, `gecode/search/options.hpp`, `gecode/search/seq/dfs.hpp`, `gecode/search/seq/bab.hpp` | The modified search option and sequential checkpoint implementation. |
| Modified `CMakeLists.txt` and `cmake/GecodeConfig.cmake.in` | Opt-in HiGHS discovery and exported `Gecode::gecodelp` target. |
| `experiments/lp-relaxation/tests/certificate.cpp` | Compiled as `test-certificate`. |
| `experiments/lp-relaxation/tests/backend.cpp` | Compiled as `test-backend`. |
| `experiments/lp-relaxation/tests/propagator.cpp` | Compiled as `test-propagator`. |
| `solver-bench/tests/reduced_cost.cpp` | Compiled as `test-reduced-cost`. This path is at the repository root, outside `experiments/`. |
| `examples/job-shop-instances.hpp` | Required to regenerate or independently test the six bundled public job-shop imports. Not required to run their already extracted inputs. |
| `test/flatzinc/*.cpp` | Required to regenerate and test the extracted FlatZinc fixtures. Not required to run their already extracted `.fzn` inputs. |
| Root `LICENSE` and embedded third-party notices, including `gecode/third-party/boost/LICENSE_1_0.txt` | Keep upstream copyright, permission, and component notices with source. |

The other two focused test sources, `tests/strengthening.cpp` and `tests/primal.cpp`, are inside this experiment directory. The root-level reduced-cost test and the three earlier LP tests have no further custom test-framework dependency: they include the shipped headers and standard library.

The prior checkpoint/clique experiments and their test logs are optional for reproducing the current six focused tests. Retain them if the final report cites their earlier validation. For example, a claim about the complete upstream search suite or the checkpoint-specific suite needs its original test sources, invocation and results, not just this experiment's LP test metadata.

## Build tools and pinned source dependencies

- Python **3.12 or later** is checked by both build scripts. The benchmark, validators, importers, trainer and analyzer use the standard library plus adjacent Python modules; there is no NumPy, scikit-learn, SciPy, notebook, MiniZinc compiler, or `highspy` dependency.
- Git is a functional dependency, not just a provenance label. `build.py` calls `git archive 3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e`, `git ls-files`, and `git rev-parse HEAD`. A directory of source files with no usable Git repository will fail. Preserve a normal checkout with that baseline object, or provide a Git bundle and restore the repository before invoking the unchanged builder.
- CMake **3.21 or later** is required by Gecode's top-level build. A C/C++ toolchain, a CMake build tool such as Make/Ninja, and POSIX threading support are needed. The custom driver/test compile commands require C++17.
- The current harness is oriented to macOS/Linux toolchains: it invokes `clang++` or `c++`, links `.a` files with `-pthread`, and its drivers use `sys/resource.h`. It is not a tested Windows/MSVC build procedure. On macOS the scripts explicitly select deployment target **15.7**. The delivered measured executables are local-machine artifacts; portability requires rebuilding and reporting another cohort.
- HiGHS is pinned to tag `v1.15.1`, commit `04024d701f79feb8e2f18bc3df0dffc04ef05088`, from [ERGO-Code/HiGHS](https://github.com/ERGO-Code/HiGHS). The builder verifies its Git HEAD and source archive. For offline rebuilding, preserve its checkout and required Git objects too. An archive without Git history does not meet the unchanged verifier's requirements.
- The continuous backend links both `libhighs.a` and `libhighs_extras.a`. The build disables HIPO and zlib and uses no GPU, external BLAS, Qt, Gist, MPFR or Python solver binding. Retain all bundled source dependencies and notices even when an optional component is disabled.
- FlatZinc uses [fzn-build.py](fzn-build.py) and separate build directories with integer, set and float support enabled; MPFR and Qt remain disabled. It imports the adjacent `build.py` verification helpers. It does not link HiGHS or automatically use the LP actor.

`build.py` compiles the focused tests but does **not run them**. Execute the six resulting programs explicitly and retain stdout, stderr, exit status and executable hash. The current `suite.py` presets run performance batches; they are not a correctness-test runner.

```sh
python3 experiments/solver-bench/build.py --jobs 4
build/solver-bench/bin/test-certificate
build/solver-bench/bin/test-backend
build/solver-bench/bin/test-propagator
build/solver-bench/bin/test-reduced-cost
build/solver-bench/bin/test-strengthening
build/solver-bench/bin/test-primal
```

The scripts support explicit `--highs-source` and `--highs-build` locations. `--skip-libraries` verifies source/configuration and records reused library hashes but does not prove how those preexisting binaries were produced. It is unsuitable as the only clean-rebuild evidence.

## Corpus and evidence to retain together

Keep every manifest byte-for-byte with its relative data directories:

| Manifest | Data directory | Current cases |
| --- | --- | ---: |
| `manifest.json` | `instances/` | 300 binary generated/control inputs |
| `native-manifest.json` | `native-instances/` | 64 native generated inputs |
| `rcpsp-manifest.json` | `rcpsp-instances/` | 16 native RCPSP inputs |
| `public-manifest.json` | `public-instances/` | 6 whole public job-shop inputs |
| `public-binary-manifest.json` | `public-binary-instances/` | 12 whole OR-Library inputs |
| `miplib-manifest.json` | `miplib-instances/` | 5 whole legacy MIPLIB inputs |
| `fzn-manifest.json` | `fzn-instances/` | 56 regression fixtures |
| `scale-manifest.json` | `scale-instances/` | 90 generated larger inputs |

All referenced JSON/TXT/FZN/expected-output/notice paths in these manifests were relative and present at the time of this audit. The 300 binary inputs include 12 tiny controls; corpus counts must not be added indiscriminately into one performance headline. The main generated split is 138 development and 230 held-out inputs across binary/native representations, plus the 12 controls. Public, larger-size, and FlatZinc tracks remain separate.

For offline import provenance and regeneration also keep:

- `public-cache/{mknap1.txt,gap1.txt,or-library-license.html}`.
- `miplib-cache/` with the five original `.mps` files, their downloaded `.mps.gz` files, `miplib3_cat.txt`, and `mps_format.txt`.
- Every public/FZN notice file, upstream source/hash attribution in the manifests and instance JSON, and the original source arrays/fixtures mentioned above.
- `generator.py`, `native.py`, `native_rcpsp.py`, `generate_scale.py`, all four importers, validators, tests, `policy.json` and `policy.hpp`.

Keep each measured `.jsonl` together with its **same-stem `.meta.json`**, the corresponding input corpus, build metadata, exact source/policy snapshot and executable hashes. Preserve all iterations separately: later builds overwrite `results/build-metadata.json` and the default output binaries. A single latest metadata file cannot describe earlier executables. The build's `bin/source/` snapshot contains selected drivers, policy, LP headers and search files; it is **not** a complete standalone source archive and omits the focused test sources, CMake files and most upstream code.

For historical result analysis, binaries are not executed or required by `analyze.py`. Its binary audit checks the hash recorded in each row against the hash recorded in immutable batch metadata. It does not reconstruct the build from that hash. Keep the actual binary/build evidence separately if making a build-provenance claim. Timestamped intermediate objective values generally lack individual assignments; the analyzer records whether the deadline objective has a checkable initial/final witness. Do not present every intermediate trace value as independently witness-verified.

Do not regenerate a frozen corpus in place before reproducing a historical report. Construction timestamps/timings can change JSON bytes and hashes even when mathematical inputs and seeds are identical. Use a different output directory for generation checks, and preserve the delivered originals for result auditing.

## Licenses and attribution

| Material | Observed notice / packaging requirement |
| --- | --- |
| Gecode source and modifications | Root `LICENSE` applies unless a file says otherwise; retain original file author notices. Several new headers explicitly say `SPDX-License-Identifier: MIT`; the remaining new files have no separate disclaimer and should ship with the root license. Do not remove Gecode's bundled component licenses. |
| HiGHS source and linked binary code | Preserve `LICENSE.txt` and third-party notices in its source tree. `extern/README.md` identifies pdqsort as Zlib-licensed; its notice is embedded in `extern/pdqsort/pdqsort.h`. Other bundled components retain their own notices even if not built. A HiGHS top-level MIT notice alone does not replace all embedded component notices. |
| Extracted job-shop arrays | `public-instances/NOTICE.txt` preserves the complete MIT notice from Gecode's bundled source. |
| Extracted FlatZinc fixtures | Each `.NOTICE.txt` preserves the corresponding upstream source notice. Keep these next to the model and expected output. |
| OR-Library data | The [official legal page](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/legal.html) explicitly applies MIT terms to OR-Library material. The downloaded page and `public-binary-instances/OR-Library-LICENSE.html` retain the notice. |
| MIPLIB 3.0 data | The [official legacy page](https://miplib2010.zib.de/miplib3/miplib.html) provides the benchmark for research, and the cached MPS/catalogue identify the original sources. No explicit redistribution license was found in the inspected page, catalogue, or MPS headers. Preserve provenance and do **not** relabel this data MIT or infer that the project's code license covers it. Before a separately published redistributed-data package, settle this point or provide the pinned official download/import route instead. Local evaluation and the present cached evidence do not establish a new data license. |

No MiniZinc Challenge corpus or MIPLIB 2017 collection was downloaded. The coverage document discusses those suites; discussion and links should not be mistaken for shipped licensed datasets.

## Recommended portable layout

Preserve the existing relative source structure rather than moving the four externally located tests without updating the build and its tests:

```text
artifact/
  SOURCE-MANIFEST.json       # whole-package hashes, exclusions, provenance
  licenses/                 # convenient copies; keep original notices too
  source/
    gecode/                 # complete modified checkout, with usable Git data
      .git/                 # or restore from a provided baseline Git bundle
      LICENSE
      CMakeLists.txt
      cmake/
      gecode/
      examples/
      test/
      solver-bench/tests/reduced_cost.cpp
      experiments/
        lp-relaxation/tests/{certificate,backend,propagator}.cpp
        solver-bench/       # scripts, docs, immutable corpus, notices
    HiGHS/                  # pinned checkout, Git data and complete notices
  evidence/
    iteration-v0/           # original logs + same-stem metadata + build evidence
    iteration-v1/
    final/
  reports/                  # generated HTML/JSON/CSV; no solver required to view
```

Put fresh builds under `source/gecode/build/solver-bench/` and supply `--highs-source ../HiGHS` from the Gecode root. This keeps all default Gecode paths valid while allowing a fully cached rebuild. Alternatively keep the builder's default dependency checkout at `source/gecode/build/solver-bench/deps/HiGHS`. Exclude stale build trees, CMake caches and `__pycache__` from the portable source package. If historical executables are included under `evidence/`, label their original architecture/OS and retain their original hashes.

Historical metadata and policy provenance intentionally contain the machine's original absolute paths. Do not silently rewrite those files or their hashes. `analyze.py` locates a recorded manifest by exact hash, either at its recorded path, alongside the analyzer, or through repeated `--manifest` overrides. Keeping unchanged manifests next to the copied analyzer often suffices. A new run records new absolute paths and forms new metadata.

An interrupted `bench.py --resume` batch requires exact protocol equality, including the absolute manifest path map and platform/binary identities. Relocating it changes that protocol, so a moved partial batch should remain historical evidence and a fresh complete batch should use a new output path. This limitation does not prevent analyzing a relocated complete batch. FlatZinc retains its own runner/protocol and separate regression summary.

## Claims checked in the current documents

The README, protocol and software guide correctly scope the new LP module to binary linear models, acknowledge existing native Gecode capabilities, separate FlatZinc regression from optimization, identify soft time limits, and avoid a commercial-solver speed claim. The following qualifications should accompany the final package:

- “Reproducible” requires the complete source/Git/test/dependency layout above, not merely the experiment directory or partial build snapshot.
- The README's general C++17 compiler prerequisite does not imply a tested Windows build; the harness currently makes POSIX/static-library assumptions.
- Source/run hashes and internal binary identity checks are recorded provenance, not independent proof of compilation or a tamper-proof submission service.
- The headline counts describe generated representations; the two encodings of TSP and coloring do not create additional problem concepts. Dataset and regression counts are separate.
- `SOFTWARE.md` documents all additions, including the earlier graph helper and checkpoint option. Their presence in that inventory does not mean every measured configuration enables them; default `c_p=0` leaves checkpoint behavior unchanged.
- The README contains a minor `all108` spacing typo. `DATA_FORMAT.md`'s last statement about every delivered instance having a feasible witness applies to its original generated binary collection, not the later cold-start MIPLIB inputs. Keep that scope explicit if editing that document into a combined data manual.

