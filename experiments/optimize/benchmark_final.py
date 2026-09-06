#!/usr/bin/env python3
"""One serial three-cohort study; ten seconds includes all automatic racing work.

Each cohort gets independent bracketing/bisection and two-repeat boundary checks.
This samples seeded families; difficulty need not be monotonic and a tested ceiling
is not a solver limit. Original witnesses are independently checked; exact optimal
status is backend-reported, not an independently proved optimum. No timing result
is selected from alternative configured routes. Historical artifacts stay intact.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import benchmark_configured as configured

legacy, common, generator = configured.legacy, configured.common, configured.generator
ROOT, HERE, sha, require = configured.ROOT, configured.HERE, configured.sha, configured.require
COHORTS = ('before', 'auto', 'configured')
legacy.COHORTS = COHORTS
legacy.MAX_ATTEMPTS = 720
legacy.WHOLE_SECONDS = 3600
# Retain the earlier preregistered domains so the final comparison is comparable.


def validate(raw, model, route):
    if route != 'auto-race':
        return configured.validate(raw, model, route)
    require(raw.get('route') == route and raw.get('backend', '').startswith('Gecode native'),
            'Automatic driver route/backend differs')
    require(raw.get('algorithm_configuration') == dict(entry_point='solve_native_race',
        exploration_seconds=2, probe_node_limit=4096,
        candidates=['structural_auto', 'ordinary_native'], presolve='automatic',
        components='automatic', symmetry='identical_columns', cpu_warning=True),
        'Automatic racing configuration differs')
    # Shared witness/gap/status validation; only the explicitly different route
    # metadata is normalized for the established original-model validator.
    normalized = dict(raw, route='native', backend='Gecode native')
    checked = legacy.validate(normalized, model)
    require(common.finite(raw.get('backend_solve_seconds')) and
            0 <= raw['backend_solve_seconds'] <= raw['solve_seconds'] + 1e-5,
            'Invalid owning solve duration')
    checked['backend_result'] = raw
    return checked


class FinalSearch(configured.ConfiguredSearch):
    def __init__(self, output, binary, runtime, policy):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output/'models').mkdir()
        self.started = time.monotonic()
        self.binary = binary.resolve(strict=True)
        self.old_binary = ROOT/'build/capacity-scaling/fixed-driver/optimize-native-benchmark'
        self.runtime = runtime.resolve(strict=True)
        self.directories = {
            'before': [ROOT/'build/comparison-algorithms/before/lib'],
            'auto': [self.runtime/'gecode/optimize', self.runtime],
            'configured': [self.runtime/'gecode/optimize', self.runtime]}
        old = json.loads((ROOT/'build/category-scaling/results/report.json').read_text())
        old_manifest = ROOT/'build/comparison-algorithms/before/manifest.json'
        frozen = json.loads(old_manifest.read_text())
        require(frozen['source_head'] == '530a3b7837205d8255c6640425018831d3f8ee0e' and
                frozen['compiled_product'] == 'c2fabb78f1fc3bcfd7432eb71cfdb22656cd3f60',
                'Unexpected original pre-algorithm baseline')
        require(all(sha(old_manifest.parent/p['copy']) == p['sha256'] for p in frozen['files']),
                'Preserved original baseline changed')
        require(sha(self.old_binary) == legacy.DRIVER_HASH, 'Original driver changed')
        build_path = self.binary.parent/'build.local.json'
        build = json.loads(build_path.read_text())
        require(build['source_sha256'] == sha(HERE/'final_benchmark.cpp') and
                build['binary_sha256'] == sha(self.binary) and build['runtime_libraries_unchanged'],
                'Current driver build differs')
        self.current_libraries = build['runtime_libraries_sha256']
        require(all(sha(Path(p)) == h for p, h in self.current_libraries.items()),
                'Current runtime differs from driver build')
        current = [{'name': Path(p).name, 'sha256': h} for p, h in self.current_libraries.items()
                   if Path(p).name.startswith(('libgecodeoptimize.', 'libgecodeint.',
                       'libgecodekernel.', 'libgecodesearch.', 'libgecodesupport.'))]
        self.expected = {'before': old['provenance']['cohorts']['before'],
                         'auto': {'libraries': current}, 'configured': {'libraries': current}}
        self.policy = json.loads(policy.resolve(strict=True).read_text())
        require(set(self.policy['families']) == set(legacy.LIMITS), 'Policy families differ')
        self.models, self.records, self.decisions = {}, [], []
        paths = [HERE/name for name in ('benchmark_final.py', 'final_benchmark.cpp',
            'build_final_benchmark.py', 'export_final_benchmark.py', 'benchmark_configured.py', 'configured_benchmark.cpp',
            'benchmark_boundaries.py', 'boundary_instances.py', 'category_instances.py',
            'scaling_instances.py', 'benchmark_native_algorithms.py', 'benchmark_progress.py')]
        paths += [policy.resolve(), build_path, ROOT/'experiments/solver-bench/validate.py',
                  ROOT/'experiments/solver-bench/native.py']
        self.sources = {str(p.relative_to(ROOT)): sha(p) for p in paths}
        self.runtime_sources = {str(p.relative_to(ROOT)): sha(p) for p in
            (ROOT/'gecode/optimize').glob('*') if p.suffix in ('.hpp', '.cpp')}
        self.provenance = dict(source_head=subprocess.check_output(['git','rev-parse','HEAD'],
            cwd=ROOT,text=True).strip(), sources=self.sources, runtime_sources=self.runtime_sources,
            driver_sha256=sha(self.binary), original_driver_sha256=sha(self.old_binary),
            original_manifest_sha256=sha(old_manifest), original_source_head=frozen['source_head'],
            original_compiled_product=frozen['compiled_product'], expected_libraries=self.expected,
            comparison='Fresh serial observations: preserved pre-algorithm native baseline; current automatic racing; current frozen family presets.',
            current_runtime_libraries_sha256={str(Path(p).relative_to(ROOT)):h for p,h in self.current_libraries.items()},
            driver_build={k:v for k,v in build.items() if k!='runtime_libraries_sha256'})
        self.protocol = dict(seconds=10, capture_seconds=11, whole_seconds=legacy.WHOLE_SECONDS,
            max_attempts=legacy.MAX_ATTEMPTS, max_sizes_per_category=legacy.MAX_SIZES,
            limits=legacy.LIMITS, policy=self.policy,
            cohort_labels={'before':'Original Gecode','auto':'Auto + race','configured':'Configured'},
            selection='Independent anchor/doubling/bisection; adjacent two-repeat confirmation. Frozen family presets, no per-instance route selection. All discovery observations retained.',
            capacity='Largest sampled size passing both repetitions and every variant. Bisection assumes local monotonicity only as a sampling heuristic; reversals are reported. A ceiling is a lower bound on capacity, not a measured solver maximum.',
            timing='One thread, serial processes, steady-clock wall time around the entire owning solve; ten seconds includes all race probes, restart and selected search. No supplied starts.',
            automatic_racing=dict(exploration_seconds=2,probe_node_limit=4096,
                candidates=['structural_auto','ordinary_native'],
                warning='Exploration and restarting can increase total CPU use or solve time; an effective strategy can pay back that cost on longer solves.'),
            optimality='Backend-reported exact optimum; original witness independently checked. No independent optimum oracle.',
            generalization='Same deterministic seeded families as earlier policy selection, not an independent holdout.')
        self.complete = False
        self.publish()
        for cohort in COHORTS:
            self.execute('knapsack',8,'uncorrelated',cohort,0,probe=True)

    def route(self, category, model, cohort):
        if cohort == 'before': return 'native'
        if cohort == 'auto': return 'auto-race'
        selected = self.policy['families'][category]
        # Compact current DP has a larger exact admission window. This preset
        # deliberately uses native DP for every knapsack size in the frozen domain.
        return selected['route']

    def execute(self, category, size, variant, cohort, repetition, probe=False):
        require(len(self.records) < legacy.MAX_ATTEMPTS and time.monotonic()-self.started < legacy.WHOLE_SECONDS,
                'Preregistered whole-run allowance exhausted')
        key, model = self.model(category,size,variant)
        route = self.route(category,model,cohort)
        label = f'{key}-{cohort}-{route}-r{repetition}'
        record = dict(case=key,category=category,size=size,variant=variant,cohort=cohort,
                      repetition=repetition,route=route,probe=probe,status='pending',passed=False)
        self.records.append(record); self.publish()
        env = {k:v for k,v in os.environ.items() if not k.startswith('DYLD_')}
        env['DYLD_LIBRARY_PATH'] = ':'.join(map(str,self.directories[cohort]))
        if probe: env['DYLD_PRINT_LIBRARIES'] = '1'
        binary = self.old_binary if cohort == 'before' else self.binary
        command = [str(binary),'--input',str(self.output/'models'/(key+'.txt')),
                   '--kind',model['kind'],'--route',route,'--seconds','10']
        record['offset_start'] = time.monotonic()-self.started
        try:
            captured = legacy.capture(command,self.output,env,
                min(11,legacy.WHOLE_SECONDS-record['offset_start']),max_output=262144)
            record['offset_end'] = time.monotonic()-self.started
            stdout,stderr = captured.pop('stdout'),captured.pop('stderr')
            (self.output/(label+'.stdout')).write_bytes(stdout)
            (self.output/(label+'.stderr')).write_bytes(stderr)
            record.update(captured)
            require(captured['returncode']==0 and not captured['hard_timeout'] and not captured['output_limit'],
                    'Process capture failed: '+stderr.decode(errors='replace')[:500])
            raw = common.strict_json(stdout.decode())
            record.update(legacy.validate(raw,model) if cohort=='before' else validate(raw,model,route))
            if probe:
                loaded=set()
                for line in stderr.decode().splitlines():
                    if 'libgecode' not in line: continue
                    p=Path(line[line.index('/'):].strip()).resolve(strict=True)
                    require(p.parent in self.directories[cohort], 'Mixed loader paths')
                    loaded.add((p.name,sha(p)))
                expected={(p['name'],p['sha256']) for p in self.expected[cohort]['libraries']}
                require(loaded==expected,'Loaded runtime differs: '+str((loaded,expected)))
                self.provenance[cohort+'_loaded']=sorted(loaded)
            peers=[r['objective'] for r in self.records if r['case']==key and r.get('backend_reported_optimal')]
            require(len(set(peers))<=1,'Reported exact optima disagree across cohorts')
            if peers:
                for r in (r for r in self.records if r['case']==key):
                    require(r.get('objective') is None or r['objective']>=peers[0], 'Witness contradicts optimum')
                    require(r.get('best_bound') is None or r['best_bound']<=peers[0], 'Bound contradicts optimum')
        except Exception as error:
            record.update(status='error',error=str(error),passed=False); self.publish(); raise
        self.publish()
        print(label,record['status'],round(record.get('solve_seconds',0),6),flush=True)

    def run(self):
        # Reuse the frozen size-search algorithm with the three explicit cohorts.
        # Its final source/model/library audit checks runtime_sources (every current
        # optimize .cpp/.hpp hash) and loader hashes for all three runtimes.
        previous=legacy.DRIVER_HASH
        legacy.DRIVER_HASH=self.provenance['driver_sha256']
        try: legacy.Search.run(self)
        finally: legacy.DRIVER_HASH=previous
        self.provenance['integrity']['original_driver_unchanged'] = sha(self.old_binary)==self.provenance['original_driver_sha256']
        self.provenance['integrity']['all_current_libraries_unchanged'] = all(sha(Path(p))==h for p,h in self.current_libraries.items())
        self.complete = all(self.provenance['integrity'].values())
        self.publish()
        require(self.complete, 'Post-run driver/runtime integrity failed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--runtime-build',type=Path,required=True)
    parser.add_argument('--policy',type=Path,default=HERE/'final-policy.json')
    args=parser.parse_args()
    FinalSearch(args.output_dir,args.binary,args.runtime_build,args.policy).run()
