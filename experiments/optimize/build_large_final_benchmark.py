#!/usr/bin/env python3
"""Expand transport guards in a generated copy of the frozen final driver.

Assignment size 128 produces 16384 binary variables, exceeding the original
10000-variable parser guard after size 64 was solved. Such a harness rejection
is not a measured solver limit. This driver-only amendment changes six explicit
parser constants; algorithms, options, ten-second solve budgets and JSON schema
are unchanged. The original source and all solver libraries remain immutable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


TRANSFORMATIONS=(
    ('bytes > 4*1024*1024','bytes > 256*1024*1024','TXT byte allowance: 4 MiB to 256 MiB'),
    ('input.integer(1, 10000)','input.integer(1, 1000000)','Binary variable allowance: 10000 to 1000000'),
    ('const auto m = static_cast<std::size_t>(input.integer(0, 100000));',
     'const auto m = static_cast<std::size_t>(input.integer(0, 10000000));',
     'Binary row allowance: 100000 to 10000000'),
    ('count > 2000000-total','count > 100000000-total','Nonzero allowance: 2000000 to 100000000'),
    ('input.integer(1, 100)','input.integer(1, 10000)','Global dimension allowance: 100 to 10000'),
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build',type=Path,default=ROOT/'build/native-structure/native-build')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/final-benchmark/large-driver')
    args=parser.parse_args();runtime=args.runtime_build.resolve(strict=True)
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    original=ROOT/'experiments/optimize/final_benchmark.cpp'
    original_hash=sha(original);text=original.read_text();changes=[]
    for before,after,reason in TRANSFORMATIONS:
        count=text.count(before);expected=2 if before=='input.integer(1, 100)' else 1
        if count!=expected:raise RuntimeError('Frozen guard changed: '+before)
        text=text.replace(before,after)
        changes.append(dict(before=before,after=after,occurrences=count,reason=reason))
    source=output/'final_benchmark_large.cpp';source.write_text(text)
    flags_path=runtime/'gecode/optimize/CMakeFiles/optimize-native-benchmark.dir/flags.make'
    link_path=flags_path.with_name('link.txt');flags=flags_path.read_text()
    compiler=next(line.removeprefix('# compile CXX with ') for line in flags.splitlines()
                  if line.startswith('# compile CXX with '))
    settings={}
    for line in flags.splitlines():
        if line.startswith(('CXX_DEFINES =','CXX_INCLUDES =','CXX_FLAGS =')):
            name,value=line.split('=',1);settings[name.strip()]=shlex.split(value)
    library=runtime/'gecode/optimize/libgecodeoptimize.dylib'
    libraries=sorted({p.resolve() for p in runtime.glob('libgecode*.dylib')}|{library.resolve()})
    before={str(p):sha(p) for p in libraries};binary=output/'optimize-final-benchmark'
    command=([compiler]+settings['CXX_DEFINES']+settings['CXX_INCLUDES']+settings['CXX_FLAGS']+
             [str(source),'-o',str(binary),str(library),'-Wl,-search_paths_first',
              '-Wl,-headerpad_max_install_names','-Wl,-rpath,'+str(library.parent),'-Wl,-rpath,'+str(runtime)])
    subprocess.run(command,cwd=ROOT,check=True)
    if before!={str(p):sha(p) for p in libraries} or sha(original)!=original_hash:
        raise RuntimeError('Original driver source or accepted solver libraries changed')
    manifest=dict(schema_version=1,source=str(source),source_sha256=sha(source),
        original_source=str(original),original_source_sha256=original_hash,
        source_transformations=changes,
        amendment='Expand driver transport guards after assignment128 exceeded the original parser allowance; no algorithm, search setting, solve budget or JSON schema changes.',
        binary=str(binary),binary_sha256=sha(binary),compiler_flags_metadata=str(flags_path),
        flags_sha256=sha(flags_path),link_metadata=str(link_path),link_metadata_sha256=sha(link_path),
        command=command,runtime_libraries_sha256=before,runtime_libraries_unchanged=True,
        original_source_unchanged=True)
    (output/'build.local.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(binary=str(binary),manifest=str(output/'build.local.json'),
                         runtime_libraries_unchanged=True,original_source_unchanged=True)))


if __name__=='__main__':main()
