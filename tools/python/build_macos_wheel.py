#!/usr/bin/env python3
"""Package a prebuilt, self-contained macOS C ABI library without downloads.

Requires the packaging and wheel Python packages, plus Apple's otool and lipo.
Builds are separate: this command neither compiles nor repairs dependency paths.
Only a thin library with system-only dependencies is accepted. A copied package
must pass an isolated automatic-load smoke test before a wheel is published to
the requested local output directory. No package index is contacted.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

from packaging.version import Version


ROOT = Path(__file__).resolve().parents[2]
ENTRY = "libgecodeoptimize_c.dylib"


def command(arguments, **kwargs):
    return subprocess.check_output([str(value) for value in arguments], text=True,
                                   stderr=subprocess.STDOUT, timeout=120, **kwargs)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_wheel(archive, binary):
    names = archive.namelist()
    if len(names) != len(set(names)) or any(name.startswith("/") or ".." in Path(name).parts for name in names):
        raise ValueError("invalid wheel member paths")
    if any(name.endswith((".pyc", ".pyo")) or "__pycache__" in Path(name).parts for name in names):
        raise ValueError("interpreter bytecode must not be included in a portable wheel")
    if archive.read("gecode_optimize/_native/" + ENTRY) != binary:
        raise ValueError("wheel changed the copied solver library")
    records = [name for name in names if name.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise ValueError("wheel must contain exactly one integrity record")
    rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode("utf-8"))))
    if any(len(row) != 3 for row in rows) or len({row[0] for row in rows}) != len(rows):
        raise ValueError("invalid wheel integrity record")
    if {row[0] for row in rows} != set(names):
        raise ValueError("wheel integrity record does not cover every member")
    for name, digest, size in rows:
        if name == records[0]:
            if digest or size:
                raise ValueError("RECORD must not hash itself")
            continue
        data = archive.read(name)
        expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
        if digest != expected or size != str(len(data)):
            raise ValueError("wheel integrity check failed: " + name)


def inspect_library(library):
    architectures = command(["lipo", "-archs", library]).split()
    if len(architectures) != 1 or architectures[0] not in ("arm64", "x86_64"):
        raise ValueError("first wheel builder requires one arm64 or x86_64 architecture")
    architecture = architectures[0]
    if architecture != platform.machine():
        raise ValueError("wheel must be checked on a host of the same architecture")
    identifiers = command(["otool", "-D", library]).splitlines()[1:]
    if len(identifiers) != 1:
        raise ValueError("input must be a Mach-O dynamic library with one install ID")
    dependencies = []
    for line in command(["otool", "-L", library]).splitlines()[1:]:
        name, separator, _ = line.strip().partition(" (compatibility version ")
        if not separator:
            raise ValueError("unrecognized Mach-O dependency record")
        if name == identifiers[0].strip():
            continue
        if (not name.startswith(("/usr/lib/", "/System/Library/"))
                or any(part in (".", "..") for part in name.split("/"))):
            raise ValueError("non-system dependency must be linked statically before packaging: " + name)
        dependencies.append(name)
    records = []
    current = {}
    for line in command(["otool", "-l", library]).splitlines():
        parts = line.split()
        if line.startswith("Load command "):
            if current:
                records.append(current)
            current = {}
        elif len(parts) == 2:
            current[parts[0]] = parts[1]
    if current:
        records.append(current)
    minimums = []
    for record in records:
        if record.get("cmd") == "LC_BUILD_VERSION":
            if record.get("platform") not in ("1", "macos"):
                raise ValueError("Mach-O target is not macOS")
            minimums.append(record["minos"])
        elif record.get("cmd") == "LC_VERSION_MIN_MACOSX":
            minimums.append(record["version"])
    if len(minimums) != 1:
        raise ValueError("input must declare exactly one macOS deployment target")
    version = tuple(int(part) for part in minimums[0].split("."))
    version = version + (0,) * (3 - len(version))
    if len(version) != 3 or version[0] < 10 or version[2] or (version[0] >= 11 and version[1]):
        raise ValueError("rebuild at a wheel-compatible deployment baseline, e.g. macOS 11.0; do not retag a newer binary")
    if architecture == "arm64" and version[0] < 11:
        raise ValueError("arm64 requires macOS 11 or newer")
    tag = "macosx_{}_{}_{}".format(version[0], version[1], architecture)
    return tag, {"architecture": architecture, "minimum_macos": minimums[0],
                 "system_dependencies": dependencies, "install_id": identifiers[0].strip()}


def stage_library(source, destination):
    # Inspect the exact captured bytes that will enter the wheel. Inspecting the
    # build output first can attach old architecture/deployment metadata to a
    # new binary when an independent build replaces it between those operations.
    with source.open("rb") as stream:
        binary = stream.read(512 * 1024 * 1024 + 1)
    if len(binary) > 512 * 1024 * 1024:
        raise ValueError("input library exceeds the 512 MiB packaging limit")
    destination.write_bytes(binary)
    os.chmod(destination, 0o755)
    tag, properties = inspect_library(destination)
    return binary, tag, properties


def copy_licenses(root, highs, destination):
    entries = [
        (root / "LICENSE", "Gecode-LICENSE"),
        (root / "gecode/third-party/boost/LICENSE_1_0.txt", "Boost-LICENSE"),
        (highs / "LICENSE.txt", "HiGHS-LICENSE"),
        (highs / "highs/io/filereaderlp/LICENSE", "HiGHS-filereaderlp-LICENSE"),
        (highs / "extern/zstr/LICENSE", "HiGHS-zstr-LICENSE"),
        (highs / "extern/rcm/LICENSE", "HiGHS-rcm-LICENSE"),
        (highs / "extern/pdqsort/license.txt", "HiGHS-pdqsort-LICENSE"),
        (highs / "extern/metis/LICENSE.txt", "HiGHS-metis-LICENSE"),
    ]
    destination.mkdir()
    for source, name in entries:
        if not source.is_file():
            raise ValueError("required dependency notice is missing: " + str(source))
        shutil.copyfile(source, destination / name)
    return [name for _, name in entries]


SMOKE = r'''
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import gecode_optimize as g
assert pathlib.Path(g.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve())
library = g.load_library()
assert library.capabilities(g.Backend.HIGHS)["available"]
assert library.capabilities(g.Backend.NATIVE)["available"]
with g.Model(library) as model:
    x = model.add_variable(g.VariableType.INTEGER, 0, 5)
    model.set_objective([(x, 2)], offset=3)
    for backend, guarantee in ((g.Backend.HIGHS, g.Guarantee.NUMERICAL),
                                (g.Backend.NATIVE, g.Guarantee.EXACT)):
        with model.solve(g.Options(backend=backend, guarantee=guarantee)) as result:
            assert result.termination == g.Termination.OPTIMAL and result.has_solution
            assert result.value(x) == 0 and result.objective == 3
print(json.dumps({"automatic_load": True, "numerical_and_native": True}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--highs-source", type=Path)
    parser.add_argument("--version", default="0.1.0.dev0")
    parser.add_argument("--allow-dirty", action="store_true", help="record a dirty source checkout for local development only")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("this first builder supports macOS only; Linux/Windows require separate audited recipes")
    root = args.source_root.resolve(strict=True)
    library = args.library.resolve(strict=True)
    if not library.is_file() or library.stat().st_size > 512 * 1024 * 1024:
        parser.error("input must be a regular shared library no larger than 512 MiB")
    highs = (args.highs_source or root.parent / "deps/HiGHS").resolve(strict=True)
    dependency = json.loads((root / "docs/solver-parity/dependencies.json").read_text())
    highs_head = command(["git", "rev-parse", "HEAD"], cwd=highs).strip()
    if highs_head != dependency["commit"] or command(["git", "status", "--porcelain"], cwd=highs).strip():
        parser.error("HiGHS source/notices must match the clean pinned dependency")
    version = str(Version(args.version))
    head = command(["git", "rev-parse", "HEAD"], cwd=root).strip()
    dirty = bool(command(["git", "status", "--porcelain"], cwd=root).strip())
    if dirty and not args.allow_dirty:
        parser.error("commit the source snapshot before packaging, or explicitly use --allow-dirty for local development")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gecode-wheel-", dir=output) as temporary:
        work = Path(temporary)
        tree = work / "tree"
        package = tree / "gecode_optimize"
        native = package / "_native"
        native.mkdir(parents=True)
        binary, tag, properties = stage_library(library, native / ENTRY)
        filename = "gecode_optimize-{}-py3-none-{}.whl".format(version, tag)
        target = output / filename
        if target.exists():
            raise FileExistsError("refusing to replace existing wheel: " + str(target))
        sources = {}
        for source in sorted((root / "python/gecode_optimize").rglob("*.py")):
            relative = source.relative_to(root / "python/gecode_optimize")
            if "__pycache__" in relative.parts or "_native" in relative.parts:
                continue
            data = source.read_bytes()
            (package / relative).parent.mkdir(parents=True, exist_ok=True)
            (package / relative).write_bytes(data)
            sources[str(relative)] = sha(data)
        if not (package / "__init__.py").is_file() or not (package / "_runtime.py").is_file():
            raise ValueError("Python source package or bundled runtime helper is missing")
        detail = dict(schema_version=1, source_head=head, source_dirty=dirty,
                      python_sources=sources, library_sha256=sha(binary),
                      highs_source_commit=highs_head, properties=properties,
                      note="Prebuilt library; binary hash and smoke checks do not prove build provenance or older-OS compatibility")
        (native / "build-details.json").write_text(json.dumps(detail, indent=2) + "\n")
        dist_info = tree / ("gecode_optimize-" + version + ".dist-info")
        dist_info.mkdir()
        licenses = copy_licenses(root, highs, dist_info / "licenses")
        metadata = ["Metadata-Version: 2.4", "Name: gecode-optimize", "Version: " + version,
                    "Summary: Gecode optimization API with bundled native and HiGHS solvers",
                    "Requires-Python: >=3.9"]
        metadata += ["License-File: licenses/" + name for name in licenses]
        (dist_info / "METADATA").write_text("\n".join(metadata) + "\n\nLocal experimental distribution. No runtime downloads.\n")
        (dist_info / "WHEEL").write_text("Wheel-Version: 1.0\nGenerator: gecode-local-wheel\nRoot-Is-Purelib: false\nTag: py3-none-" + tag + "\n")
        env = dict(os.environ)
        for name in ("GECODE_OPTIMIZE_LIBRARY", "PYTHONPATH", "PYTHONHOME",
                     "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES"):
            env.pop(name, None)
        smoke = json.loads(command([sys.executable, "-I", "-B", "-c", SMOKE, tree], cwd=work, env=env))
        packed = work / "packed"
        packed.mkdir()
        command([sys.executable, "-m", "wheel", "pack", tree, "--dest-dir", packed])
        built = packed / filename
        if not built.is_file():
            raise ValueError("wheel tool produced an unexpected platform/version tag")
        with zipfile.ZipFile(built) as archive:
            check_wheel(archive, binary)
        if sha(library.read_bytes()) != sha(binary):
            raise ValueError("input library changed during packaging; rebuild from a frozen binary")
        # Same-filesystem exclusive link publishes only the fully checked wheel.
        os.link(built, target)
        print(json.dumps(dict(wheel=str(target), sha256=sha(target.read_bytes()),
                              tag="py3-none-" + tag, smoke=smoke, build_details=detail)))


if __name__ == "__main__":
    main()
