#!/usr/bin/env python3
"""Build pinned stock/enhanced Gecode binary/native benchmarks and focused tests.

Requires Python 3.12+, Git, CMake, and a C++17 compiler. Missing HiGHS sources
are cloned locally; nothing is installed system-wide. --skip-libraries reuses
existing libraries after source and CMake-cache verification, then rebuilds
the drivers/tests. It does not establish the provenance of reused binaries;
their hashes and caches are recorded so this choice remains explicit.
"""
import argparse
import hashlib
import io
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

BASELINE = "3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e"
HIGHS_COMMIT = "04024d701f79feb8e2f18bc3df0dffc04ef05088"
HIGHS_TAG = "v1.15.1"
HIGHS_URL = "https://github.com/ERGO-Code/HiGHS.git"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build/solver-bench"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Runner:
    def __init__(self, metadata):
        self.commands = metadata["commands"]

    def __call__(self, command, capture=False):
        argv = list(map(str, command))
        print(shlex.join(argv), flush=True)
        entry = {"argv": argv, "cwd": str(ROOT)}
        self.commands.append(entry)
        start = time.perf_counter()
        result = subprocess.run(argv, cwd=ROOT, check=False,
                                stdout=subprocess.PIPE if capture else None)
        entry.update(returncode=result.returncode,
                     elapsed_seconds=time.perf_counter()-start)
        result.check_returncode()
        return result.stdout


def extract_if_missing(source, archive):
    if source.exists():
        return
    source.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="stock-extract-", dir=source.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
            handle.extractall(temporary, filter="data")
        temporary.rename(source)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def verify_archive(source, archive, allowed_extra_roots=()):
    """Check actual bytes, not a marker that could outlive source edits."""
    expected = set()
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        for member in handle.getmembers():
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("Unexpected path in pinned Git archive")
            actual = source / relative
            expected.add(relative.as_posix())
            if member.isfile():
                content = handle.extractfile(member)
                if (actual.is_symlink() or not actual.is_file() or
                        file_hash(actual) != digest(content.read())):
                    raise RuntimeError(f"Pinned source differs: {actual}")
            elif member.issym():
                if not actual.is_symlink() or os.readlink(actual) != member.linkname:
                    raise RuntimeError(f"Pinned source symlink differs: {actual}")
            elif not member.isdir():
                raise RuntimeError(f"Unsupported archive entry: {member.name}")
    ignored = [source / ".git"]
    ignored.extend(path for path in allowed_extra_roots if path != source)
    for parent, directories, files in os.walk(source, followlinks=False):
        parent = Path(parent)
        directories[:] = [name for name in directories
                          if not any((parent/name).is_relative_to(p) for p in ignored)]
        for name in files + [name for name in directories if (parent/name).is_symlink()]:
            path = parent/name
            if any(path.is_relative_to(p) for p in ignored):
                continue
            if path.relative_to(source).as_posix() not in expected:
                raise RuntimeError(f"Unexpected file in pinned source: {path}")
    return {"archive_sha256": digest(archive), "verified_entries": len(expected),
            "ignored_extra_paths": [str(path) for path in ignored]}


def prepare_highs(source, build, run):
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix="highs-clone-", dir=source.parent))
        try:
            run(["git", "clone", "--depth", "1", "--branch", HIGHS_TAG,
                 HIGHS_URL, temporary])
            commit = run(["git", "-C", temporary, "rev-parse", "HEAD"], True).decode().strip()
            if commit != HIGHS_COMMIT:
                raise RuntimeError(f"HiGHS tag resolves to unexpected commit: {commit}")
            temporary.rename(source)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    commit = run(["git", "-C", source, "rev-parse", "HEAD"], True).decode().strip()
    if commit != HIGHS_COMMIT:
        raise RuntimeError(f"HiGHS must be at {HIGHS_COMMIT}; found {commit}")
    archive = run(["git", "-C", source, "archive", HIGHS_COMMIT], True)
    return verify_archive(source, archive, (build,))


def cache_values(build):
    values = {}
    for line in (build/"CMakeCache.txt").read_text().splitlines():
        if line and not line.startswith(("#", "//")) and "=" in line:
            key, value = line.split("=", 1)
            values[key.split(":", 1)[0]] = value
    return values


def verify_cache(build, source, options):
    values = cache_values(build)
    if Path(values.get("CMAKE_HOME_DIRECTORY", "")).resolve() != source:
        raise RuntimeError(f"CMake cache belongs to another source: {build}")
    for key, expected in options.items():
        actual = values.get(key)
        if expected in ("ON", "OFF"):
            actual = "ON" if str(actual).upper() in ("1", "ON", "TRUE", "YES") else "OFF" if actual is not None else None
        if actual != expected:
            raise RuntimeError(f"CMake cache {build}: {key}={actual}, expected {expected}")
    return {"sha256": file_hash(build/"CMakeCache.txt"), "values": values}


def source_hashes(run):
    paths = run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], True)
    result = {}
    for name in paths.decode().split("\0"):
        if not name:
            continue
        relative = Path(name)
        if any(part in {"build", "results", "instances", "native-instances", "__pycache__"} for part in relative.parts):
            continue
        path = ROOT/relative
        if path.is_symlink():
            result[name] = {"symlink": os.readlink(path)}
        elif path.is_file():
            result[name] = file_hash(path)
        else:
            result[name] = {"missing": True}
    return {"tree_sha256": digest(json.dumps(result, sort_keys=True).encode()), "files": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in {
            "stock-source": BUILD/"stock-source", "stock-build": BUILD/"stock",
            "modified-build": BUILD/"modified", "highs-source": BUILD/"deps/HiGHS",
            "highs-build": BUILD/"deps/HiGHS-build", "out": BUILD/"bin"}.items():
        parser.add_argument("--"+name, type=Path, default=default)
    parser.add_argument("--skip-libraries", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    cmake = shutil.which("cmake")
    compiler = shutil.which("clang++") or shutil.which("c++")
    if not cmake or not compiler or not shutil.which("git"):
        parser.error("Git, CMake, and a C++ compiler must be on PATH")
    args.out.mkdir(parents=True, exist_ok=True)
    metadata = {"status": "building", "started_utc": datetime.now(timezone.utc).isoformat(),
                "baseline_commit": BASELINE, "highs_commit": HIGHS_COMMIT,
                "highs_tag": HIGHS_TAG, "highs_url": HIGHS_URL,
                "platform": platform.platform(), "machine": platform.machine(),
                "skip_libraries": args.skip_libraries, "commands": [],
                "paths": {k: str(v) for k, v in vars(args).items() if isinstance(v, Path)}}
    run = Runner(metadata)
    try:
        metadata["compiler"] = run([compiler, "--version"], True).decode()
        metadata["cmake"] = run([cmake, "--version"], True).decode()
        archive = run(["git", "archive", BASELINE], True)
        extract_if_missing(args.stock_source, archive)
        metadata["stock_source_verification"] = verify_archive(
            # Earlier experiments may live beside this pristine checkout.
            # The pinned upstream CMake does not build experiments/; every
            # upstream source/header and all additional solver files are
            # still verified. Drivers always come from HERE, not this tree.
            args.stock_source, archive, (args.stock_build, args.stock_source/"experiments"))
        metadata["highs_source_verification"] = prepare_highs(
            args.highs_source, args.highs_build, run)
        metadata["modified_sources"] = source_hashes(run)
        metadata["modified_git_head"] = run(["git", "rev-parse", "HEAD"], True).decode().strip()

        # Keep the iteration's selected policy and header-only extensions,
        # which can change later without rebuilding the shared libraries.
        snapshot_paths = [HERE/"driver.cpp", HERE/"native-driver.cpp",
                          HERE/"policy.hpp", HERE/"build.py"]
        snapshot_paths.extend(sorted((ROOT/"gecode/minimodel").glob("lp-*.hpp")))
        snapshot_paths.extend(ROOT/name for name in
                              ("gecode/search.hh", "gecode/search/options.hpp",
                               "gecode/search/seq/bab.hpp", "gecode/search/seq/dfs.hpp"))
        snapshot_hashes = {}
        for path in snapshot_paths:
            relative = path.relative_to(ROOT)
            destination = args.out/"source"/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            snapshot_hashes[relative.as_posix()] = file_hash(destination)
        metadata["source_snapshot"] = {"root": str(args.out/"source"),
                                       "files": snapshot_hashes}

        gecode = {"CMAKE_BUILD_TYPE": "Release", "BUILD_SHARED_LIBS": "OFF",
                  "GECODE_BUILD_SHARED": "OFF", "GECODE_BUILD_STATIC": "ON",
                  "BUILD_TESTING": "OFF", "GECODE_ENABLE_MINIMODEL": "ON",
                  "GECODE_ENABLE_SEARCH": "ON", "GECODE_ENABLE_INT_VARS": "ON"}
        for feature in ("EXAMPLES", "QT", "GIST", "CPPROFILER", "SET_VARS",
                        "FLOAT_VARS", "DRIVER", "FLATZINC", "MPFR"):
            gecode["GECODE_ENABLE_"+feature] = "OFF"
        highs = {"CMAKE_BUILD_TYPE": "Release", "BUILD_SHARED_LIBS": "OFF",
                 "BUILD_SHARED_EXTRAS_LIB": "OFF", "BUILD_CXX": "ON",
                 "BUILD_CXX_EXE": "OFF", "BUILD_TESTING": "OFF",
                 "BUILD_EXAMPLES": "OFF", "HIPO": "OFF", "ZLIB": "OFF"}
        if platform.system() == "Darwin":
            gecode["CMAKE_OSX_DEPLOYMENT_TARGET"] = "15.7"
            highs["CMAKE_OSX_DEPLOYMENT_TARGET"] = "15.7"
        modified = dict(gecode, GECODE_ENABLE_LP_RELAXATION="ON",
                        highs_DIR=str(args.highs_build))
        builds = [(args.highs_source, args.highs_build, highs, ["highs", "highs_extras"]),
                  (args.stock_source, args.stock_build, gecode,
                   ["gecodeminimodel_static", "gecodesearch_static"]),
                  (ROOT, args.modified_build, modified,
                   ["gecodeminimodel_static", "gecodesearch_static"])]
        metadata["cmake_options"] = {"highs": highs, "stock": gecode, "modified": modified}
        for source, build, options, targets in builds:
            if not args.skip_libraries:
                run([cmake, "-S", source, "-B", build,
                     "-DCMAKE_CXX_COMPILER="+compiler,
                     *[f"-D{key}={value}" for key, value in options.items()]])
                run([cmake, "--build", build, "--parallel", args.jobs, "--target", *targets])
            metadata.setdefault("library_caches", {})[str(build)] = verify_cache(build, source, options)

        gecode_names = ["minimodel", "int", "search", "kernel", "support"]
        stock_libs = [args.stock_build/f"libgecode{name}.a" for name in gecode_names]
        modified_libs = [args.modified_build/f"libgecode{name}.a" for name in gecode_names]
        highs_libs = [args.highs_build/"lib/libhighs.a", args.highs_build/"lib/libhighs_extras.a"]
        metadata["library_hashes"] = {str(path): file_hash(path)
                                      for path in stock_libs+modified_libs+highs_libs}
        common = [compiler, "-std=c++17", "-O3", "-DNDEBUG", "-DGECODE_NO_AUTOLINK"]
        if platform.system() == "Darwin":
            common.append("-mmacosx-version-min=15.7")
        metadata["compiler_flags"] = common

        def compile_binary(name, source, includes, libraries, defines=()):
            run([*common, *defines, *["-I"+str(path) for path in includes], source,
                 *libraries, "-pthread", "-o", args.out/name])

        # Both binary executables compile the same driver and native model
        # builder. Stock headers/configuration precede ROOT's shared builder.
        stock_includes = [args.stock_build, args.stock_source, ROOT]
        lp_includes = [args.modified_build, ROOT, args.highs_build, args.highs_source/"highs"]
        compile_binary("stock-binary", HERE/"driver.cpp", stock_includes, stock_libs)
        compile_binary("enhanced-binary", HERE/"driver.cpp", lp_includes,
                       modified_libs+highs_libs, ["-DWITH_LP"])
        compile_binary("stock-native", HERE/"native-driver.cpp", stock_includes, stock_libs)
        compile_binary("enhanced-native", HERE/"native-driver.cpp",
                       [args.modified_build, ROOT], modified_libs)
        previous_tests = HERE.parent/"lp-relaxation/tests"
        compile_binary("test-certificate", previous_tests/"certificate.cpp", [ROOT], [])
        for name in ("backend", "propagator"):
            compile_binary("test-"+name, previous_tests/(name+".cpp"),
                           lp_includes, modified_libs+highs_libs)
        compile_binary("test-reduced-cost", ROOT/"solver-bench/tests/reduced_cost.cpp",
                       lp_includes, modified_libs+highs_libs)
        compile_binary("test-strengthening", HERE/"tests/strengthening.cpp",
                       [args.modified_build, ROOT], modified_libs)
        compile_binary("test-primal", HERE/"tests/primal.cpp",
                       lp_includes, modified_libs+highs_libs)
        binaries = ("stock-binary", "enhanced-binary", "stock-native", "enhanced-native",
                    "test-certificate", "test-backend", "test-propagator",
                    "test-reduced-cost", "test-strengthening", "test-primal")
        metadata["binary_hashes"] = {name: file_hash(args.out/name) for name in binaries}
        for name, expected in snapshot_hashes.items():
            if file_hash(ROOT/name) != expected:
                raise RuntimeError(f"Build input changed during compilation: {name}")
        metadata["status"] = "built"
    except Exception as error:
        metadata["status"] = "failed"
        metadata["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(metadata, indent=2, sort_keys=True)+"\n"
        (args.out/"build-metadata.json").write_text(payload)
        (HERE/"results").mkdir(exist_ok=True)
        (HERE/"results/build-metadata.json").write_text(payload)


if __name__ == "__main__":
    main()
