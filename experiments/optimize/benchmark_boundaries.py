#!/usr/bin/env python3
"""Adaptive paired size search; ten seconds per solve, no builds or oracle jobs.

Freeze this source/generator before invocation. Inputs are deterministic and saved
before their first solve. Binary search is a sampling heuristic, not a proof of
monotonic difficulty. Each cohort is bracketed independently; shared timing points are filled only
within the smaller confirmed range. Larger unmeasured outcomes remain unknown.
Boundary candidates and neighboring sizes receive two paired repetitions; failed
confirmations are retained. Reported exact optima have independently checked
original witnesses, but no independent optimum oracle is claimed for this study.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LIMITS = {'knapsack': (8, 32, 512), 'assignment': (3, 16, 32),
          'facility_location': (2, 8, 16), 'bin_packing': (4, 16, 32),
          'production': (3, 6, 48), 'native_tsp': (4, 16, 96),
          'weighted_queens': (4, 12, 32)}
SECONDS, WALL_SECONDS, WHOLE_SECONDS, MAX_ATTEMPTS, MAX_SIZES = 10, 11, 2400, 480, 32
COHORTS = ('before', 'after')
DRIVER_HASH = 'fa2a8b1f7afcc93589d941dd9e92383bf79a9f11a3bdf73b8213cae11f3c49a4'


def require(test, message):
    if not test:
        raise ValueError(message)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


common = module('boundary_common', HERE/'benchmark_native_algorithms.py')
generator = module('boundary_instances', HERE/'boundary_instances.py')
capture = module('boundary_capture', HERE/'benchmark_progress.py').capture_command
sha = common.sha


def validate(raw, model):
    """Check protocol/primal/auxiliaries; trust and label backend proof explicitly."""
    n, kind = model['n'], model['kind']
    require(type(raw.get('schema_version')) is int and raw['schema_version'] == 1 and raw.get('kind') == kind and
            raw.get('route') == 'native' and raw.get('backend') == 'Gecode native' and
            raw.get('guarantee') == 'exact' and raw.get('start_submitted') is False,
            'Driver protocol mismatch')
    require(isinstance(raw.get('backend_version'), str) and raw['backend_version'] and
            type(raw.get('model_id')) is int and raw['model_id'] > 0 and
            type(raw.get('revision')) is int and raw['revision'] >= 0, 'Invalid model identity')
    for key in ('solve_seconds', 'build_seconds', 'driver_seconds'):
        require(common.finite(raw.get(key)) and raw[key] >= 0, 'Invalid elapsed time')
    require(raw['build_seconds'] + raw['solve_seconds'] <= raw['driver_seconds'] + 1e-6,
            'Inconsistent elapsed time')
    for key in ('objective', 'best_bound', 'absolute_gap', 'relative_gap'):
        require(raw.get(key) is None or common.finite(raw[key]), 'Nonfinite scalar')
    expected = (n, len(model['rows']), 0) if kind == 'binary' else (
        n*(2 if kind == 'native_tsp' else 4), 0 if kind == 'native_tsp' else 2*n,
        n+(1 if kind == 'native_tsp' else 3))
    require(tuple(raw.get(k) for k in ('model_columns', 'model_rows', 'model_globals')) == expected,
            'Compiled model dimensions differ')
    require(all(raw.get(k) is None for k in ('nodes', 'expanded_nodes', 'budget_nodes',
            'peak_open_nodes', 'unresolved_regions')), 'Unexpected ordinary-search counters')
    require(raw.get('status') in ('optimal', 'time_limit'), 'Unexpected solver status')
    point = raw.get('has_solution')
    require(type(point) is bool and raw.get('solution_validated') is point, 'Presence mismatch')
    values, full = raw.get('assignment'), raw.get('full_values')
    require(type(values) is list and type(full) is list, 'Missing values')
    if point:
        require(len(values) == n and len(full) == expected[0] and all(
            common.finite(v) and v == round(v) for v in values + full), 'Invalid exact values')
        values, full = list(map(int, values)), list(map(int, full))
        checked = generator.validate_assignment(model, values)
        require(checked['valid'] and checked['objective'] == raw['objective'], 'Original witness failed')
        expected_full = values[:]
        if kind == 'weighted_queens':
            expected_full += [v for i, x in enumerate(values) for v in (x+i, x-i)]
        if kind != 'binary':
            expected_full += [model['data'][i][x] for i, x in enumerate(values)]
        require(full == expected_full, 'Auxiliary values differ')
    else:
        require(not values and not full and raw['objective'] is None, 'Absent-point values')
    bound, objective = raw['best_bound'], raw['objective']
    if point and bound is not None:
        gap = objective-bound
        require(gap >= 0 and raw['absolute_gap'] == gap and
                abs(raw['relative_gap']-gap/max(1, abs(objective), abs(bound))) <= 1e-12,
                'Bound/gap inconsistency')
    else:
        require(raw['absolute_gap'] is None and raw['relative_gap'] is None, 'Gap without both sides')
    optimal = raw['status'] == 'optimal'
    require(not optimal or (point and bound == objective and raw['absolute_gap'] == 0),
            'Incomplete optimal result')
    return dict(status=raw['status'], passed=optimal and raw['solve_seconds'] <= SECONDS,
                primal_checked=point, independent_optimality_verified=False,
                backend_reported_optimal=optimal, solve_seconds=raw['solve_seconds'],
                objective=objective, best_bound=bound, backend_result=raw)


class Search:
    def __init__(self, output):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output/'models').mkdir()
        self.started = time.monotonic()
        self.binary = ROOT/'build/capacity-scaling/fixed-driver/optimize-native-benchmark'
        self.directories = {'before': [ROOT/'build/comparison-algorithms/before/lib'],
                            'after': [ROOT/'build/native-compat/gecode/optimize', ROOT/'build/native-compat']}
        self.models, self.records, self.decisions = {}, [], []
        paths = [Path(__file__), HERE/'boundary_instances.py', HERE/'category_instances.py',
                 HERE/'scaling_instances.py', HERE/'benchmark_native_algorithms.py',
                 HERE/'benchmark_progress.py', ROOT/'experiments/solver-bench/validate.py',
                 ROOT/'experiments/solver-bench/native.py']
        self.sources = {str(p.relative_to(ROOT)): sha(p) for p in paths}
        prior = ROOT/'build/category-scaling/results/report.json'
        # This fixed artifact supplies expected library hashes, never new timing outcomes.
        expected_sha = json.loads((ROOT.parent.parent/'benchmark-site/scripts/category-scaling-evidence.json').read_text())['files']['report']['sha256']
        require(sha(prior) == expected_sha, 'Prior provenance artifact changed')
        old = json.loads(prior.read_text())
        self.expected = old['provenance']['cohorts']
        self.runtime_sources = old['provenance']['runtime_source_sha256']
        self.provenance = dict(source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                               sources=self.sources, prior_report_sha256=expected_sha, driver_sha256=sha(self.binary),
                               runtime_sources=self.runtime_sources, expected_libraries=self.expected)
        self.protocol = dict(seconds=SECONDS, capture_seconds=WALL_SECONDS, whole_seconds=WHOLE_SECONDS,
                             max_attempts=MAX_ATTEMPTS, max_sizes_per_category=MAX_SIZES, limits=LIMITS,
                             selection='Independent anchor/exponential bracketing, integer bisection and adjacent two-repeat confirmation. Stop expanding each cohort at its first failure. Fill shared points only through the smaller confirmed boundary. No retries.',
                             optimality='Backend-reported exact optimum; original witness independently checked. No independent optimum oracle.',
                             capacity='Largest sampled size with all variants passing both repetitions. Untested sizes remain unknown.')
        self.complete = False
        self.publish()
        require(sha(self.binary) == DRIVER_HASH, 'Fixed driver changed')
        for name, digest in self.runtime_sources.items():
            require(sha(ROOT/name) == digest, 'Solver source changed')
        for cohort in COHORTS:
            self.execute('knapsack', 8, 'uncorrelated', cohort, 0, probe=True)

    def publish(self):
        report = dict(protocol=self.protocol, provenance=self.provenance,
                      started_utc=getattr(self, 'utc', None), elapsed_seconds=time.monotonic()-self.started,
                      complete=self.complete, models=list(self.models.values()), records=self.records,
                      decisions=self.decisions)
        common.write(self.output/'report.json', common.public_copy(report, [(str(ROOT), 'REPOSITORY')]))

    def model(self, category, size, variant):
        key = f'{category}-{size}-{variant}'
        if key not in self.models:
            model = generator.make(category, size, variant)
            common.write(self.output/'models'/(key+'.json'), model)
            text = generator.encode_txt(model)
            (self.output/'models'/(key+'.txt')).write_text(text)
            self.models[key] = dict(id=key, category=category, size=size, variant=variant,
                                   model=model, json_sha256=sha(self.output/'models'/(key+'.json')),
                                   txt_sha256=sha(self.output/'models'/(key+'.txt')))
            self.publish()
        return key, self.models[key]['model']

    def execute(self, category, size, variant, cohort, repetition, probe=False):
        require(len(self.records) < MAX_ATTEMPTS and time.monotonic()-self.started < WHOLE_SECONDS,
                'Preregistered whole-run allowance exhausted')
        key, model = self.model(category, size, variant)
        label = f'{key}-{cohort}-r{repetition}'
        record = dict(case=key, category=category, size=size, variant=variant, cohort=cohort,
                      repetition=repetition, probe=probe, status='pending', passed=False)
        self.records.append(record)
        self.publish()
        env = {k: v for k, v in os.environ.items() if not k.startswith('DYLD_')}
        env['DYLD_LIBRARY_PATH'] = ':'.join(map(str, self.directories[cohort]))
        if probe:
            env['DYLD_PRINT_LIBRARIES'] = '1'
        command = [str(self.binary), '--input', str(self.output/'models'/(key+'.txt')),
                   '--kind', model['kind'], '--route', 'native', '--seconds', str(SECONDS)]
        record['offset_start'] = time.monotonic()-self.started
        try:
            raw = capture(command, self.output, env, min(WALL_SECONDS, WHOLE_SECONDS-record['offset_start']), max_output=262144)
            record['offset_end'] = time.monotonic()-self.started
            stdout, stderr = raw.pop('stdout'), raw.pop('stderr')
            (self.output/(label+'.stdout')).write_bytes(stdout)
            (self.output/(label+'.stderr')).write_bytes(stderr)
            record.update(raw)
            require(raw['returncode'] == 0 and not raw['hard_timeout'] and not raw['output_limit'], 'Process capture failed')
            record.update(validate(common.strict_json(stdout.decode()), model))
            if probe:
                loaded = set()
                for line in stderr.decode().splitlines():
                    if 'libgecode' not in line:
                        continue
                    p = Path(line[line.index('/'):].strip()).resolve(strict=True)
                    require(p.parent in self.directories[cohort], 'Mixed loader paths')
                    loaded.add((p.name, sha(p)))
                expected = {(x['name'], x['sha256']) for x in self.expected[cohort]['libraries']}
                require(loaded == expected, 'Loaded cohort differs from preserved product')
                self.provenance[cohort+'_loaded'] = sorted(loaded)
            peers = [r['objective'] for r in self.records if r['case'] == key and r.get('backend_reported_optimal')]
            require(len(set(peers)) <= 1, 'Paired optimum disagreement')
            if peers:
                for peer in (r for r in self.records if r['case'] == key):
                    require(peer.get('objective') is None or peer['objective'] >= peers[0], 'Feasible peer contradicts reported optimum')
                    require(peer.get('best_bound') is None or peer['best_bound'] <= peers[0], 'Peer bound contradicts reported optimum')
        except Exception as error:
            record.update(status='error', error=str(error), passed=False)
            self.publish()
            raise
        self.publish()
        print(label, record['status'], record.get('solve_seconds'), flush=True)

    def rows(self, category, size, cohort):
        return [r for r in self.records if not r['probe'] and r['category'] == category and
                r['size'] == size and r['cohort'] == cohort]

    def sizes(self, category):
        return sorted({r['size'] for r in self.records if not r['probe'] and r['category'] == category})

    def passed(self, category, size, cohort, confirmed=False):
        rows = self.rows(category, size, cohort)
        required = (2 if category == 'knapsack' else 1)*(2 if confirmed else 1)
        return len(rows) >= required and all(r['passed'] for r in rows)

    def query(self, category, size, reason, repeats=1, cohorts=COHORTS):
        minimum, _, maximum = LIMITS[category]
        require(minimum <= size <= maximum, 'Query outside fixed domain')
        require(size in self.sizes(category) or len(self.sizes(category)) < MAX_SIZES, 'Category size allowance exhausted')
        self.decisions.append(dict(category=category, size=size, reason=reason, repeats=repeats,
                                   after_records=len(self.records), cohorts=list(cohorts)))
        self.publish()
        variants = ('uncorrelated', 'correlated') if category == 'knapsack' else ('single',)
        for repetition in range(1, repeats+1):
            for cohort in (cohorts if repetition == 1 else cohorts[::-1]):
                for variant in variants:
                    if not any(r['category'] == category and r['size'] == size and r['cohort'] == cohort and
                               r['variant'] == variant and r['repetition'] == repetition for r in self.records):
                        self.execute(category, size, variant, cohort, repetition)

    def run(self):
        self.utc = datetime.now(timezone.utc).isoformat()
        # Independent searches stop expanding a cohort after its first failure.
        for category, (minimum, anchor, cap) in LIMITS.items():
            for cohort in COHORTS:
                self.query(category, anchor, cohort+' starting size', cohorts=(cohort,))
                if not self.passed(category, anchor, cohort):
                    self.query(category, minimum, cohort+' minimum fallback', cohorts=(cohort,))
                passing = [s for s in self.sizes(category) if self.passed(category, s, cohort)]
                if not passing:
                    continue
                low, high = max(passing), None
                failures = [s for s in self.sizes(category) if s > low and
                            self.rows(category, s, cohort) and not self.passed(category, s, cohort)]
                if failures:
                    high = min(failures)
                while high is None and low < cap:
                    nxt = min(low*2, cap)
                    self.query(category, nxt, cohort+' exponential bracket', cohorts=(cohort,))
                    if self.passed(category, nxt, cohort):
                        low = nxt
                    else:
                        high = nxt
                if high is not None:
                    while high-low > 1:
                        mid = (low+high)//2
                        self.query(category, mid, cohort+' integer bisection', cohorts=(cohort,))
                        if self.passed(category, mid, cohort):
                            low = mid
                        else:
                            high = mid
                # Confirm the candidate and adjacent inputs without exploring
                # a previously failed upper interval again.
                for _ in range(6):
                    passing = [s for s in self.sizes(category) if self.passed(category, s, cohort)]
                    if not passing:
                        break
                    candidate = max(passing)
                    for size in range(max(minimum, candidate-1), min(cap, candidate+1)+1):
                        self.query(category, size, cohort+' boundary confirmation', repeats=2, cohorts=(cohort,))
                    updated = [s for s in self.sizes(category) if self.passed(category, s, cohort)]
                    if updated and max(updated) == candidate and self.passed(category, candidate, cohort, True):
                        break
            maxima = [max((s for s in self.sizes(category) if self.passed(category, s, c, True)),
                          default=minimum) for c in COHORTS]
            shared_ceiling = min(maxima)+1
            for size in list(self.sizes(category)):
                if size <= shared_ceiling:
                    self.query(category, size, 'shared timing point within smaller boundary', cohorts=COHORTS)
        self.provenance['integrity'] = dict(
            sources_unchanged=all(sha(ROOT/p) == h for p, h in self.sources.items()),
            runtime_sources_unchanged=all(sha(ROOT/p) == h for p, h in self.runtime_sources.items()),
            driver_unchanged=sha(self.binary) == DRIVER_HASH,
            models_unchanged=all(sha(self.output/'models'/(k+'.json')) == v['json_sha256'] and
                sha(self.output/'models'/(k+'.txt')) == v['txt_sha256'] for k, v in self.models.items()),
            libraries_unchanged=all(any((d/x['name']).is_file() and sha(d/x['name']) == x['sha256']
                for d in self.directories[c]) for c in COHORTS for x in self.expected[c]['libraries']))
        require(all(self.provenance['integrity'].values()), 'Measurement integrity failed')
        require(time.monotonic()-self.started < WHOLE_SECONDS, 'Whole-run allowance exhausted before completion')
        self.complete = True
        self.publish()
        if time.monotonic()-self.started >= WHOLE_SECONDS:
            self.complete = False
            self.publish()
            raise ValueError('Whole-run allowance exhausted during publication')
        print('Adaptive search complete:', len(self.records)-2, 'measured runs;', round(time.monotonic()-self.started, 2), 'seconds', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    Search(args.output_dir).run()
