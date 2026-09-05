#!/usr/bin/env python3
"""Separate stock BoolVar/IntVar representation sensitivity track.

Delegates scheduling, input/witness validation, cutoff accounting and immutable
batch metadata to the unchanged adjacent bench.py. No builds or downloads.
Default actions: stock (IntVar), stock-bool (BoolVar), portfolio (enhanced).
The new executable must be built separately against pristine stock libraries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bench

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    # Only parse fields needed to constrain this bridge. bench.main owns the
    # full parser, including output existence/resume and all normal filters.
    parser=argparse.ArgumentParser(add_help=False,allow_abbrev=False)
    parser.add_argument('--kinds',default='binary')
    parser.add_argument('--configs',default='stock,stock-bool,portfolio')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--bin',type=Path,default=bench.ROOT/'build/solver-bench/bin')
    parser.add_argument('--resume',action='store_true')
    options,_=parser.parse_known_args()
    if options.kinds!='binary':
        parser.error('The Boolean representation track supports --kinds binary only')
    configurations=options.configs.split(',')
    if (set(configurations)!={'stock','stock-bool','portfolio'} or len(configurations)!=3):
        parser.error('Use the three paired actions stock,stock-bool,portfolio (order may vary)')
    if not options.output:
        # Let the original parser print its help/required argument diagnostic.
        if not any(arg in ('--help','-h') for arg in sys.argv[1:]):
            parser.error('--output is required; use a separate sensitivity-track path')
    arguments=sys.argv[1:]
    if not any(arg=='--kinds' or arg.startswith('--kinds=') for arg in arguments):
        sys.argv+=['--kinds','binary']
    if not any(arg=='--configs' or arg.startswith('--configs=') for arg in arguments):
        sys.argv+=['--configs',options.configs]
    bench.CONFIGS['stock-bool']=('stock-bool','native','afc','stock-native')

    sidecar=None
    if options.output:
        sidecar=options.output.with_suffix('.bool-wrapper.json')
        provenance={
            'schema_version':1,
            'track':'Stock Boolean representation sensitivity; separate from frozen primary benchmark',
            'wrapper_sha256':sha(__file__),
            'shared_runner_sha256':sha(HERE/'bench.py'),
            'driver_source_sha256':sha(HERE/'stock-bool-driver.cpp'),
            'matrix_header_sha256':sha(bench.ROOT/'gecode/minimodel/lp-model.hpp'),
            'driver_source_scope':'Current source hash, not a claim that this source produced an unverified executable',
            'configurations':configurations,
            'semantics':'Same original matrix and objective; stock IntVar vs stock BoolVar posting; common supplied witness; AFC variable order and objective-aware values',
            'binary_hashes':{name:sha(options.bin/name) for name in ('stock-binary','stock-bool','enhanced-binary')},
            'lp_in_stock_bool':False,
            'timing':'Same solver timing boundary; Boolean driver additionally checks final assignment outside solver time',
        }
        build_evidence=options.bin/'stock-bool-build.json'
        if build_evidence.exists():
            provenance['stock_bool_build_metadata_sha256']=sha(build_evidence)
        if options.resume:
            if not sidecar.exists() or json.loads(sidecar.read_text())!=provenance:
                raise ValueError('Cannot resume after Boolean-wrapper/source/build identity change')
        else:
            if sidecar.exists() or options.output.exists():
                raise ValueError('Sensitivity output already exists; use --resume or a new output path')
            sidecar.parent.mkdir(parents=True,exist_ok=True)
            sidecar.write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n')
    bench.main()


if __name__=='__main__':
    main()
