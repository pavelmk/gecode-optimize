#!/usr/bin/env python3
"""Compare current ordinary Native/BAB with explicit, frozen family settings.

The pilot retains every attempted configuration. The separate adaptive run
uses a policy frozen before timing; it does not select a per-instance winner.
Both cohorts load the same accepted solver libraries. All solves receive ten
seconds, with no oracle or supplied start. Earlier studies remain separate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


legacy = module('configured_boundary_tools', HERE/'benchmark_boundaries.py')
common, generator, require, sha = legacy.common, legacy.generator, legacy.require, legacy.sha
ROUTES = ('native', 'lp-root', 'lp-cuts', 'lp-updated', 'dfs-reliability',
          'lp-reliability', 'lp-reliability-neighborhood')
PILOT_CASES = (('assignment', 18), ('facility_location', 9),
               ('bin_packing', 18), ('production', 12), ('knapsack', 408))


def validate(raw, model, route):
    """Independently check original witnesses, model identity and result protocol."""
    require(route in ROUTES, 'Unknown route')
    require(type(raw) is dict and type(raw.get('schema_version')) is int and
            raw.get('schema_version') == 1 and raw.get('kind') == model['kind'] and
            raw.get('route') == route and raw.get('guarantee') == 'exact' and
            raw.get('start_submitted') is False, 'Driver protocol mismatch')
    lp, reliability, neighborhood = route.startswith('lp-'), 'reliability' in route, route.endswith('-neighborhood')
    covers = lp and route != 'lp-root'
    expected_backend = ('Gecode native' + (' frontier' if reliability else '') +
                        (' + checked LP' if lp else '') + (' + BinaryHamming' if neighborhood else ''))
    require(raw.get('backend') == expected_backend and type(raw.get('backend_version')) is str and
            bool(raw['backend_version']), 'Unexpected backend')
    for key in ('model_id', 'revision'):
        require(type(raw.get(key)) is int and raw[key] > 0, 'Invalid model identity')
    for key in ('solve_seconds', 'backend_solve_seconds', 'build_seconds', 'driver_seconds'):
        require(common.finite(raw.get(key)) and raw[key] >= 0, 'Invalid duration')
    require(raw['build_seconds'] + raw['solve_seconds'] <= raw['driver_seconds'] + 1e-5,
            'Inconsistent elapsed time')
    require(raw['backend_solve_seconds'] <= raw['solve_seconds'] + 1e-5,
            'Backend duration exceeds owning solve')
    n, kind = model['n'], model['kind']
    expected = (n, len(model['rows']), 0) if kind == 'binary' else (
        n*(2 if kind == 'native_tsp' else 4), 0 if kind == 'native_tsp' else 2*n,
        n+(1 if kind == 'native_tsp' else 3))
    require(all(type(raw.get(k)) is int for k in ('model_columns', 'model_rows', 'model_globals')) and
            tuple(raw.get(k) for k in ('model_columns', 'model_rows', 'model_globals')) == expected,
            'Model dimensions differ')
    require(raw.get('status') in ('optimal', 'time_limit', 'memory_limit'),
            'Unexpected solver status: '+str(raw.get('status')))
    point = raw.get('has_solution')
    require(type(point) is bool and raw.get('solution_validated') is point, 'Presence mismatch')
    values, full = raw.get('assignment'), raw.get('full_values')
    require(type(values) is list and type(full) is list, 'Missing values')
    if point:
        require(len(values) == n and len(full) == expected[0] and all(
            common.finite(v) and v == round(v) for v in values+full), 'Invalid exact values')
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
    for key in ('objective', 'best_bound', 'absolute_gap', 'relative_gap'):
        require(raw.get(key) is None or common.finite(raw[key]), 'Nonfinite scalar')
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
    config = raw.get('algorithm_configuration')
    require(type(config) is dict, 'Missing algorithm configuration')
    expected_config = dict(
        entry_point=('solve_native_neighborhoods' if neighborhood else 'solve_native_search' if reliability
                     else 'solve_native_lp' if lp else 'solve_native'),
        search_order='depth_first' if reliability else 'native_bab', checked_lp=lp,
        lp_frequency=('root' if route in ('lp-root', 'lp-cuts') else 'after_bound_changes') if lp else None,
        bound_tightening=lp, bound_change_interval=(1 if route in ('lp-root', 'lp-cuts') else 4) if lp else None,
        root_cover_cuts=covers, binary_reliability=reliability, neighborhoods=neighborhood,
        knapsack_dp_eligible_route=not lp, presolve=False, max_open_nodes=1024 if reliability else None,
        cover_settings=dict(max_rounds=4, max_work=4000000, max_cuts=64, max_cut_nonzeros=4096,
            max_model_columns=200000, max_model_rows=200000, max_model_nonzeros=2000000,
            max_separation_rows=256, max_terms_per_row=512, denominator=1048576) if covers else None,
        branching_settings=dict(policy='binary_reliability', max_candidates_per_decision=8,
            max_probe_status_calls=128, max_probe_status_calls_per_decision=8, max_branching_work=100000,
            reliability_samples=2, max_nonimproving_pairs=2, max_history_entries=4096) if reliability else None,
        neighborhood_settings=dict(policy='binary_hamming', radius=4, max_status_calls=128,
            max_distance_variables=4096, max_source_entries=100000, max_coordinator_work=100000,
            max_local_spaces=64, time_limit_seconds=0.05) if neighborhood else None)
    require(json.dumps(config, sort_keys=True, allow_nan=False) ==
            json.dumps(expected_config, sort_keys=True, allow_nan=False), 'Algorithm configuration differs')
    relaxation = raw.get('relaxation')
    branching = raw.get('branching')
    local = raw.get('neighborhood')
    require(all(type(g) is dict for g in (relaxation, branching, local)), 'Missing mechanism statistics')
    cover = relaxation.get('root_cover')
    require(type(cover) is dict, 'Missing cover statistics')

    def counters(group, names, seconds=()):
        require(all(type(group.get(k)) is int and group[k] >= 0 for k in names.split()),
                'Invalid/missing mechanism counter')
        require(all(common.finite(group.get(k)) and 0 <= group[k] <= raw['solve_seconds'] + 1e-5
                    for k in seconds), 'Invalid mechanism duration')

    counters(relaxation, 'lp_calls valid_bounds rejected_bounds numerical_infeasibility_reports '
             'certificate_evaluations conditional_checks variable_fixings variable_bound_tightenings', ('lp_seconds',))
    counters(cover, 'rounds augmentations cuts nonzeros work projected_coordinates unsupported_rows '
             'oversized_rows separated_cuts duplicate_cuts arithmetic_rejections lp_calls valid_bounds '
             'rejected_bounds numerical_infeasibility_reports', ('lp_seconds',))
    counters(branching, 'decisions manual_splits fallback_decisions probe_status_calls completed_pairs '
             'published_pairs finite_samples zero_gain_samples failed_directions reliable_candidates '
             'probe_propagations budget_nodes work history_entries probe_lp_calls', ('probe_lp_seconds',))
    counters(local, 'attempts eligible_variables source_entries coordinator_work status_attempts '
             'completed_status_calls failed_nodes feasible_candidates accepted_improvements peak_local_spaces '
             'peak_total_spaces budget_nodes', ('elapsed_seconds',))
    require(cover.get('requested') is covers and branching.get('requested') is reliability and
            local.get('requested') is neighborhood, 'Mechanism request differs')
    require(cover.get('completion') in ('NotRequested', 'NotStarted', 'NoNewCuts', 'RoundLimit', 'WorkLimit',
            'StorageLimit', 'SeparationLimit', 'Cancelled', 'TimeLimit', 'NoPrimalSuggestion',
            'InvalidSuggestion', 'CallbackError', 'BackendError', 'AllocationFailure'), 'Unknown cover completion')
    require(local.get('completion') in ('NotStarted', 'NoIncumbent', 'ProofCompletedBeforeAttempt',
            'NoEligibleBinary', 'NonrestrictingRadius', 'FormulationLimit', 'SourceLimit', 'WorkLimit',
            'StatusLimit', 'SharedNodeReserve', 'LocalStorageLimit', 'LocalTimeLimit', 'NoImprovement',
            'Improved', 'GlobalStop', 'Error'), 'Unknown neighborhood completion')
    require('stop_reason' in local and (local['stop_reason'] is None or local['stop_reason'] in
            ('time_limit', 'memory_limit', 'node_limit', 'cancelled')), 'Invalid neighborhood stop')
    require(cover['lp_calls'] <= relaxation['lp_calls'] and
            branching['probe_lp_calls'] <= relaxation['lp_calls'] and
            cover['lp_seconds'] <= relaxation['lp_seconds'] + 1e-5 and
            branching['probe_lp_seconds'] <= relaxation['lp_seconds'] + 1e-5,
            'LP subset accounting differs')
    require(local['attempts'] <= 1 and local['accepted_improvements'] <= local['feasible_candidates'] and
            local['completed_status_calls'] <= local['status_attempts'], 'Neighborhood accounting differs')
    if not lp:
        require(all(v == 0 for k, v in relaxation.items() if k != 'root_cover'), 'LP work on non-LP route')
    if not covers:
        require(cover['completion'] == 'NotRequested' and all(v == 0 for k, v in cover.items()
                if k not in ('requested', 'completion')), 'Unrequested cover work')
    if not reliability:
        require(all(v == 0 for k, v in branching.items() if k != 'requested'), 'Unrequested branching work')
    if not neighborhood:
        require(local['completion'] == 'NotStarted' and local['stop_reason'] is None and
                all(v == 0 for k, v in local.items() if k not in ('requested', 'completion', 'stop_reason')),
                'Unrequested neighborhood work')
    node_keys = ('nodes', 'expanded_nodes', 'budget_nodes', 'peak_open_nodes', 'unresolved_regions')
    require(all(k in raw for k in node_keys), 'Missing search counters')
    if reliability:
        require(all(type(raw[k]) is int and raw[k] >= 0 for k in node_keys), 'Invalid frontier counter')
        require(raw['budget_nodes'] == branching['budget_nodes'] ==
                raw['nodes'] + branching['probe_status_calls'] + local['status_attempts'],
                'Shared node accounting differs')
        require(raw['expanded_nodes'] <= raw['nodes'] and raw['peak_open_nodes'] <= config['max_open_nodes'] and
                (not optimal or raw['unresolved_regions'] == 0), 'Frontier accounting differs')
        if neighborhood:
            require(local['budget_nodes'] == raw['budget_nodes'], 'Neighborhood shared budget differs')
    else:
        require(all(raw[k] is None for k in node_keys), 'Unexpected ordinary-search counters')
    return dict(status=raw['status'], passed=optimal and raw['solve_seconds'] <= 10,
                primal_checked=point, independent_optimality_verified=False,
                backend_reported_optimal=optimal, solve_seconds=raw['solve_seconds'],
                objective=objective, best_bound=bound, backend_result=raw)


class ConfiguredSearch(legacy.Search):
    def passed(self, category, size, cohort, confirmed=False):
        """A boundary needs distinct complete observations for every variant."""
        rows = self.rows(category, size, cohort)
        variants = ('uncorrelated', 'correlated') if category == 'knapsack' else ('single',)
        identities = [(r.get('variant'), r.get('repetition')) for r in rows]
        required = {(v, r) for v in variants for r in range(1, 3 if confirmed else 2)}
        allowed = {(v, r) for v in variants for r in (1, 2)}
        return (len(identities) == len(set(identities)) and required <= set(identities) <= allowed and
                all(r.get('passed') is True and r.get('status') == 'optimal' and
                    r.get('primal_checked') is True and r.get('backend_reported_optimal') is True and
                    common.finite(r.get('solve_seconds')) and 0 <= r['solve_seconds'] <= 10
                    for r in rows))

    def __init__(self, output, binary, policy_path=None, pilot=False):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output/'models').mkdir()
        self.started = time.monotonic()
        self.binary = binary.resolve(strict=True)
        build_path = self.binary.parent/'build.local.json'
        build = json.loads(build_path.read_text())
        require(build['source_sha256'] == sha(HERE/'configured_benchmark.cpp') and
                build['binary_sha256'] == sha(self.binary) and build['runtime_libraries_unchanged'],
                'Driver build identity differs from current source/executable')
        require(all(Path(p).is_file() and sha(Path(p)) == h
                    for p, h in build['runtime_libraries_sha256'].items()),
                'Built driver runtime libraries changed')
        policy_path = policy_path.resolve(strict=True) if policy_path else None
        self.directories = {c: [ROOT/'build/native-compat/gecode/optimize', ROOT/'build/native-compat']
                            for c in ('before', 'after')}
        prior = ROOT/'build/category-scaling/results/report.json'
        manifest = json.loads((ROOT.parent.parent/'benchmark-site/scripts/category-scaling-evidence.json').read_text())
        require(sha(prior) == manifest['files']['report']['sha256'], 'Prior provenance changed')
        old = json.loads(prior.read_text())
        self.expected = {c: old['provenance']['cohorts']['after'] for c in ('before', 'after')}
        self.runtime_sources = old['provenance']['runtime_source_sha256']
        self.models, self.records, self.decisions = {}, [], []
        self.policy = json.loads(policy_path.read_text()) if policy_path else None
        self.policy_path = policy_path
        self.pilot = pilot
        paths = [Path(__file__), HERE/'configured_benchmark.cpp', HERE/'build_configured_benchmark.py',
                 build_path, HERE/'benchmark_boundaries.py',
                 HERE/'boundary_instances.py', HERE/'category_instances.py', HERE/'scaling_instances.py',
                 HERE/'benchmark_native_algorithms.py', HERE/'benchmark_progress.py',
                 ROOT/'experiments/solver-bench/validate.py', ROOT/'experiments/solver-bench/native.py']
        if policy_path:
            paths.append(policy_path)
            require(set(self.policy['families']) == set(legacy.LIMITS), 'Policy family mismatch')
            for family, value in self.policy['families'].items():
                require(value['route'] in ROUTES, 'Unknown policy route')
                if value.get('outside_dp_route'):
                    require(family == 'knapsack' and value['route'] == 'native' and
                            value['outside_dp_route'] in ROUTES, 'Invalid DP dispatch')
        require(pilot != bool(policy_path), 'Choose pilot or a frozen policy')
        self.sources = {str(p.relative_to(ROOT)): sha(p) for p in paths}
        self.provenance = dict(source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            sources=self.sources, runtime_sources=self.runtime_sources,
            driver_sha256=sha(self.binary), expected_libraries=self.expected,
            driver_build=dict(source_sha256=build['source_sha256'], binary_sha256=build['binary_sha256'],
                compiler_flags_sha256=build['flags_sha256'], link_metadata_sha256=build['link_metadata_sha256']),
            comparison='Same accepted current solver libraries; ordinary settings versus selected explicit settings.')
        self.protocol = dict(seconds=10, capture_seconds=11, whole_seconds=legacy.WHOLE_SECONDS,
            max_attempts=legacy.MAX_ATTEMPTS, max_sizes_per_category=legacy.MAX_SIZES,
            limits=legacy.LIMITS, pilot=pilot, pilot_cases=PILOT_CASES if pilot else None,
            candidate_routes=ROUTES if pilot else None, policy=self.policy,
            cohort_labels={'before': 'Previous settings', 'after': 'Configured'},
            selection='Pilot is exploratory and preserves every candidate. Adaptive policy is fixed before timing; independent doubling/bisection and adjacent two-repeat confirmation.',
            optimality='Backend-reported exact optimum; original witness independently checked. No independent optimum oracle.',
            capacity='Largest sampled size with all variants passing both repetitions. Untested sizes remain unknown.',
            timing='Steady-clock wall time around the entire owning solve call; ten seconds per solve. No supplied starts.',
            generalization='Policy selection and adaptive measurement reuse seeded families; this is not an independent holdout.')
        self.complete = False
        self.publish()
        for name, digest in self.runtime_sources.items():
            require(sha(ROOT/name) == digest, 'Accepted solver source changed')
        self.execute('knapsack', 8, 'uncorrelated', 'before', 0, probe=True)
        self.execute('knapsack', 8, 'uncorrelated', 'after', 0, probe=True)

    def route(self, category, model, cohort):
        if cohort == 'before' or self.pilot:
            return 'native'
        selected = self.policy['families'][category]
        if category == 'knapsack' and not model['parameters']['dp_eligible']:
            return selected.get('outside_dp_route', selected['route'])
        return selected['route']

    def execute(self, category, size, variant, cohort, repetition, probe=False, route_override=None):
        require(len(self.records) < legacy.MAX_ATTEMPTS and time.monotonic()-self.started < legacy.WHOLE_SECONDS,
                'Whole-run allowance exhausted')
        key, model = self.model(category, size, variant)
        route = route_override or self.route(category, model, cohort)
        label = f'{key}-{cohort}-{route}-r{repetition}'
        record = dict(case=key, category=category, size=size, variant=variant, cohort=cohort,
                      repetition=repetition, route=route, probe=probe, status='pending', passed=False)
        self.records.append(record)
        self.publish()
        env = {k: v for k, v in os.environ.items() if not k.startswith('DYLD_')}
        directories = self.directories['after']
        env['DYLD_LIBRARY_PATH'] = ':'.join(map(str, directories))
        if probe:
            env['DYLD_PRINT_LIBRARIES'] = '1'
        command = [str(self.binary), '--input', str(self.output/'models'/(key+'.txt')),
                   '--kind', model['kind'], '--route', route, '--seconds', '10']
        record['offset_start'] = time.monotonic()-self.started
        try:
            raw = legacy.capture(command, self.output, env,
                min(11, legacy.WHOLE_SECONDS-record['offset_start']), max_output=262144)
            record['offset_end'] = time.monotonic()-self.started
            stdout, stderr = raw.pop('stdout'), raw.pop('stderr')
            (self.output/(label+'.stdout')).write_bytes(stdout)
            (self.output/(label+'.stderr')).write_bytes(stderr)
            record.update(raw)
            require(raw['returncode'] == 0 and not raw['hard_timeout'] and not raw['output_limit'],
                    'Process capture failed: '+stderr.decode(errors='replace')[:500])
            record.update(validate(common.strict_json(stdout.decode()), model, route))
            if probe:
                loaded = set()
                for line in stderr.decode().splitlines():
                    if 'libgecode' not in line:
                        continue
                    p = Path(line[line.index('/'):].strip()).resolve(strict=True)
                    require(p.parent in directories, 'Mixed loader paths')
                    loaded.add((p.name, sha(p)))
                expected = {(x['name'], x['sha256']) for x in self.expected['after']['libraries']}
                require(loaded == expected, 'Loaded product differs from accepted current libraries')
                self.provenance[cohort+'_loaded'] = sorted(loaded)
            peers = [r['objective'] for r in self.records if r['case'] == key and r.get('backend_reported_optimal')]
            require(len(set(peers)) <= 1, 'Reported optima disagree')
            if peers:
                for peer in (r for r in self.records if r['case'] == key):
                    require(peer.get('objective') is None or peer['objective'] >= peers[0], 'Feasible peer contradicts optimum')
                    require(peer.get('best_bound') is None or peer['best_bound'] <= peers[0], 'Peer bound contradicts optimum')
        except Exception as error:
            record.update(status='error', error=str(error), passed=False)
            self.publish()
            raise
        self.publish()
        print(label, record['status'], round(record.get('solve_seconds', 0), 6), flush=True)

    def integrity(self):
        self.provenance['integrity'] = dict(
            sources_unchanged=all(sha(ROOT/p) == h for p, h in self.sources.items()),
            runtime_sources_unchanged=all(sha(ROOT/p) == h for p, h in self.runtime_sources.items()),
            driver_unchanged=sha(self.binary) == self.provenance['driver_sha256'],
            models_unchanged=all(sha(self.output/'models'/(k+'.json')) == v['json_sha256'] and
                sha(self.output/'models'/(k+'.txt')) == v['txt_sha256'] for k, v in self.models.items()),
            libraries_unchanged=all(any((d/x['name']).is_file() and sha(d/x['name']) == x['sha256']
                for d in self.directories['after']) for x in self.expected['after']['libraries']))
        require(all(self.provenance['integrity'].values()), 'Measurement integrity failed')

    def run_pilot(self):
        for category, size in PILOT_CASES:
            for route in ROUTES:
                variants = ('uncorrelated', 'correlated') if category == 'knapsack' else ('single',)
                for variant in variants:
                    self.execute(category, size, variant, route, 1, route_override=route)
        self.integrity()
        self.complete = True
        self.publish()
        print('Pilot complete:', len(self.records)-2, 'measurements', flush=True)

    def run(self):
        # Use the existing independent search policy, but verify this new driver
        # against its own frozen identity rather than the historical executable.
        original_hash = legacy.DRIVER_HASH
        legacy.DRIVER_HASH = self.provenance['driver_sha256']
        try:
            super().run()
        finally:
            legacy.DRIVER_HASH = original_hash


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pilot', action='store_true')
    group.add_argument('--policy', type=Path)
    args = parser.parse_args()
    study = ConfiguredSearch(args.output_dir, args.binary, args.policy, args.pilot)
    study.run_pilot() if args.pilot else study.run()
