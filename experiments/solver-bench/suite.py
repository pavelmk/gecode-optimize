#!/usr/bin/env python3
"""Run reproducible local benchmark presets without network access or implicit builds."""
import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preset', choices=['quick', 'development', 'test', 'public', 'cold', 'scale', 'flatzinc'])
    parser.add_argument('--bin', type=Path, default=ROOT/'build/solver-bench/bin')
    parser.add_argument('--output-dir', type=Path, default=HERE/'results/local')
    parser.add_argument('--configs', help='Override the preset configurations')
    parser.add_argument('--limit-ms', type=float)
    parser.add_argument('--repeats', type=int)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    configs = 'stock,lp,portfolio'
    repeats, cutoff, warm = 3, 2000, 1
    extra = []
    if args.preset == 'quick':
        # One fixed development seed per representation, at the small size.
        ids = []
        for name in ('manifest.json', 'native-manifest.json', 'rcpsp-manifest.json'):
            grouped = {}
            for item in json.loads((HERE/name).read_text())['instances']:
                if item['split'] == 'dev' and item['tier'] == 'small':
                    grouped.setdefault(item['family'], []).append(item)
            ids.extend(min(values, key=lambda r:r['seed'])['id'] for values in grouped.values())
        extra = ['--split', 'dev', '--ids', ','.join(sorted(ids))]
        repeats, cutoff, configs = 1, 250, 'stock,portfolio'
    elif args.preset == 'development':
        extra = ['--split', 'dev', '--kinds', 'binary']
        repeats, cutoff = 1, 1000
        configs = 'stock,lp,fix4,fix8,cuts-fix4,lns-fix4,pump-fix4'
    elif args.preset == 'cold':
        extra = ['--split', 'test']
        configs, warm = 'stock,portfolio', 0
    elif args.preset == 'scale':
        extra = ['--split', 'scale', '--manifest', str(HERE/'scale-manifest.json')]
        configs = 'stock,portfolio'
    elif args.preset == 'flatzinc':
        cutoff = 1000
    else:
        extra = ['--split', args.preset]
    repeats = args.repeats if args.repeats is not None else repeats
    cutoff = args.limit_ms if args.limit_ms is not None else cutoff
    destination = args.output_dir/(args.preset+'.jsonl')
    command = [sys.executable, str(HERE/('fzn-bench.py' if args.preset == 'flatzinc' else 'bench.py')),
               '--bin', str(args.bin.resolve()), '--output', str(destination.resolve()),
               '--limit-ms', str(cutoff), '--repeats', str(repeats)]
    if args.preset != 'flatzinc':
        command += ['--configs', args.configs or configs, '--warm', str(warm), *extra]
    elif args.configs:
        parser.error('FlatZinc uses its fixed stock/enhanced compatibility pair')
    if args.resume:
        command.append('--resume')
    print(shlex.join(command), flush=True)
    if not args.dry_run:
        subprocess.run(command, check=True, cwd=HERE)


if __name__ == '__main__':
    main()
