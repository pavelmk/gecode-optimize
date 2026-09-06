#!/usr/bin/env python3
"""Freeze and measure seven native model categories on a fixed size ladder.

Freeze first with --freeze-only --freeze-dir NEW_DIRECTORY. The separate measured
invocation requires that directory, its literal --manifest-sha256, one --binary,
repeated --before-libraries/--after-libraries, and a new --output-dir. The before
libraries must match the preserved pre-algorithm manifest. No builds, downloads,
starts or reference witnesses are supplied to the solver.

The same existing ten-second native benchmark executable runs both cohorts.
Each solve receives exactly 10 seconds; capture allows 11 seconds plus at most
0.5 seconds cleanup. The whole invocation has a cooperative 1500-second budget.
All 132 required observations remain recorded, including unattempted cases after
an exhausted budget or rejected loader probe. Internal solve time is primary.

Main knapsack size groups require both distributions to prove their independent
reference optimum in both repetitions. Its separate single-distribution stress
point never counts as an all-distribution main group. Other categories each have
one variant. Model variables include native auxiliary columns; input variables
and size units are retained separately. Capacity comparisons stay within each
category and describe this sampled ladder, not an estimated general maximum.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPETITIONS = 2
SOLVE_SECONDS = 10
PROCESS_SECONDS = 11
WHOLE_SECONDS = 1500
CATEGORIES = ('knapsack', 'assignment', 'facility_location', 'bin_packing',
              'production', 'native_tsp', 'weighted_queens')
TIERS = ('sanity', 'small', 'medium', 'large')
PLANNED = (
    [('knapsack', 'uncorrelated', n) for n in (8, 32, 128, 384)] +
    [('knapsack', 'correlated', n) for n in (8, 32, 128, 384)] +
    [('assignment', 'single', n) for n in (9, 25, 81, 256)] +
    [('facility_location', 'single', n) for n in (8, 28, 104, 300)] +
    [('bin_packing', 'single', n) for n in (15, 36, 65, 102)] +
    [('production', 'single', n) for n in (24, 48, 96, 192)] +
    [('native_tsp', 'single', n) for n in (4, 8, 12, 16)] +
    [('weighted_queens', 'single', n) for n in (4, 8, 10, 12)] +
    [('knapsack', 'uncorrelated', 512)]
)
EXPECTED_RUNS = len(PLANNED)*REPETITIONS*2


def model_columns(category, input_count):
    return input_count*({'native_tsp': 2, 'weighted_queens': 4}.get(category, 1))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def modules():
    return (load_module('category_common', HERE/'benchmark_native_algorithms.py'),
            load_module('category_instances', HERE/'category_instances.py'))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')


def source_files():
    return (Path(__file__).resolve(), HERE/'category_instances.py',
            HERE/'scaling_instances.py', HERE/'benchmark_native_algorithms.py',
            HERE/'benchmark_progress.py', HERE/'native_benchmark.cpp',
            ROOT/'experiments/solver-bench/validate.py',
            ROOT/'experiments/solver-bench/native.py')


def source_hashes():
    return {str(path.relative_to(ROOT)): sha(path) for path in source_files()}


def protocol():
    return dict(
        schema_version=1, purpose='sampled_category_capacity_within_ten_second_solver_budget',
        selection='Fixed families, prefixes, sizes and seeds before measurements; no replacement after outcomes.',
        planned=[dict(category=category, variant=variant, input_variables=n,
                      model_variables=model_columns(category, n))
                 for category, variant, n in PLANNED],
        repetitions=REPETITIONS, expected_measured_runs=EXPECTED_RUNS, loader_probes=2,
        backend='Native', guarantee='Exact', route='native', threads=1,
        random_seed=0, primal_start=False, relative_gap=0, absolute_gap=0,
        solver_seconds=SOLVE_SECONDS, process_seconds=PROCESS_SECONDS,
        whole_seconds=WHOLE_SECONDS,
        ordering='First repeat before/after per case; second after/before per case.',
        capacity_rule='Largest sampled main group with every variant independently verified Optimal within internal solve_seconds <= 10 in both repetitions. Knapsack requires both distributions; other categories have one variant.',
        boundary_rule='The 512-variable uncorrelated stress point is a separate single-variant group. Largest-any-group statistics retain its stress and variant_count; it cannot increase the all-variant main maximum.',
        reference_rule='Independent exact references generated before freezing; measured phase checks hashes and original witnesses without recomputing optima.',
    )


def ordered_models(models):
    require(isinstance(models, list) and len(models)==len(PLANNED),
            'Expected exactly 33 frozen models')
    keyed = {(m['category'], m['variant'], m['n']): m for m in models}
    require(len(keyed)==len(models) and set(keyed)==set(PLANNED),
            'Generator models differ from preregistered categories/variants/sizes')
    require(len({m['id'] for m in models})==len(models), 'Duplicate model ID')
    for i, key in enumerate(PLANNED):
        model = keyed[key]
        category, _, n = key
        stress = key==('knapsack', 'uncorrelated', 512)
        require(re.fullmatch(r'[A-Za-z0-9_-]+', model['id']) is not None,
                'Unsafe model ID')
        expected_kind = category if category in ('native_tsp', 'weighted_queens') else 'binary'
        require(model['kind']==expected_kind, 'Driver kind differs from fixed category')
        require(model['modelled_variables']==model_columns(category, n) and
                model['dimensions']['input_variables']==n and
                model['dimensions']['variables']==model['modelled_variables'],
                'Original input/modelled variable counts differ')
        require(model['stress'] is stress and
                (stress or model['tier']==TIERS[i % len(TIERS)]),
                'Fixed tier/stress metadata differs')
    return [keyed[key] for key in PLANNED]


def unit_metadata(model):
    return dict(id=model['id'], category=model['category'], variant=model['variant'],
                family=model['family'], tier=model['tier'], tier_size=model['tier_size'],
                size_unit=model['size_unit'], input_variables=model['n'],
                model_variables=model['modelled_variables'], dimensions=model['dimensions'],
                seed=model['seed'], stress=model['stress'], kind=model['kind'], route='native',
                objective=model['reference']['objective'],
                reference_method=model['reference']['method'], parameters=model['parameters'])


def freeze(directory):
    common, generator = modules()
    require(not directory.exists(), 'Freeze directory already exists')
    sources = source_hashes()
    started = time.monotonic()
    models = ordered_models(generator.generate_suite())
    directory.mkdir(parents=True)
    (directory/'models').mkdir()
    write(directory/'protocol.json', protocol())
    records = []
    for model in models:
        checked = generator.verify_reference(model)
        require(checked['valid'] and checked['witness_checked'] and
                not checked['optimality_recomputed'], 'Reference validation failed')
        stem = 'models/'+model['id']
        json_path, txt_path = directory/(stem+'.json'), directory/(stem+'.txt')
        write(json_path, model)
        txt_path.write_text(generator.encode_txt(model), encoding='utf8')
        require(common.strict_json(json_path.read_text())==model, 'JSON round-trip differs')
        records.append(dict(
            unit_metadata(model), semantic_sha256=generator.semantic_hash(model),
            json=stem+'.json', txt=stem+'.txt',
            json_sha256=sha(json_path), txt_sha256=sha(txt_path),
        ))
    require(source_hashes()==sources, 'Generation/measurement source changed while freezing')
    manifest = dict(
        schema_version=1, ready=True, created_utc=datetime.now(timezone.utc).isoformat(),
        protocol_sha256=sha(directory/'protocol.json'), protocol=protocol(),
        sources=sources, records=records, generation_seconds=time.monotonic()-started,
    )
    write(directory/'manifest.json', manifest)
    return dict(manifest_sha256=sha(directory/'manifest.json'), models=len(records),
                generation_seconds=manifest['generation_seconds'])


def inside(directory, relative):
    directory = directory.resolve(strict=True)
    name = Path(relative)
    require(not name.is_absolute() and '..' not in name.parts, 'Unsafe frozen relative path')
    path = directory/name
    require(not path.is_symlink(), 'Frozen files must not be symbolic links')
    resolved = path.resolve(strict=True)
    require(directory in resolved.parents and resolved.is_file(), 'Frozen file escaped its directory')
    return resolved


def read_frozen(directory, expected_hash, common, generator):
    require(re.fullmatch(r'[0-9a-f]{64}', expected_hash) is not None,
            'A literal manifest SHA256 is required')
    path = inside(directory, 'manifest.json')
    require(sha(path)==expected_hash, 'Frozen manifest hash mismatch')
    manifest = common.strict_json(path.read_text(encoding='utf8'))
    require(manifest.get('schema_version')==1 and manifest.get('ready') is True and
            manifest['protocol']==protocol(), 'Frozen protocol differs')
    require(sha(inside(directory, 'protocol.json'))==manifest['protocol_sha256'],
            'Frozen protocol bytes changed')
    require(manifest['sources']==source_hashes(), 'Frozen generator/measurement source changed')
    models, hashes = {}, {'manifest.json': expected_hash,
                         'protocol.json': manifest['protocol_sha256']}
    for record in manifest['records']:
        jp, tp = (inside(directory, record[key]) for key in ('json', 'txt'))
        require(sha(jp)==record['json_sha256'] and sha(tp)==record['txt_sha256'],
                'Frozen model bytes changed: '+record['id'])
        model = common.strict_json(jp.read_text(encoding='utf8'))
        require(all(record.get(key)==value for key, value in unit_metadata(model).items()),
                'Frozen manifest/model metadata mismatch')
        require(generator.encode_txt(model)==tp.read_text(encoding='utf8'),
                'Frozen TXT/JSON semantics differ')
        checked = generator.verify_reference(model)
        require(checked['valid'] and checked['witness_checked'] and
                not checked['optimality_recomputed'] and checked['objective']==record['objective'] and
                generator.semantic_hash(model)==record['semantic_sha256'],
                'Frozen reference identity/witness failed')
        models[record['id']] = model
        hashes[record['json']], hashes[record['txt']] = record['json_sha256'], record['txt_sha256']
    ordered = ordered_models(list(models.values()))
    require([model['id'] for model in ordered]==[record['id'] for record in manifest['records']],
            'Frozen measurement ordering differs')
    return manifest, models, hashes


def checked_observation(raw, unit, model, common, generator):
    descriptor = dict(unit, route='native')
    checked = common.checked_result(raw, descriptor, model, generator, generator)
    checked['proved_within_limit'] = checked['completed'] and checked['solve_seconds']<=SOLVE_SECONDS
    return checked


def summarize(records, manifest, provenance, valid, elapsed):
    result = dict(
        schema_version=1, comparison_valid=bool(valid), elapsed_seconds=elapsed,
        required_runs=EXPECTED_RUNS, recorded_runs=len(records), repetitions=REPETITIONS,
        solver_seconds=SOLVE_SECONDS, primary_measure='largest_main_group_proved_model_variables',
        provenance=provenance, cases=[], categories=[],
        caveats=[
            'One seeded instance per variant/size, repeated twice; repetitions are not independent samples.',
            'Largest sampled size is an observed ladder result, not the true solver capacity.',
            'Every variant and repetition must prove the independently checked optimum within 10 seconds.',
            'The knapsack stress group has only one variant; it is separate from the two-variant main ladder.',
            'Model variables include auxiliary columns; input variables, cities/queens and dimensions remain explicit.',
            'No cross-category capacity ratio or pooled variable count is defined.',
            'All failures and capped solves remain in the denominator; no time ratio uses a censored solve.',
            'Internal solve times are primary; external times also include startup, parsing and model construction.',
            'Capacity, constraints and formulation affect complexity; variable count alone does not.',
        ],
    )
    for unit in manifest['records']:
        keys = ('id', 'category', 'variant', 'family', 'tier', 'tier_size', 'size_unit',
                'input_variables', 'model_variables', 'dimensions', 'stress', 'kind',
                'objective', 'parameters')
        case = {key: unit[key] for key in keys}
        groups = {}
        for cohort in ('before', 'after'):
            rows = sorted((r for r in records if r['case']==unit['id'] and r['cohort']==cohort),
                          key=lambda r: r['repetition'])
            groups[cohort] = rows
            internal = [r.get('solve_seconds') for r in rows]
            external = [r.get('external_seconds') for r in rows]
            complete_slots = [r['repetition'] for r in rows]==list(range(1, REPETITIONS+1))
            case[cohort] = dict(
                required_runs=REPETITIONS, recorded_runs=len(rows),
                attempted_runs=sum(r.get('attempted', True) for r in rows),
                proved=sum(r['proved_within_limit'] for r in rows),
                proved_all=bool(valid and complete_slots and all(r['proved_within_limit'] for r in rows)),
                statuses=[r['status'] for r in rows], internal_seconds=internal,
                external_seconds=external,
                median_internal_seconds=statistics.median(internal) if complete_slots and all(v is not None for v in internal) else None,
                median_external_seconds=statistics.median(external) if complete_slots and all(v is not None for v in external) else None,
                objectives=[r.get('objective') for r in rows], bounds=[r.get('best_bound') for r in rows],
            )
        all_proved = case['before']['proved_all'] and case['after']['proved_all']
        for clock in ('solve_seconds', 'external_seconds'):
            ratios = [b[clock]/a[clock] for a, b in zip(groups['before'], groups['after'])
                      if a.get(clock, 0)>0 and b.get(clock, 0)>0] if all_proved else []
            case['median_paired_'+clock+'_ratio_after_before'] = statistics.median(ratios) if len(ratios)==REPETITIONS else None
        result['cases'].append(case)
    for category in CATEGORIES:
        cases = [case for case in result['cases'] if case['category']==category]
        item = dict(category=category, main_groups=[], stress_groups=[])
        grouped = [(tier, False, [c for c in cases if not c['stress'] and c['tier']==tier])
                   for tier in TIERS]
        grouped += [(c['tier'], True, [c]) for c in cases if c['stress']]
        for tier, stress, selected in grouped:
            expected_variants = ['uncorrelated'] if stress else (
                ['correlated', 'uncorrelated'] if category=='knapsack' else ['single'])
            require(sorted(c['variant'] for c in selected)==expected_variants,
                    'Summary lacks the complete preregistered variant group')
            require(len({(c['input_variables'], c['model_variables']) for c in selected})==1,
                    'Cannot pool variants with different variable counts')
            group = dict(tier=tier, stress=stress, variant_count=len(selected),
                         variants=sorted(c['variant'] for c in selected),
                         cases=[c['id'] for c in selected],
                         input_variables=selected[0]['input_variables'],
                         model_variables=selected[0]['model_variables'])
            for cohort in ('before', 'after'):
                group[cohort] = dict(
                    required_runs=len(selected)*REPETITIONS,
                    recorded_runs=sum(c[cohort]['recorded_runs'] for c in selected),
                    proved=sum(c[cohort]['proved'] for c in selected),
                    proved_all=bool(valid and all(c[cohort]['proved_all'] for c in selected)),
                    statuses=[status for c in selected for status in c[cohort]['statuses']],
                )
            item['stress_groups' if stress else 'main_groups'].append(group)
        for cohort in ('before', 'after'):
            main = [g for g in item['main_groups'] if g[cohort]['proved_all']]
            any_group = [g for g in item['main_groups']+item['stress_groups'] if g[cohort]['proved_all']]
            largest_main = max((g['model_variables'] for g in main), default=None)
            largest_any = max(any_group, key=lambda g: g['model_variables'], default=None)
            item[cohort] = dict(
                largest_main_group_proved_model_variables=largest_main,
                largest_any_sampled_group_proved_model_variables=largest_any['model_variables'] if largest_any else None,
                largest_any_sampled_group_variant_count=largest_any['variant_count'] if largest_any else None,
                largest_any_sampled_group_stress=largest_any['stress'] if largest_any else None,
                proved_main_groups=len(main), total_main_groups=len(item['main_groups']),
                larger_main_groups_unproved_model_variables=[g['model_variables'] for g in item['main_groups']
                    if largest_main is not None and g['model_variables']>largest_main and not g[cohort]['proved_all']],
            )
        before, after = (item[c]['largest_main_group_proved_model_variables'] for c in ('before', 'after'))
        item['ratio_of_largest_main_group_proved_model_variables'] = after/before if before and after else None
        result['categories'].append(item)
    return result


def pending_record(unit, cohort, repetition):
    return dict(case=unit['id'], family=unit['family'], category=unit['category'],
                variant=unit['variant'], input_variables=unit['input_variables'],
                model_variables=unit['model_variables'], tier=unit['tier'], stress=unit['stress'],
                cohort=cohort, repetition=repetition, attempted=False, completed=False,
                proved_within_limit=False, witness_checked=False, expected_objective=unit['objective'])


def planned_slots(manifest):
    for repetition in range(1, REPETITIONS+1):
        for unit in manifest['records']:
            for cohort in (('before', 'after') if repetition==1 else ('after', 'before')):
                yield unit, cohort, repetition


def measure(args, started):
    deadline = started+WHOLE_SECONDS
    common, generator = modules()
    frozen = args.freeze_dir.resolve(strict=True)
    manifest, models, frozen_hashes = read_frozen(frozen, args.manifest_sha256, common, generator)
    binary = args.binary.resolve(strict=True)
    directories = {cohort: [path.resolve(strict=True) for path in paths] for cohort, paths in
                   (('before', args.before_libraries), ('after', args.after_libraries))}
    require(all(path.is_dir() for paths in directories.values() for path in paths), 'Library directory required')
    require(not set(directories['before']) & set(directories['after']), 'Library cohorts overlap')
    preserved_path = (args.baseline_manifest or directories['before'][0].parent/'manifest.json').resolve(strict=True)
    preserved, expected_before = common.baseline_manifest(preserved_path)
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    capture = load_module('category_capture', HERE/'benchmark_progress.py').capture_command
    replacements = sorted([(str(ROOT), 'REPOSITORY'), (str(frozen), 'FROZEN'),
                           (str(destination), 'OUTPUT'), (str(binary), 'BINARY')] +
                          [(str(path), cohort.upper()+'_LIBRARIES') for cohort, paths in directories.items() for path in paths],
                          key=lambda item: len(item[0]), reverse=True)
    def publish(name, value):
        write(destination/name, common.public_copy(value, replacements))
    runtime_sources = {str(path.relative_to(ROOT)): sha(path)
                       for folder in (ROOT/'gecode/optimize', ROOT/'gecode/int/linear')
                       for path in sorted(folder.rglob('*')) if path.suffix in ('.cpp', '.hpp')}
    provenance = dict(driver_name=binary.name, driver_sha256=sha(binary),
                      source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=2).strip(),
                      runtime_source_sha256=runtime_sources, measurement_source_sha256=source_hashes(),
                      frozen_manifest_sha256=args.manifest_sha256,
                      frozen_protocol_sha256=manifest['protocol_sha256'], preserved_baseline=preserved, cohorts={})
    report = dict(schema_version=1, started_utc=datetime.now(timezone.utc).isoformat(),
                  expected_runs=EXPECTED_RUNS, protocol=protocol(), frozen_manifest=manifest,
                  provenance=provenance, comparison_valid=False, loader_probes=[], records=[
                      dict(pending_record(unit, cohort, repetition), status='not_run_pending')
                      for unit, cohort, repetition in planned_slots(manifest)])
    loaded, local = {}, {}
    def execute(unit, cohort, label, trace=False):
        remaining = deadline-time.monotonic()
        require(remaining>0, 'Whole-run allowance exhausted')
        command = [str(binary), '--input', str(inside(frozen, unit['txt'])), '--kind', unit['kind'],
                   '--route', 'native', '--seconds', str(SOLVE_SECONDS)]
        environment = {key: value for key, value in os.environ.items() if not key.startswith('DYLD_')}
        environment['DYLD_LIBRARY_PATH'] = ':'.join(map(str, directories[cohort]))
        if trace:
            environment['DYLD_PRINT_LIBRARIES'] = '1'
        utc = datetime.now(timezone.utc).isoformat()
        offset_start = time.monotonic()-started
        outcome = capture(command, destination, environment, min(PROCESS_SECONDS, remaining), max_output=262144)
        offset_end = time.monotonic()-started
        stdout, stderr = outcome.pop('stdout'), outcome.pop('stderr')
        (destination/(label+'.stdout')).write_bytes(stdout)
        (destination/(label+'.stderr')).write_bytes(stderr)
        outcome.update(started_utc=utc, invocation_offset_start_seconds=offset_start,
                       invocation_offset_end_seconds=offset_end,
                       stdout_file=label+'.stdout', stderr_file=label+'.stderr',
                       command=['BINARY', '--input', unit['txt'], '--kind', unit['kind'],
                                '--route', 'native', '--seconds', str(SOLVE_SECONDS)])
        return outcome, stdout.decode('utf8', errors='replace'), stderr.decode('utf8', errors='replace')
    publish('report.json', report)
    for cohort in ('before', 'after'):
        probe_record = dict(cohort=cohort, status='pending')
        report['loader_probes'].append(probe_record)
        publish('report.json', report)
        try:
            unit = manifest['records'][0]
            probe, out, err = execute(unit, cohort, 'provenance-'+cohort, trace=True)
            probe_record.update(probe)
            publish('report.json', report)  # Retain even rejected probe outcomes.
            require(probe['returncode']==0 and not probe['hard_timeout'] and not probe['output_limit'], 'Loader probe failed')
            checked_observation(common.strict_json(out), unit, models[unit['id']], common, generator)
            paths = set()
            for line in err.splitlines():
                if 'libgecode' not in line:
                    continue
                require('/' in line, 'Malformed loader trace')
                path = Path(line[line.index('/'):].strip()).resolve(strict=True)
                require(path.parent in directories[cohort], 'Unexpected mixed runtime library')
                paths.add(path)
            require(any(path.name=='libgecodeoptimize.dylib' for path in paths), 'No observed Optimize library')
            libraries = [dict(name=path.name, sha256=sha(path)) for path in sorted(paths)]
            if cohort=='before':
                require(all(expected_before.get(item['name'])==item['sha256'] for item in libraries), 'Preserved baseline library differs')
            loaded[cohort] = paths
            provenance['cohorts'][cohort] = dict(libraries=libraries, loader_probe=probe)
            local[cohort] = dict(directories=list(map(str, directories[cohort])), loaded=list(map(str, sorted(paths))))
            if cohort=='after':
                facade_hashes = [next(item['sha256'] for item in provenance['cohorts'][name]['libraries']
                                     if item['name']=='libgecodeoptimize.dylib') for name in ('before', 'after')]
                require(facade_hashes[0]!=facade_hashes[1], 'Candidate facade is byte-identical to the preserved baseline')
            probe_record['status'] = 'validated'
            publish('report.json', report)
        except (ValueError, KeyError, TypeError, OverflowError, OSError, RuntimeError) as error:
            probe_record.update(status='failed', error=str(error))
            report['records'] = [dict(pending_record(unit, name, repetition),
                status='not_run_preflight', error='Loader provenance preflight rejected')
                for unit, name, repetition in planned_slots(manifest)]
            report.update(preflight_failure=True, elapsed_seconds=time.monotonic()-started,
                          finished_utc=datetime.now(timezone.utc).isoformat())
            publish('report.json', report)
            publish('summary.json', summarize(report['records'], manifest, provenance, False, report['elapsed_seconds']))
            print('Category loader preflight failed:', str(error), flush=True)
            return 1
    write(destination/'paths.local.json', dict(binary=str(binary), frozen=str(frozen),
                                              baseline_manifest=str(preserved_path), cohorts=local))
    publish('report.json', report)
    for slot, (unit, cohort, repetition) in enumerate(planned_slots(manifest)):
        label = f"{unit['id']}-r{repetition}-{cohort}"
        record = pending_record(unit, cohort, repetition)
        if time.monotonic()>=deadline:
            record.update(status='not_run_whole_limit', error='Required case could not start within whole-run allowance')
        else:
            try:
                record['attempted'] = True
                outcome, out, err = execute(unit, cohort, label)
                record.update(outcome)
                if outcome['hard_timeout']:
                    record['status'] = 'external_timeout'
                elif outcome['output_limit']:
                    record['status'] = 'output_limit'
                elif outcome['returncode']!=0:
                    record['status'] = 'process_error'
                else:
                    record.update(checked_observation(common.strict_json(out), unit, models[unit['id']], common, generator))
            except (ValueError, KeyError, TypeError, OverflowError, OSError, RuntimeError) as error:
                record.update(status='validation_error', error=str(error))
        report['records'][slot] = record
        publish('report.json', report)
        print(label, record['status'], record.get('solve_seconds'), flush=True)
    integrity = dict(
        frozen_unchanged=all(sha(inside(frozen, name))==digest for name, digest in frozen_hashes.items()),
        measurement_source_unchanged=source_hashes()==provenance['measurement_source_sha256'],
        runtime_source_unchanged=all(sha(ROOT/name)==digest for name, digest in runtime_sources.items()),
        driver_unchanged=sha(binary)==provenance['driver_sha256'],
        preserved_manifest_unchanged=sha(preserved_path)==preserved['manifest_sha256'],
        libraries_unchanged=all(sha(path)==next(item['sha256'] for item in provenance['cohorts'][cohort]['libraries']
                                              if item['name']==path.name)
                                for cohort, paths in loaded.items() for path in paths),
    )
    failures = {'not_run_pending', 'not_run_preflight', 'not_run_whole_limit', 'external_timeout', 'output_limit', 'process_error', 'validation_error'}
    valid = (all(integrity.values()) and len(report['records'])==EXPECTED_RUNS and time.monotonic()<deadline and
             not any(record['status'] in failures for record in report['records']))
    report.update(integrity=integrity, comparison_valid=bool(valid),
                  finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic()-started)
    summary = summarize(report['records'], manifest, provenance, valid, report['elapsed_seconds'])
    publish('report.json', report)
    publish('summary.json', summary)
    if time.monotonic()>=deadline:
        valid = False
        report.update(comparison_valid=False, elapsed_seconds=time.monotonic()-started,
                      final_publication_limit=True)
        summary = summarize(report['records'], manifest, provenance, False, report['elapsed_seconds'])
        publish('report.json', report)
        publish('summary.json', summary)
    print('Category panel:', len(report['records']), 'records; comparison valid:', bool(valid))
    return 0 if valid else 1


def main(argv=None):
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze-only', action='store_true')
    parser.add_argument('--freeze-dir', type=Path, required=True)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--before-libraries', type=Path, action='append')
    parser.add_argument('--after-libraries', type=Path, action='append')
    parser.add_argument('--baseline-manifest', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    if args.freeze_only:
        print(json.dumps(freeze(args.freeze_dir.resolve()), indent=2))
        return 0
    for name in ('manifest_sha256', 'binary', 'before_libraries', 'after_libraries', 'output_dir'):
        if not getattr(args, name):
            parser.error('--'+name.replace('_', '-')+' is required for measurement')
    if sys.platform!='darwin':
        parser.error('Measured loader provenance currently requires macOS')
    return measure(args, started)


if __name__=='__main__':
    raise SystemExit(main())
