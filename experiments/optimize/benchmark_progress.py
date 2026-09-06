#!/usr/bin/env python3
"""Bounded pre-project/current benchmark using existing macOS binaries.

No builds, source modifications or downloads. Run only during a quiet window.
A relocation-friendly reproduction of the measured 2026-09-05 panel; original
raw records identify the exact measured script hash. Requires the preserved
pre-project binary manifests and conventional combined current build layout.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def capture_command(
    command, directory, environment, timeout, max_output=4 * 1024 * 1024
):
    """Capture trusted POSIX fixtures with bounded memory and group cleanup.

    Temporary files avoid pipe hangs from descendants and unbounded communicate
    buffering. The output allowance is checked during polling and after exit;
    only its bounded prefix is loaded or returned. Ordinary descendants retain
    the child's process group; programs deliberately escaping it are outside
    this benchmark harness. Cleanup can take up to 0.5 seconds after the deadline.
    """
    if os.name != 'posix':
        raise ValueError('POSIX process-group containment is required')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    if type(max_output) is not int or max_output <= 0:
        raise ValueError('max_output must be a positive integer')
    started = time.perf_counter()
    finish = time.monotonic() + timeout
    proc = None
    timed_out = False
    oversized = False
    with tempfile.TemporaryFile(dir=directory) as stdout, tempfile.TemporaryFile(
        dir=directory
    ) as stderr:
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                cwd=directory,
                env=environment,
                start_new_session=True,
                close_fds=True,
            )
            while True:
                oversized = (
                    max(
                        os.fstat(stdout.fileno()).st_size,
                        os.fstat(stderr.fileno()).st_size,
                    )
                    > max_output
                )
                timed_out = time.monotonic() >= finish
                if oversized or timed_out or proc.poll() is not None:
                    break
                time.sleep(min(0.002, max(0, finish - time.monotonic())))
        finally:
            if proc is not None:
                # The leader may already have exited while descendants still
                # hold inherited descriptors; always terminate the whole group.
                cleanup_deadline = time.monotonic() + 0.5
                retry_group = False
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    retry_group = True
                finally:
                    try:
                        proc.wait(timeout=max(0, cleanup_deadline-time.monotonic()))
                    except subprocess.TimeoutExpired as error:
                        raise RuntimeError(
                            'benchmark child cleanup deadline exceeded'
                        ) from error
                if retry_group:
                    # Darwin can return EPERM while an exiting leader is not
                    # yet waitable, or for a zombie-only group. The single wait
                    # above must finish before retrying group termination once.
                    # Reaping a leader alone does not prove descendants gone.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        sizes = [os.fstat(stream.fileno()).st_size for stream in (stdout, stderr)]
        oversized = oversized or max(sizes) > max_output
        stdout.seek(0)
        stderr.seek(0)
        result = {
            'returncode': proc.returncode,
            'hard_timeout': timed_out,
            'output_limit': oversized,
            'stdout_bytes_observed': sizes[0],
            'stderr_bytes_observed': sizes[1],
            'stdout': stdout.read(max_output),
            'stderr': stderr.read(max_output),
            'external_seconds': time.perf_counter() - started,
        }
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--before-source',
        type=Path,
        required=True,
        help='Read-only pre-project checkout containing original inputs',
    )
    parser.add_argument(
        '--before-binary-dir',
        type=Path,
        help='Directory containing enhanced-binary, enhanced-fzn and their build manifests; default BEFORE_SOURCE/build/solver-bench/bin',
    )
    parser.add_argument(
        '--current-build',
        type=Path,
        default=ROOT / 'build/native-compat',
        help='Existing combined shared build; default build/native-compat',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        required=True,
        help='New result directory; refuses overwrite',
    )
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument(
        '--seconds', type=float, default=2, help='Internal solver limit, seconds (0,5]'
    )
    parser.add_argument(
        '--budget-seconds', type=float, default=180, help='Whole-call limit (0,300]'
    )
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        parser.error(
            'This reproduction uses verified macOS dyld provenance; other platforms need their own loader verification'
        )
    if not 1 <= args.repetitions <= 5:
        parser.error('repetitions must be in [1,5]')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 5:
        parser.error('seconds must be finite in (0,5]')
    if not math.isfinite(args.budget_seconds) or not 0 < args.budget_seconds <= 300:
        parser.error('budget-seconds must be finite in (0,300]')
    if args.seconds * 1000 != round(args.seconds * 1000):
        parser.error('seconds must be an integral number of milliseconds')
    HERE = args.output_dir.resolve()
    OLD = args.before_source.resolve(strict=True)
    BEFORE_BIN = (args.before_binary_dir or OLD / 'build/solver-bench/bin').resolve(
        strict=True
    )
    CURRENT = args.current_build.resolve(strict=True)
    LIMIT = args.seconds
    HARD_LIMIT = LIMIT + 1.5
    REPETITIONS = args.repetitions
    SUITE = ROOT / 'experiments/solver-bench'
    sys.path.insert(0, str(SUITE))
    import miplib_import, validate, public_catalog

    spec = importlib.util.spec_from_file_location('fznb', SUITE / 'fzn-bench.py')
    fznb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fznb)
    BIN = {
        'mip': {
            'before': BEFORE_BIN / 'enhanced-binary',
            'now': CURRENT / 'bin/optimize-file',
        },
        'native_cp': {
            'before': BEFORE_BIN / 'enhanced-fzn',
            'now': CURRENT / 'bin/fzn-gecode',
        },
    }
    LIBDIRS = [CURRENT / 'gecode/optimize', CURRENT]

    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def dump(p, x):
        p.write_text(json.dumps(x, indent=2, allow_nan=False) + '\n')

    def env(cohort, trace=False):
        e = {k: v for k, v in os.environ.items() if not k.startswith('DYLD_')}
        e['PYTHONDONTWRITEBYTECODE'] = '1'
        if cohort == 'now':
            e['DYLD_LIBRARY_PATH'] = ':'.join(map(str, LIBDIRS))
        if trace:
            e['DYLD_PRINT_LIBRARIES'] = '1'
        return e

    START = time.monotonic()
    DEADLINE = START + args.budget_seconds
    DEST = HERE
    DEST.mkdir(parents=True, exist_ok=False)
    report = {
        'schema_version': 1,
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'pre_project_to_current_bounded_comparison',
        'source_head': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True
        ).strip(),
        'platform': platform.platform(),
        'machine': platform.machine(),
        'whole_budget_seconds': args.budget_seconds,
        'per_solve_seconds': LIMIT,
        'hard_process_seconds': HARD_LIMIT,
        'repetitions': REPETITIONS,
        'warm_start': False,
        'records': [],
        'provenance': {},
        'inputs': {},
    }

    def run(cmd, cohort, label, trace=False):
        remaining = DEADLINE - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('Whole comparison budget exhausted')
        utc_start = datetime.now(timezone.utc).isoformat()
        captured = capture_command(
            cmd, HERE, env(cohort, trace), min(HARD_LIMIT, remaining)
        )
        out, err = captured.pop('stdout'), captured.pop('stderr')
        (DEST / (label + '.stdout')).write_bytes(out)
        (DEST / (label + '.stderr')).write_bytes(err)
        return (
            dict(
                captured,
                command=cmd,
                started_utc=utc_start,
                finished_utc=datetime.now(timezone.utc).isoformat(),
                stdout_path=label + '.stdout',
                stderr_path=label + '.stderr',
            ),
            out.decode(errors='replace'),
            err.decode(errors='replace'),
        )

    def finite(x):
        if not math.isfinite(float(x)):
            raise ValueError('Nonfinite JSON')
        return float(x)

    def load(s):
        return json.loads(
            s,
            parse_constant=lambda s: (_ for _ in ()).throw(
                ValueError('Nonfinite JSON')
            ),
            parse_float=finite,
        )

    # Assertions are input/evidence guards here, not optional diagnostics.
    if not __debug__:
        raise RuntimeError(
            'Run without python -O; validation assertions must be enabled'
        )
    # Frozen original identities must match their existing build manifests.
    for track, meta, key in [
        ('mip', 'build-metadata.json', 'enhanced-binary'),
        ('native_cp', 'fzn-build-metadata.json', 'enhanced-fzn'),
    ]:
        p = BEFORE_BIN / meta
        md = json.loads(p.read_text())
        want = md['binary_hashes'][key]
        assert sha(BIN[track]['before']) == want
        report['provenance'][track] = {
            'old_metadata_sha256': sha(p),
            'old_metadata_file': str(p),
            'old_baseline_commit': md['baseline_commit'],
            'old_build_finished': md['finished_utc'],
            'binaries': {
                c: {'path': str(v), 'sha256': sha(v)} for c, v in BIN[track].items()
            },
        }
    # Exact equivalence of existing old driver TXT to original MPS; no regenerated input.
    MIPS = {}
    for n, (_, _, opt, dig) in miplib_import.MODELS.items():
        mps = SUITE / 'miplib-cache' / (n + '.mps')
        txt = (
            OLD
            / 'experiments/solver-bench/miplib-instances'
            / ('public_miplib3_' + n + '.txt')
        )
        j = txt.with_suffix('.json')
        model, md = miplib_import.parse_mps(mps.read_text())
        old = json.loads(j.read_text())
        assert sha(mps) == dig
        assert all(model[k] == old[k] for k in ('n', 'c', 'rows'))
        assert public_catalog.encode(old) == txt.read_text()
        MIPS[n] = (mps, txt, model, md, opt)
        report['inputs'][n] = {
            'mps_sha256': sha(mps),
            'old_txt_sha256': sha(txt),
            'old_json_sha256': sha(j),
            'exact_equivalent': True,
            'known_optimum': opt,
            'columns': model['n'],
            'original_rows': md['original_rows'],
        }
    chosen = [
        'public_fzn_jobshop',
        'public_fzn_cumulatives',
        'public_fzn_sudoku',
        'public_fzn_multidim_knapsack_simple',
    ]
    manifest = json.loads((SUITE / 'fzn-manifest.json').read_text())
    FZN = {r['id']: r for r in manifest['instances'] if r['id'] in chosen}
    assert len(FZN) == 4
    for name, r in FZN.items():
        for key in ('fzn', 'expected'):
            p = SUITE / r[key]
            assert sha(p) == r[key + '_sha256']
            assert sha(OLD / 'experiments/solver-bench' / r[key]) == sha(p)
        report['inputs'][name] = {
            'fzn_sha256': r['fzn_sha256'],
            'expected_sha256': r['expected_sha256'],
            'family': r['family'],
            'method': r['solve'],
            'all_solutions': r['all_solutions'],
        }

    def command(track, cohort, name):
        b = str(BIN[track][cohort])
        if track == 'mip':
            mps, txt, *_ = MIPS[name]
            return (
                [b, str(txt), 'auto', 'afc', str(round(LIMIT * 1000)), '0', '1']
                if cohort == 'before'
                else [
                    b,
                    str(mps),
                    '--time-limit',
                    str(LIMIT),
                    '--relative-gap',
                    '0',
                    '--absolute-gap',
                    '0',
                    '--seed',
                    '0',
                ]
            )
        r = FZN[name]
        return (
            [b, '-p', '1', '-time', str(round(LIMIT * 1000)), '-s']
            + (['-a'] if r['all_solutions'] else [])
            + [str(SUITE / r['fzn'])]
        )

    # Untimed dynamic provenance probes use the exact measured commands with dyld tracing.
    loaded = set()
    for track, name in [('mip', 'p0033'), ('native_cp', 'public_fzn_sudoku')]:
        for c in ('before', 'now'):
            rec, out, err = run(
                command(track, c, name), c, 'provenance-' + track + '-' + c, True
            )
            assert (
                not rec['hard_timeout']
                and not rec['output_limit']
                and rec['returncode'] == 0
            )
            paths = []
            for line in err.splitlines():
                if 'libgecode' not in line:
                    continue
                p = Path(line[line.index('/') :].strip()).resolve(strict=True)
                assert c == 'now' and p.parent in [d.resolve() for d in LIBDIRS], str(p)
                paths.append(str(p))
                loaded.add(p)
            assert bool(paths) == (c == 'now')
            report['provenance'][track][c + '_loaded_libraries'] = paths
    report['libraries'] = [{'path': str(p), 'sha256': sha(p)} for p in sorted(loaded)]
    report['runner_sha256'] = sha(Path(__file__))
    report['validation_source_hashes'] = {
        str(p): sha(p)
        for p in (
            SUITE / 'miplib_import.py',
            SUITE / 'validate.py',
            SUITE / 'public_catalog.py',
            SUITE / 'fzn-bench.py',
        )
    }
    report['methodology'] = [
        'Before static binaries and now shared binaries differ in process startup/layout.',
        'MIP before is a pre-existing binary auto adapter; now is numerical HiGHS.',
        'Current known-optimal completion is numerical-qualified, not an exact proof certificate.',
        'Original CP globals already existed; this native track preserves the default FlatZinc route.',
    ]
    dump(DEST / 'report.json', report)

    def check_mip(cohort, name, out):
        x = load(out)
        _, _, model, md, opt = MIPS[name]
        status = x['status'] if cohort == 'before' else x['termination']
        values = x['assignment'] if cohort == 'before' else x['values']
        d = {
            'reported_status': status,
            'objective': x.get('objective'),
            'validation': 'no_witness',
            'completed': False,
            'internal_seconds': (
                x['elapsed_ms'] / 1000 if cohort == 'before' else x['solve_seconds']
            ),
            'raw_result': x,
        }
        if values:
            if cohort == 'now':
                names = x['variable_names']
                assert len(names) == len(values) == len(set(names))
                mapped = dict(zip(names, values))
                assert set(mapped) == set(md['column_names'])
                values = [mapped[k] for k in md['column_names']]
            assert all(
                type(v) in (int, float)
                and math.isfinite(v)
                and abs(v - round(v)) <= 1e-6
                for v in values
            )
            witness = [round(v) for v in values]
            checked = validate.validate_assignment(model, witness)
            assert checked['valid'], checked
            objective = md['sign'] * Fraction(
                checked['objective'], md['objective_scale']
            ) + Fraction(md['original_objective_offset'])
            shown = checked['objective'] if cohort == 'before' else float(objective)
            assert x['objective'] is not None and abs(x['objective'] - shown) <= 1e-6
            d.update(
                validation='independent_exact_original_rows_and_domains',
                objective=float(objective),
                witness_valid=True,
                at_known_optimum=objective == opt,
            )
            if status == 'optimal':
                assert objective == opt
                if cohort == 'now':
                    assert (
                        x['solution_validated'] and abs(x['best_bound'] - opt) <= 1e-6
                    )
                d['completed'] = True
        else:
            assert status in (
                'unknown',
                'time_limit',
                'time limit',
                'node_limit',
            ), status
        return d

    for repetition in range(REPETITIONS):
        for track, names in [('mip', list(MIPS)), ('native_cp', chosen)]:
            for name in names:
                for c in (
                    ('before', 'now') if repetition % 2 == 0 else ('now', 'before')
                ):
                    label = f'{track}-{name}-r{repetition+1}-{c}'
                    r, out, err = run(command(track, c, name), c, label)
                    r.update(
                        track=track,
                        case=name,
                        cohort=c,
                        repetition=repetition + 1,
                        completed=False,
                        validation='not_checked',
                    )
                    try:
                        if r['output_limit']:
                            r['reported_status'] = 'output_limit'
                        elif r['hard_timeout']:
                            r['reported_status'] = 'external_timeout'
                        elif r['returncode'] != 0:
                            r['reported_status'] = 'process_error'
                        elif track == 'mip':
                            r.update(check_mip(c, name, out))
                        else:
                            text, stats, ok = fznb.output_and_statistics(out)
                            expected = (SUITE / FZN[name]['expected']).read_text()
                            status, reason = fznb.classify(
                                FZN[name], text, expected, r['returncode'], False
                            )
                            r.update(
                                reported_status=status,
                                validation=(
                                    'exact_unchanged_upstream_output'
                                    if text == expected
                                    else 'output_mismatch'
                                ),
                                completed=status == 'passed',
                                reason=reason,
                                statistics=stats,
                                internal_seconds=stats.get('solveTime'),
                                statistics_parsed=ok,
                            )
                    except (
                        ValueError,
                        AssertionError,
                        KeyError,
                        TypeError,
                        ZeroDivisionError,
                    ) as e:
                        r.update(reported_status='validation_error', error=str(e))
                    report['records'].append(r)
                    dump(DEST / 'report.json', report)
                    print(
                        label,
                        r['reported_status'],
                        round(r['external_seconds'], 4),
                        flush=True,
                    )
    report['hashes_unchanged'] = all(
        sha(Path(v['path'])) == v['sha256'] for v in report['libraries']
    ) and all(
        sha(Path(v['path'])) == v['sha256']
        for p in report['provenance'].values()
        for v in p['binaries'].values()
    )
    assert report['hashes_unchanged']
    dump(DEST / 'report.json', report)
    summary = {
        'schema_version': 1,
        'before_label': 'Pre-project experimental checkout',
        'now_label': 'Current integrated implementation',
        'source_head': report['source_head'],
        'repetitions': REPETITIONS,
        'per_solve_seconds': LIMIT,
        'wall_seconds': time.monotonic() - START,
        'all_records': len(report['records']),
        'tracks': [],
        'caveats': [
            'Five pure-binary MIPLIB3 classics; not a broad MILP performance score.',
            'Before binaries are static, now binaries are shared; startup/loading differences are included.',
            'Current optimal results are numerical-qualified and checked against known optima; these are not exact proof certificates.',
            'Native CP uses the unchanged default FlatZinc path and pre-existing capabilities.',
            'MIP before is the pre-existing experimental binary auto adapter; now is the numerical HiGHS facade. Different public file formats have exact mathematical equivalence.',
            'Native CP uses exact upstream expected output, not an independent mathematical checker.',
            'End-to-end times include startup, import, search and output; tiny cases are startup-sensitive.',
            'Alternating paired repetitions; one process at a time. No warm starts or reference assignments.',
            'No speedup ratio is published for a case with a censored or unsuccessful repetition.',
        ],
    }
    for track, names in [('mip', list(MIPS)), ('native_cp', chosen)]:
        t = {
            'id': track,
            'cases': [],
            'required_runs_per_cohort': len(names) * REPETITIONS,
        }
        for name in names:
            entry = {'id': name, 'before': {}, 'now': {}}
            for c in ('before', 'now'):
                rr = [
                    r
                    for r in report['records']
                    if r['track'] == track and r['case'] == name and r['cohort'] == c
                ]
                walls = [r['external_seconds'] for r in rr]
                internals = [
                    r['internal_seconds']
                    for r in rr
                    if r.get('internal_seconds') is not None
                ]
                entry[c] = {
                    'runs': len(rr),
                    'completed': sum(r['completed'] for r in rr),
                    'statuses': [r['reported_status'] for r in rr],
                    'wall_seconds': walls,
                    'median_wall_seconds': statistics.median(walls),
                    'median_internal_seconds': (
                        statistics.median(internals)
                        if len(internals) == len(rr)
                        else None
                    ),
                    'objectives': [r.get('objective') for r in rr],
                    'validation': [r['validation'] for r in rr],
                }
            complete = all(
                entry[c]['completed'] == REPETITIONS for c in ('before', 'now')
            )
            entry['uncensored_ratio_now_over_before'] = (
                statistics.median(
                    [
                        b / a
                        for a, b in zip(
                            entry['before']['wall_seconds'],
                            entry['now']['wall_seconds'],
                        )
                    ]
                )
                if complete
                else None
            )
            entry['censored'] = not complete
            t['cases'].append(entry)
        for c in ('before', 'now'):
            rows = [
                r for r in report['records'] if r['track'] == track and r['cohort'] == c
            ]
            t[c] = {
                'completed_runs': sum(r['completed'] for r in rows),
                'all_runs': len(rows),
                'all_repetitions_completed_cases': sum(
                    e[c]['completed'] == REPETITIONS for e in t['cases']
                ),
            }
        summary['tracks'].append(t)
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    dump(DEST / 'report.json', report)
    dump(DEST / 'summary.json', summary)
    print(
        'DONE',
        json.dumps({k: summary[k] for k in ('wall_seconds', 'all_records')}),
        flush=True,
    )


if __name__ == "__main__":
    main()
