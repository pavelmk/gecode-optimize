#!/usr/bin/env python3
"""Build the final driver against the separately validated current runtime.

Uses the ordinary benchmark target's recorded compiler and compile flags.
Never invokes CMake or rebuilds/rewrites any solver library. The new executable
and build provenance are placed in build/final-benchmark by default.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, default=ROOT/'build/native-structure/native-build')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'build/final-benchmark')
    args = parser.parse_args()
    runtime = args.runtime_build.resolve()
    output = args.output_dir.resolve()
    flags_path = runtime/'gecode/optimize/CMakeFiles/optimize-native-benchmark.dir/flags.make'
    link_path = flags_path.with_name('link.txt')
    flags = flags_path.read_text()
    compiler = next(line.removeprefix('# compile CXX with ') for line in flags.splitlines()
                    if line.startswith('# compile CXX with '))
    settings = {}
    for line in flags.splitlines():
        if line.startswith(('CXX_DEFINES =', 'CXX_INCLUDES =', 'CXX_FLAGS =')):
            name, value = line.split('=', 1)
            settings[name.strip()] = shlex.split(value)
    source = ROOT/'experiments/optimize/final_benchmark.cpp'
    library = runtime/'gecode/optimize/libgecodeoptimize.dylib'
    libraries = sorted({path.resolve() for path in runtime.glob('libgecode*.dylib')} |
                       {library.resolve()})
    before = {str(path): sha(path) for path in libraries}
    output.mkdir(parents=True, exist_ok=True)
    binary = output/'optimize-final-benchmark'
    command = ([compiler] + settings['CXX_DEFINES'] + settings['CXX_INCLUDES'] +
               settings['CXX_FLAGS'] + [str(source), '-o', str(binary), str(library),
               '-Wl,-search_paths_first', '-Wl,-headerpad_max_install_names',
               '-Wl,-rpath,'+str(library.parent), '-Wl,-rpath,'+str(runtime)])
    subprocess.run(command, cwd=ROOT, check=True)
    after = {str(path): sha(path) for path in libraries}
    if before != after:
        raise RuntimeError('Accepted runtime libraries changed during driver-only build')
    manifest = {'schema_version': 1, 'source': str(source), 'source_sha256': sha(source),
                'binary': str(binary), 'binary_sha256': sha(binary),
                'compiler_flags_metadata': str(flags_path), 'flags_sha256': sha(flags_path),
                'link_metadata': str(link_path), 'link_metadata_sha256': sha(link_path),
                'command': command, 'runtime_libraries_sha256': before,
                'runtime_libraries_unchanged': True}
    (output/'build.local.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'binary': str(binary), 'manifest': str(output/'build.local.json'),
                      'runtime_libraries_unchanged': True}))


if __name__ == '__main__':
    main()
