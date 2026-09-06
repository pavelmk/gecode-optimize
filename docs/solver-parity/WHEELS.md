# Local self-contained Python wheels

The first wheel recipe targets a native macOS host and packages a prebuilt
single-architecture C ABI library with native Gecode and HiGHS linked statically
inside it. The installed Python package locates that library beside its own
modules. An application can call `Model()` without setting a library path or
installing a separate solver. Explicit `load_library(path)` and
`GECODE_OPTIMIZE_LIBRARY` still take precedence. Missing/incomplete bundled data
fails explicitly; it does not silently load an unrelated solver.

This is a local experimental distribution. It does not publish to PyPI or
provide Linux, Windows, universal macOS, or separately linked dependency repair.
Those need their own builds, dependency audits and clean-environment tests.
The declared minimum macOS version is read from the binary; a successful run on
a newer host does not establish testing on that oldest supported OS.

## Build a suitable library

Start from a clean implementation checkout and the pinned HiGHS source recorded
in [dependencies.json](dependencies.json). Build in an isolated directory:

```sh
cmake -S . -B build/python-wheel \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
  -DGECODE_ENABLE_OPTIMIZE=ON -DGECODE_OPTIMIZE_WITH_HIGHS=ON \
  -DGECODE_OPTIMIZE_HIGHS_SOURCE="$PWD/../deps/HiGHS" \
  -DGECODE_BUILD_SHARED=OFF -DGECODE_BUILD_STATIC=ON \
  -DBUILD_SHARED_LIBS=OFF -DGECODE_DEFAULT_LINK_VARIANT=STATIC \
  -DGECODE_ENABLE_QT=OFF -DGECODE_ENABLE_GIST=OFF \
  -DGECODE_ENABLE_MPFR=OFF -DGECODE_ENABLE_EXAMPLES=OFF \
  -DGECODE_ENABLE_SET_VARS=OFF -DGECODE_ENABLE_FLOAT_VARS=OFF \
  -DGECODE_ENABLE_MINIMODEL=OFF -DGECODE_ENABLE_DRIVER=OFF \
  -DGECODE_ENABLE_FLATZINC=OFF -DBUILD_TESTING=OFF \
  -DGECODE_OPTIMIZE_BUILD_TESTS=OFF
cmake --build build/python-wheel --target gecodeoptimize_c -j2
```

This Python library contains the integer/global native API and numerical
LP/MILP/QP route. It does not bundle the legacy FlatZinc executable, Gist, set or
interval-float native frontends. Existing C++ installation recipes remain
available for those modules. The builder requires a matching native host; an
x86_64 recipe needs its own suitable deployment target and actual verification.

Use a Python environment containing `packaging` and `wheel`, then run:

```sh
python tools/python/build_macos_wheel.py \
  --library build/python-wheel/gecode/optimize/libgecodeoptimize_c.dylib \
  --output-dir build/wheels --version 0.1.0.dev20260905
```

Packaging performs no compilation or downloads. It checks thin architecture,
the macOS deployment load command, and system-only dynamic dependencies. An
input depending on other solver libraries, Homebrew paths or unresolved rpaths
is rejected; rebuild it with static dependencies. A binary targeting macOS
15.7 cannot be relabeled as requiring 15.0. For modern macOS, build at a major
baseline such as 11.0 so the wheel tag can describe the actual minimum. Platform
tags describe interpreter/ABI/platform compatibility; this ctypes package uses
`py3-none` and a macOS architecture tag, with Python >=3.9 in its metadata.
[PyPA compatibility tags](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/).

The builder copies Python sources and required Gecode/HiGHS/dependency notices,
records source/dependency identities and binary/source hashes, runs an isolated
automatic-load native/numerical smoke test, and uses the standard `wheel pack`
tool. It independently checks every archive member against RECORD, excludes
interpreter bytecode, and publishes the finished local file without overwriting
an existing wheel. Wheel metadata marks the archive as platform-dependent.
[PyPA wheel format](https://packaging.python.org/en/latest/specifications/binary-distribution-format/).

The source checkout must be clean unless `--allow-dirty` is explicitly selected
for development. A binary hash and successful smoke test do not prove that a
supplied binary was built from the accompanying source tree. Keep the build
configuration, source snapshot and test logs together; a release pipeline must
build and package the same frozen inputs. Bundled notices are included from the
clean pinned dependency source. No binary is downloaded at import or solve time.

## Verify the installed wheel

Install the resulting wheel into a fresh virtual environment using
`pip install --no-index --no-deps /absolute/path/to/the.whl`. Clear external
solver/Python/dynamic-library search overrides. Verify that both the imported
module and loaded C ABI file are inside that environment, and run the complete
Python conformance suite from outside the source package. Test numerical and
explicit native solves, ownership, cancellation and each newly added workflow.

Use `python -I -B` for isolated packaging checks: `-I` ignores Python environment
variables, so an environment-only bytecode suppression flag is insufficient.
The package locates its own binary rather than relying on `find_library`, whose
platform search behavior is intended for installed external libraries.
[Python ctypes library lookup](https://docs.python.org/3/library/ctypes.html#finding-shared-libraries).

Local checks and artifact paths belong in [VALIDATION.md](VALIDATION.md) once
the complete integration gate finishes. Add actual architecture/OS CI before
claiming cross-platform or minimum-OS release coverage; the broader workflow
should use established wheel tooling such as
[cibuildwheel](https://cibuildwheel.pypa.io/en/stable/).

The packager inspects the private staged binary after capturing its bytes, so a
concurrent rebuild cannot attach older deployment metadata to a newer library.
System dependency paths containing `.` or `..` components are rejected. Run the
portable adversarial packaging panel with a Python environment containing
`packaging`: `python -I -B tools/python/test_build_macos_wheel.py -v`. It checks
staged-byte identity, dependency traversal, deployment tags, and wheel RECORD,
binary and bytecode rejection. Actual automatic loading remains a required
packaging step on the matching macOS architecture.
