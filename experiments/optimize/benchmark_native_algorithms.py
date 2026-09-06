#!/usr/bin/env python3
"""Fixed native before/after panel: existing inputs, one binary, owning exact APIs.

Run only after all project builds/tests are quiet. No build, fetch or source
mutation occurs. --freeze-only validates immutable inputs and writes their
manifest without launching a process. Measured runs use three alternating pairs,
two-second solver limits, three-second child limits and a 240-second outer cap.

Example from the repository root, after building optimize-native-benchmark:
  python3 experiments/optimize/benchmark_native_algorithms.py \\
    --binary build/native-compat/bin/optimize-native-benchmark \\
    --before-libraries build/comparison-algorithms/before/lib \\
    --after-libraries build/native-compat/gecode/optimize \\
    --after-libraries build/native-compat \\
    --output-dir build/comparison-algorithms/results

The before directory must match its preserved manifest; building today's source
does not reconstruct that historical product. Directory options may be repeated.
The output directory must not exist. summary.json/report.json omit host paths;
paths.local.json and raw stderr retain local reproduction details. The eight
stored reference optima are hash-pinned and their witnesses are revalidated,
not recomputed or passed to the solver. Ordinary node counts are unavailable.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / 'experiments/solver-bench'
FROZEN_INPUTS = [
    {
        "id": "test_knapsack_large_1312000",
        "kind": "binary",
        "stem": "instances/test_knapsack_large_1312000",
        "json_sha256": "7058d2ad2e22d58f800c860f451b73f916ddb326974fd0c21432b9af5e8e63cd",
        "txt_sha256": "78b2364ca6925017ca930517489c7fc56cf6e908c7c8e033e2a2e1c254a9e28e",
        "objective": -2464,
        "semantic_sha256": "0e974e09f297a80d3615b5468c02b9b2e504de97e79deba0b7e46bb0efd31741"
    },
    {
        "id": "test_facility_location_large_1812000",
        "kind": "binary",
        "stem": "instances/test_facility_location_large_1812000",
        "json_sha256": "b93e5c15d83bff49cd4aee1dde60df72638a37d4674299e3629fa01406659d65",
        "txt_sha256": "e627b916143364e246990b9451164c9f3b1c1ec98730680b91ad1a0d06bb46a1",
        "objective": 240,
        "semantic_sha256": "e1860a148b48ab19be2fb3d23d4e3323b958ee0f969c32b843e02074f4853af2"
    },
    {
        "id": "test_assignment_large_2012000",
        "kind": "binary",
        "stem": "instances/test_assignment_large_2012000",
        "json_sha256": "86186c3a82b3012c48da2d5362e354bbc32ff8d7c163df6e31f79b7e6d68da78",
        "txt_sha256": "785ac7cb5bcea26a813715f5cfe593eb80ca512aa6928d1444d32ee61b60bdf1",
        "objective": 164,
        "semantic_sha256": "125ff7049cca1b7fa457c9c147a513a04875d81d2179bf8272d91242e2afee05"
    },
    {
        "id": "test_tsp_large_2412000",
        "kind": "binary",
        "stem": "instances/test_tsp_large_2412000",
        "json_sha256": "984de574f27830e6cb7b5ce94383b335ed90624c9963d8da31c9e243dfa8eb45",
        "txt_sha256": "1659002ab70dd6ba37bef182d0577654542ad810d227a450998a3b59cae8afdd",
        "objective": 168,
        "semantic_sha256": "ee5430e34e118638173bf3373858eb42d0c6fa4cf710420fac97d4dd74d481a8"
    },
    {
        "id": "test_production_large_2712000",
        "kind": "binary",
        "stem": "instances/test_production_large_2712000",
        "json_sha256": "d6e359a10be09c35a9ee2c8b53b15c16ce6bd7defcb90f572d70ca261104e87a",
        "txt_sha256": "5991ecd6e9795e3084780551212c3e93722b63bb6c6bb3e0bb59c628aeed25a8",
        "objective": 512,
        "semantic_sha256": "aec49df05779029d8b78b322837a807a6c2401081abbc004692db664c80f7030"
    },
    {
        "id": "test_bin_packing_small_2202000",
        "kind": "binary",
        "stem": "instances/test_bin_packing_small_2202000",
        "json_sha256": "cb6b44423fd1f72565301576a6da35360d66e39a2a23a964ca641bf2a4ba09ba",
        "txt_sha256": "dc779b85821f0b752eb2bb5313f3cffdce03474dc39620545e0baaf368780943",
        "objective": 3,
        "semantic_sha256": "f2b1b623a08201a1d16b003201fa02bedd2d64ae93c581ac06c75145f752827c"
    },
    {
        "id": "test_native_tsp_large_9112000",
        "kind": "native_tsp",
        "stem": "native-instances/test_native_tsp_large_9112000",
        "json_sha256": "7946df28b5f4f2a85db52932c3a61431c8dcf950709fed69d2969e8a9d238dec",
        "txt_sha256": "b8c212e821fe3d5f2a90035898b8bcf295fdd8fb41e71f134c55db587bb289b8",
        "objective": 390,
        "semantic_sha256": "97070e1d2126f3dea60fe61a7ec586b8ce8c86b38e3d739b9ef360bda14961e3"
    },
    {
        "id": "test_weighted_queens_large_9312000",
        "kind": "weighted_queens",
        "stem": "native-instances/test_weighted_queens_large_9312000",
        "json_sha256": "47d48e4ad3ed2cd384ffab6111570081801af12c4b1e4f7ab811b05c08c45bca",
        "txt_sha256": "d6c023e6f6b2ae1e61bde3228337c4b84a596440e9a46edfe446b1bd6c79ba1a",
        "objective": 129,
        "semantic_sha256": "7ee39f26c494d0d5bfd66cb8f4113acdf9d7d959abdf3f9c08c08721a15dba0f"
    }
]
REPETITIONS, SOLVE_SECONDS, PROCESS_SECONDS, WHOLE_SECONDS = 3, 2, 3, 240
BASELINE_SOURCE = '530a3b7837205d8255c6640425018831d3f8ee0e'
BASELINE_COMPILED = 'c2fabb78f1fc3bcfd7432eb71cfdb22656cd3f60'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(text):
    def number(token):
        value = float(token)
        require(math.isfinite(value), 'Nonfinite JSON number')
        return value
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: '+key)
            result[key] = value
        return result
    return json.loads(text, parse_float=number, object_pairs_hook=object_pairs,
                      parse_constant=lambda token: number(token))


def expected_binary_text(model):
    lines = [f"{model['n']} {len(model['rows'])}", ' '.join(map(str, model['c']))]
    for row in model['rows']:
        lines.append(' '.join(map(str, [row['b'], len(row['a'])] +
                                  [item for pair in row['a'] for item in pair])))
    present = 'incumbent' in model
    lines.append('incumbent '+str(int(present)))
    if present:
        lines.append(' '.join(map(str, model['incumbent'])))
    return '\n'.join(lines)+'\n'


def expected_native_text(model):
    n = model['size']
    return (f"{model['family']} {n} {model.get('machines',0)} {n}\n" +
            ' '.join(str(value) for row in model['data'] for value in row)+'\n' +
            ' '.join(map(str, model['incumbent']))+'\n')


def prepare_inputs():
    # Existing independent mathematical validators; no Optimize/compiler oracle.
    sys.path.insert(0, str(SUITE))
    import validate
    import native
    models, manifest = {}, []
    for item in FROZEN_INPUTS:
        jp, tp = (SUITE/(item['stem']+suffix) for suffix in ('.json', '.txt'))
        require(sha(jp) == item['json_sha256'] and sha(tp) == item['txt_sha256'],
                'Frozen input bytes changed: '+item['id'])
        model = strict_json(jp.read_text())
        encoded = expected_binary_text(model) if item['kind']=='binary' else expected_native_text(model)
        require(encoded == tp.read_text(), 'TXT/JSON semantic mismatch: '+item['id'])
        semantic = validate.input_hash(model) if item['kind']=='binary' else native.mathematical_hash(model)
        require(semantic == item['semantic_sha256'] == model['reference']['input_sha256'],
                'Reference identity mismatch: '+item['id'])
        require(model['reference']['status']=='optimal' and model['reference']['objective']==item['objective'],
                'Frozen independent optimum mismatch')
        # Exact references were generated before this comparison. Freeze their
        # complete JSON bytes and validate the retained witness independently;
        # do not spend the run allowance repeating DP/Held-Karp enumeration.
        checker = validate if item['kind']=='binary' else native
        witness = checker.validate_assignment(model, model['reference']['assignment'])
        require(witness['valid'] and witness['objective']==item['objective'],
                'Stored independent optimum witness failed: '+item['id'])
        models[item['id']] = model
        manifest.append(dict(item, reference_method=model['reference']['method'],
                             input_variables=model['n'], reference_record_verified=True,
                             reference_witness_checked=True, reference_recomputed=False))
    return models, manifest, validate, native


def units():
    return [dict(item, route='native', unit=item['id']+'-native') for item in FROZEN_INPUTS] + [
        dict(FROZEN_INPUTS[index], route='dfs', unit=FROZEN_INPUTS[index]['id']+'-dfs') for index in (0,5)]


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def checked_result(raw, unit, model, binary_validator, native_validator):
    require(type(raw.get('schema_version')) is int and raw['schema_version']==1 and
            raw.get('kind')==unit['kind'] and raw.get('route')==unit['route'],
            'Driver identity/protocol mismatch')
    expected_backend = 'Gecode native' if unit['route']=='native' else 'Gecode native frontier'
    require(raw.get('guarantee')=='exact' and raw.get('backend')==expected_backend,
            'Wrong backend or guarantee')
    require(isinstance(raw.get('backend_version'),str) and raw['backend_version'],
            'Missing backend version')
    require(raw.get('start_submitted') is False, 'Unexpected solver start')
    require(type(raw.get('model_id')) is int and raw['model_id']>0 and
            type(raw.get('revision')) is int and raw['revision']>=0, 'Invalid original identity')
    for name in ('build_seconds','solve_seconds','driver_seconds'):
        require(finite(raw.get(name)) and raw[name]>=0, 'Invalid elapsed time')
    require(raw['build_seconds']+raw['solve_seconds']<=raw['driver_seconds']+1e-6,
            'Inconsistent driver/solve elapsed times')
    for name in ('objective','best_bound','absolute_gap','relative_gap'):
        require(raw.get(name) is None or finite(raw[name]), 'Invalid scalar '+name)
    require(raw.get('absolute_gap') is None or raw['absolute_gap']>=0, 'Negative gap')
    require(raw.get('relative_gap') is None or raw['relative_gap']>=0, 'Negative gap')
    status = raw.get('status')
    require(status in ('optimal','time_limit','node_limit','memory_limit','cancelled','unknown'),
            'Unsupported/error or impossible source status: '+str(status))
    n = model['n']
    expected_columns = n if unit['kind']=='binary' else n*(2 if unit['kind']=='native_tsp' else 4)
    expected_rows = len(model['rows']) if unit['kind']=='binary' else (0 if unit['kind']=='native_tsp' else 2*n)
    expected_globals = 0 if unit['kind']=='binary' else n+(1 if unit['kind']=='native_tsp' else 3)
    require((raw.get('model_columns'),raw.get('model_rows'),raw.get('model_globals')) ==
            (expected_columns,expected_rows,expected_globals), 'Compiled workload dimensions differ')
    if unit['route']=='native':
        require(all(raw.get(k) is None for k in ('nodes','expanded_nodes','budget_nodes','peak_open_nodes','unresolved_regions')),
                'Ordinary solve invented unavailable counters')
    else:
        for name in ('nodes','expanded_nodes','budget_nodes','peak_open_nodes','unresolved_regions'):
            require(type(raw.get(name)) is int and raw[name]>=0, 'Invalid frontier counter')
        require(raw['nodes']==raw['budget_nodes'] and raw['expanded_nodes']<=raw['nodes'] and
                raw['peak_open_nodes']<=1024, 'Frontier accounting mismatch')
    point = raw.get('has_solution')
    require(type(point) is bool and type(raw.get('solution_validated')) is bool, 'Invalid presence flag')
    require(raw['solution_validated']==point, 'Solution presence disagreement')
    assignment, full = raw.get('assignment'), raw.get('full_values')
    require(type(assignment) is list and type(full) is list, 'Missing assignments')
    checked = False
    if point:
        require(len(assignment)==n and len(full)==expected_columns, 'Original assignment length')
        require(all(finite(v) and v==round(v) for v in assignment+full), 'Nonintegral/nonfinite exact assignment')
        assignment = list(map(int, assignment));full = list(map(int, full))
        validation = (binary_validator if unit['kind']=='binary' else native_validator).validate_assignment(model, assignment)
        require(validation['valid'] and validation['objective']==raw['objective'], 'Independent original witness/objective failed')
        expected_full = assignment[:]
        if unit['kind']=='weighted_queens':
            expected_full += [value for i,x in enumerate(assignment) for value in (x+i,x-i)]
        if unit['kind']!='binary':
            expected_full += [model['data'][i][x] for i,x in enumerate(assignment)]
        require(full==expected_full, 'Original/auxiliary global assignment mapping failed')
        require(raw['objective']>=unit['objective'], 'Incumbent contradicts independent minimum')
        checked = True
    else:
        require(not assignment and not full and raw['objective'] is None, 'Unexpected absent-point data')
    bound = raw['best_bound']
    if bound is not None:
        require(bound<=unit['objective'] and (not point or bound<=raw['objective']), 'Bound contradicts original optimum')
    if point and bound is not None:
        gap = abs(raw['objective']-bound)
        require(raw['absolute_gap']==gap and abs(raw['relative_gap']-gap/max(1,abs(raw['objective']),abs(bound)))<=1e-12,
                'Reported gap inconsistent')
    else:
        require(raw['absolute_gap'] is None and raw['relative_gap'] is None, 'Gaps without both sides')
    completed = status=='optimal'
    if completed:
        require(point and raw['objective']==unit['objective'] and bound==raw['objective'],
                'Claimed optimum differs from independent oracle')
        if unit['route']=='dfs':require(raw['unresolved_regions']==0, 'Completed frontier remains unresolved')
    return dict(completed=completed, witness_checked=checked, status=status,
                objective=raw['objective'], best_bound=bound,
                absolute_primal_gap_to_oracle=(raw['objective']-unit['objective']) if point else None,
                solve_seconds=raw['solve_seconds'], nodes=raw['nodes'], backend_result=raw)


def baseline_manifest(path):
    data = strict_json(path.read_text(encoding='utf8'))
    require(data.get('source_head')==BASELINE_SOURCE and
            data.get('compiled_product')==BASELINE_COMPILED,
            'Preserved baseline source/product identity differs')
    libraries = {}
    for entry in data['files']:
        relative = Path(entry['copy'])
        require(not relative.is_absolute() and '..' not in relative.parts,
                'Malformed preserved baseline entry')
        if relative.parent != Path('lib'):
            continue
        name, digest = relative.name, entry['sha256']
        require(re.fullmatch(r'[0-9a-f]{64}', digest) is not None,
                'Malformed preserved baseline digest')
        require(name not in libraries or libraries[name]==digest,
                'Conflicting preserved baseline entries')
        libraries[name] = digest
    require('libgecodeoptimize.dylib' in libraries, 'Preserved baseline facade missing')
    return dict(manifest_sha256=sha(path), source_head=BASELINE_SOURCE,
                compiled_product=BASELINE_COMPILED), libraries


def public_copy(value, replacements):
    """Keep host paths only in *.local.json and raw process logs."""
    if isinstance(value, str):
        for source, replacement in replacements:
            value = value.replace(source, replacement)
        # Diagnostics can include an unexpected OS path; it is not provenance.
        return re.sub(r'/(?:Users|private|home|tmp|Volumes)/[^\s\"\']+', '<HOST_PATH>', value)
    if isinstance(value, dict):
        return {key: public_copy(item,replacements) for key,item in value.items()}
    if isinstance(value, list):
        return [public_copy(item,replacements) for item in value]
    return value


def main(argv=None):
    started=time.monotonic();deadline=started+WHOLE_SECONDS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-libraries',type=Path,action='append',required=True)
    parser.add_argument('--after-libraries',type=Path,action='append',required=True)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--baseline-manifest',type=Path,
                        help='Defaults to ../manifest.json beside the first before-library directory')
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args(argv)
    if sys.platform!='darwin':parser.error('Actual dyld runtime provenance is macOS-specific')
    dest=args.output_dir.resolve();dest.mkdir(parents=True,exist_ok=False)
    models, inputs, validator, native_validator=prepare_inputs()
    write(dest/'inputs.json',inputs)
    panel=units()
    write(dest/'protocol.json',dict(schema_version=1,units=[u['unit'] for u in panel],repetitions=REPETITIONS,
          solver_seconds=SOLVE_SECONDS,process_seconds=PROCESS_SECONDS,whole_seconds=WHOLE_SECONDS,
          backend='Native',guarantee='Exact',threads=1,random_seed=0,
          absolute_gap=0,relative_gap=0,
          warm_start=False,baseline_source=BASELINE_SOURCE,
          baseline_compiled=BASELINE_COMPILED,
          frontier='DepthFirst, no optional branching/LP, max_open_nodes1024',
          ordinary_nodes='Not present in SolveResult; reported as null',inputs=inputs))
    if args.freeze_only:
        print('Frozen 10 units and 8 independent input/oracle pairs; no subprocess launched.');return 0
    binary=args.binary.resolve(strict=True)
    directories={c:[p.resolve(strict=True) for p in paths] for c,paths in
                 [('before',args.before_libraries),('after',args.after_libraries)]}
    for paths in directories.values():require(all(p.is_dir() for p in paths),'Library directory required')
    require(not set(directories['before'])&set(directories['after']),'Cohorts must have distinct library directories')
    preserved_path = (args.baseline_manifest or directories['before'][0].parent/'manifest.json').resolve(strict=True)
    preserved, expected_baseline = baseline_manifest(preserved_path)
    replacements = sorted([(str(binary),'BINARY'),(str(dest),'OUTPUT'),(str(ROOT),'REPOSITORY')] +
                          [(str(path),cohort.upper()+'_LIBRARIES')
                           for cohort,paths in directories.items() for path in paths],
                          key=lambda pair:len(pair[0]), reverse=True)
    def publish(path,value):
        write(path,public_copy(value,replacements))
    capture=module('native_benchmark_capture',Path(__file__).with_name('benchmark_progress.py')).capture_command
    # Source fingerprints supplement the current commit ID when a candidate is
    # intentionally tested before its commit. Binary hashes remain authoritative.
    source_paths = sorted(path for folder in (ROOT/'gecode/optimize',ROOT/'gecode/int/linear')
                          for path in folder.rglob('*') if path.suffix in ('.cpp','.hpp'))
    provenance=dict(driver_sha256=sha(binary),driver_name=binary.name,
                    source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,timeout=2).strip(),
                    candidate_source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source_paths},
                    driver_source_sha256=sha(Path(__file__).with_name('native_benchmark.cpp')),
                    runner_sha256=sha(Path(__file__)),capture_sha256=sha(Path(__file__).with_name('benchmark_progress.py')),
                    validators={p.name:sha(p) for p in (SUITE/'validate.py',SUITE/'native.py')},
                    preserved_baseline=preserved,cohorts={})
    measurement_files = [Path(__file__),Path(__file__).with_name('native_benchmark.cpp'),
                         Path(__file__).with_name('benchmark_progress.py'),
                         SUITE/'validate.py',SUITE/'native.py']
    measurement_hashes = {str(p.relative_to(ROOT)):sha(p) for p in measurement_files}
    provenance['measurement_source_sha256'] = measurement_hashes
    report=dict(schema_version=1,started_utc=datetime.now(timezone.utc).isoformat(),
                purpose='native_algorithm_changes_from_current_pre_algorithm_baseline',expected_runs=60,
                inputs=inputs,provenance=provenance,records=[])
    local_paths={};loaded_paths={}
    def execute(unit,cohort,label,trace=False):
        remaining=deadline-time.monotonic()
        require(remaining>0,'Whole native panel deadline exhausted')
        command=[str(binary),'--input',str(SUITE/(unit['stem']+'.txt')),'--kind',unit['kind'],
                 '--route',unit['route'],'--seconds',str(SOLVE_SECONDS)]
        environment={k:v for k,v in os.environ.items() if not k.startswith('DYLD_')}
        environment['DYLD_LIBRARY_PATH']=':'.join(map(str,directories[cohort]))
        if trace:environment['DYLD_PRINT_LIBRARIES']='1'
        begin=datetime.now(timezone.utc).isoformat()
        raw=capture(command,dest,environment,min(PROCESS_SECONDS,remaining),max_output=262144)
        stdout,stderr=raw.pop('stdout'),raw.pop('stderr')
        (dest/(label+'.stdout')).write_bytes(stdout);(dest/(label+'.stderr')).write_bytes(stderr)
        # Command provenance remains reproducible without publishing host paths.
        raw.update(command=['BINARY','--input',unit['stem']+'.txt','--kind',unit['kind'],
                            '--route',unit['route'],'--seconds',str(SOLVE_SECONDS)],started_utc=begin,
                   stdout_file=label+'.stdout',stderr_file=label+'.stderr')
        return raw,stdout.decode('utf8',errors='replace'),stderr.decode('utf8',errors='replace')
    for cohort in ('before','after'):
        probe,out,err=execute(panel[0],cohort,'provenance-'+cohort,True)
        require(probe['returncode']==0 and not probe['hard_timeout'] and not probe['output_limit'],'Loader probe failed')
        checked_result(strict_json(out),panel[0],models[panel[0]['id']],validator,native_validator)
        paths=set()
        for line in err.splitlines():
            if 'libgecode' not in line:continue
            require('/' in line,'Malformed loader trace')
            path=Path(line[line.index('/'):].strip()).resolve(strict=True)
            require(path.parent in directories[cohort],'Unexpected mixed runtime library')
            paths.add(path)
        require(any(p.name=='libgecodeoptimize.dylib' for p in paths),'No observed Optimize library load')
        libraries = [dict(name=p.name,sha256=sha(p)) for p in sorted(paths)]
        if cohort=='before':
            require(all(expected_baseline.get(item['name'])==item['sha256'] for item in libraries),
                    'Loaded before library differs from preserved baseline manifest')
        loaded_paths[cohort]=paths
        provenance['cohorts'][cohort]=dict(libraries=libraries,
                                          loader_probe=probe)
        local_paths[cohort]=dict(directories=list(map(str,directories[cohort])),loaded=list(map(str,sorted(paths))))
    facade_hashes = [next(item['sha256'] for item in provenance['cohorts'][cohort]['libraries']
                         if item['name']=='libgecodeoptimize.dylib') for cohort in ('before','after')]
    require(facade_hashes[0]!=facade_hashes[1], 'Candidate facade is byte-identical to the preserved baseline')
    write(dest/'paths.local.json',dict(binary=str(binary),baseline_manifest=str(preserved_path),cohorts=local_paths))
    publish(dest/'report.json',report)
    for rep in range(REPETITIONS):
        for unit in panel:
            for cohort in (('before','after') if rep%2==0 else ('after','before')):
                label=f"{unit['unit']}-r{rep+1}-{cohort}"
                record=dict(unit=unit['unit'],case=unit['id'],kind=unit['kind'],route=unit['route'],cohort=cohort,
                            repetition=rep+1,expected_objective=unit['objective'],completed=False,witness_checked=False)
                try:
                    captured,out,err=execute(unit,cohort,label);record.update(captured)
                    if captured['hard_timeout']:record['status']='external_timeout'
                    elif captured['output_limit']:record['status']='output_limit'
                    elif captured['returncode']!=0:record['status']='process_error'
                    else:record.update(checked_result(strict_json(out),unit,models[unit['id']],validator,native_validator))
                except (ValueError,KeyError,TypeError,OverflowError,OSError,RuntimeError) as error:
                    record.update(status='validation_error',error=str(error))
                report['records'].append(record);publish(dest/'report.json',report)
                print(label,record['status'],record.get('external_seconds'),flush=True)
    unchanged=sha(binary)==provenance['driver_sha256']
    for cohort,paths in loaded_paths.items():
        original={p['name']:p['sha256'] for p in provenance['cohorts'][cohort]['libraries']}
        unchanged &= all(sha(p)==original[p.name] for p in paths)
    inputs_unchanged = all(sha(SUITE/(item['stem']+suffix))==item[key]
                          for item in FROZEN_INPUTS for suffix,key in
                          (('.json','json_sha256'),('.txt','txt_sha256')))
    sources_unchanged = all(sha(ROOT/path)==digest for path,digest in provenance['candidate_source_sha256'].items())
    measurement_unchanged = all(sha(ROOT/path)==digest for path,digest in measurement_hashes.items())
    preserved_unchanged = sha(preserved_path)==preserved['manifest_sha256']
    report.update(runtime_hashes_unchanged=bool(unchanged),finished_utc=datetime.now(timezone.utc).isoformat(),
                  input_hashes_unchanged=inputs_unchanged,candidate_source_hashes_unchanged=sources_unchanged,
                  measurement_source_hashes_unchanged=measurement_unchanged,
                  preserved_manifest_unchanged=preserved_unchanged,
                  elapsed_seconds=time.monotonic()-started)
    integrity_ok = bool(unchanged and inputs_unchanged and sources_unchanged and
                        measurement_unchanged and preserved_unchanged)
    summary=dict(schema_version=1,cohorts={'before':'Pre-algorithm 530a3b783 / compiled c2fabb78f',
                 'after':'Candidate, identical driver and verified runtime libraries'},repetitions=3,
                 required_units=10,required_runs=60,actual_runs=len(report['records']),units=[],
                 elapsed_seconds=report['elapsed_seconds'],provenance=provenance,
                 caveats=['Fixed saved instances; no post-result selection, starts or reference feed.',
                          'Ordinary Native and explicit DFS frontier are separate routes; no HiGHS solve is requested.',
                          'No timing ratio unless every repetition completed and independently matched the optimum.',
                          'Capped incumbents/bounds and failures remain in all denominators.',
                          'Ordinary native node counts are unavailable through the frozen public API.',
                          'External times include process and model construction; internal solve time is also retained.',
                          'Three paired repetitions are a small diagnostic, not a statistical speed guarantee.'])
    for unit in panel:
        item=dict(unit=unit['unit'],case=unit['id'],route=unit['route'],known_optimum=unit['objective'])
        for cohort in ('before','after'):
            records=[r for r in report['records'] if r['unit']==unit['unit'] and r['cohort']==cohort]
            walls=[r['external_seconds'] for r in records if 'external_seconds' in r]
            internal=[r['solve_seconds'] for r in records if 'solve_seconds' in r]
            item[cohort]=dict(attempts=len(records),completed=sum(r['completed'] for r in records),
                             statuses=[r['status'] for r in records],external_seconds=walls,
                             median_external_seconds=statistics.median(walls) if len(walls)==3 else None,
                             median_solve_seconds=statistics.median(internal) if len(internal)==3 else None,
                             objectives=[r.get('objective') for r in records],bounds=[r.get('best_bound') for r in records],
                             nodes=[r.get('nodes') for r in records])
        complete=integrity_ok and all(item[c]['completed']==3 for c in ('before','after'))
        item['median_paired_ratio_after_before']=(statistics.median([b/a for a,b in zip(item['before']['external_seconds'],item['after']['external_seconds'])]) if complete else None)
        summary['units'].append(item)
    publish(dest/'report.json',report);publish(dest/'summary.json',summary)
    failures={'validation_error','process_error','output_limit','external_timeout'}
    ok=(len(report['records'])==60 and integrity_ok and
        time.monotonic()<=deadline and not any(r['status'] in failures for r in report['records']))
    report['comparison_valid']=summary['comparison_valid']=bool(ok)
    report['elapsed_seconds']=summary['elapsed_seconds']=time.monotonic()-started
    publish(dest/'report.json',report);publish(dest/'summary.json',summary)
    print('Complete native panel:',len(report['records']),'records; validation/process gate:',ok)
    return 0 if ok else 1


if __name__=='__main__':
    raise SystemExit(main())
