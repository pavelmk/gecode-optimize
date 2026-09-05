#!/usr/bin/env python3
"""Serial paired benchmarking with resume, validation and immutable provenance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import time
from pathlib import Path
import native
import validate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CONFIGS={
 'native-lns':('enhanced-binary','native','afc','enhanced-native'),
 'native-incumbent':('enhanced-binary','native','afc','enhanced-native'),
 'native-lns-degree':('enhanced-binary','native','degree','enhanced-native'),
 'native-lns-size':('enhanced-binary','native','size','enhanced-native'),
 'stock':('stock-binary','native','afc','stock-native'),
 'disabled':('enhanced-binary','native','afc','enhanced-native'),
 'lp':('enhanced-binary','lp','afc','enhanced-native'),
 'fix':('enhanced-binary','fix','afc','enhanced-native'),
 'fix4':('enhanced-binary','fix4','afc','enhanced-native'),
 'fix8':('enhanced-binary','fix8','afc','enhanced-native'),
 'rootfix':('enhanced-binary','rootfix','afc','enhanced-native'),
 'cuts':('enhanced-binary','cuts-native','afc','enhanced-native'),
 'presolve':('enhanced-binary','presolve','afc','enhanced-native'),
 'cuts-lp':('enhanced-binary','cuts-lp','afc','enhanced-native'),
 'cuts-fix':('enhanced-binary','cuts-fix','afc','enhanced-native'),
 'cuts-fix4':('enhanced-binary','cuts-fix4','afc','enhanced-native'),
 'lns':('enhanced-binary','lns-native','afc','enhanced-native'),
 'lns-fix4':('enhanced-binary','lns-fix4','afc','enhanced-native'),
 'pump':('enhanced-binary','pump','afc','enhanced-native'),
 'pump-fix4':('enhanced-binary','pump-fix4','afc','enhanced-native'),
 'cuts-pump-fix4':('enhanced-binary','cuts-pump-fix4','afc','enhanced-native'),
 'portfolio':('enhanced-binary','auto','afc','enhanced-native'),
 'stock-size':('stock-binary','native','size','stock-native'),
 'stock-degree':('stock-binary','native','degree','stock-native'),
 'fix4-size':('enhanced-binary','fix4','size','enhanced-native'),
}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()


def load_records(paths):
    records=[]
    for path in paths:
        manifest=json.loads(path.read_text())
        if manifest.get('generation_status')=='in_progress' or manifest.get('ready') is False:
            raise ValueError(f'Manifest not ready: {path}')
        for record in manifest['instances']:
            row=dict(record);row.setdefault('kind','native' if path.name.startswith('native') else 'binary')
            row['_directory']=path.parent;records.append(row)
    if len({r['id'] for r in records})!=len(records):raise ValueError('Duplicate instance IDs')
    return records


def binary_txt_matches(instance,path):
    tokens=iter(path.read_text().split());n=int(next(tokens));m=int(next(tokens))
    costs=[int(next(tokens)) for _ in range(n)];rows=[]
    for _ in range(m):
        b=int(next(tokens));count=int(next(tokens));a=[[int(next(tokens)),int(next(tokens))] for _ in range(count)];rows.append({'a':a,'b':b})
    if next(tokens)!='incumbent':raise ValueError('Missing incumbent')
    witness=[int(next(tokens)) for _ in range(n)] if int(next(tokens)) else []
    if list(tokens):raise ValueError('Trailing input')
    if (n,costs,rows,witness)!=(instance['n'],instance['c'],instance['rows'],instance.get('incumbent') or []):raise ValueError('JSON/TXT mismatch')


def native_txt_matches(instance,path):
    if instance['family']=='native_rcpsp':
        from native_rcpsp import encode
        if encode(instance).split()!=path.read_text().split():raise ValueError('RCPSP JSON/TXT mismatch')
        return
    tokens=iter(path.read_text().split());family=next(tokens);size=int(next(tokens));machines=int(next(tokens));rows=int(next(tokens))
    flat=[v for row in instance['data'] for v in row]
    actual=[int(next(tokens)) for _ in flat];witness=[int(next(tokens)) for _ in range(instance['n'])]
    if list(tokens) or (family,size,machines,rows,actual,witness)!=(instance['family'],instance['size'],instance.get('machines',0),len(instance['data']),flat,instance['incumbent']):raise ValueError('Native JSON/TXT mismatch')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bin',type=Path,default=ROOT/'build/solver-bench/bin')
    p.add_argument('--manifest',type=Path,action='append')
    p.add_argument('--split',default='dev');p.add_argument('--kinds',default='binary,native')
    p.add_argument('--families',default='');p.add_argument('--tiers',default='')
    p.add_argument('--ids',default='');p.add_argument('--configs',default='stock,lp,portfolio')
    p.add_argument('--repeats',type=int,default=3);p.add_argument('--limit-ms',type=float,default=2000)
    p.add_argument('--warm',type=int,choices=[0,1],default=1)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true')
    p.add_argument('--wall-budget',type=float,default=0,help='Stop between runs after this many seconds; resume later')
    a=p.parse_args();paths=a.manifest or [HERE/name for name in ['manifest.json','native-manifest.json','rcpsp-manifest.json','public-manifest.json','public-binary-manifest.json','miplib-manifest.json'] if (HERE/name).exists()];configs=a.configs.split(',')
    if any(c not in CONFIGS for c in configs) or len(set(configs))!=len(configs):p.error('Unknown/duplicate configuration')
    if a.repeats<1 or not math.isfinite(a.limit_ms) or a.limit_ms<=0 or a.limit_ms>86400000:p.error('Positive repeats and finite cutoff <=86400000ms required')
    if not math.isfinite(a.wall_budget) or a.wall_budget<0:p.error('Finite nonnegative wall budget required')
    records=[r for r in load_records(paths) if r['split'] in a.split.split(',') and r['kind'] in a.kinds.split(',')]
    for field,arg in [('family',a.families),('tier',a.tiers),('id',a.ids)]:
        if arg:records=[r for r in records if r.get(field) in arg.split(',')]
    if not records:p.error('No matching instances')
    if any(c.startswith('native-') for c in configs) and any(r['kind']!='native' for r in records):p.error('Native controller configurations require --kinds native')
    inputs={};input_hashes={}
    for r in records:
        directory=r['_directory'];instance=json.loads((directory/r['json']).read_text());inputs[r['id']]=instance
        if r['kind']=='native':
            native_txt_matches(instance,directory/r['txt']);check=native.validate_assignment(instance,instance['incumbent'])
        else:
            binary_txt_matches(instance,directory/r['txt']);check=validate.validate_assignment(instance,instance.get('incumbent')) if instance.get('incumbent') else {'valid':True}
        if not check['valid']:raise ValueError((r['id'],'bad input witness',check))
        input_hashes[r['id']]={'json':sha(directory/r['json']),'txt':sha(directory/r['txt'])}
    binaries=set()
    for r in records:
        for c in configs:binaries.add(CONFIGS[c][3] if r['kind']=='native' else CONFIGS[c][0])
    protocol={'schema_version':1,'runner_sha256':sha(Path(__file__)),
      'validator_hashes':{name:sha(HERE/name) for name in ('validate.py','native.py','native_rcpsp.py')},'manifests':{str(path.resolve()):sha(path) for path in paths},
      'inputs':input_hashes,'configs':{c:CONFIGS[c] for c in configs},'repeats':a.repeats,'limit_ms':a.limit_ms,'warm':a.warm,
      'binaries':{b:sha(a.bin/b) for b in sorted(binaries)},'order_seed':614918,'split':a.split,
      'platform':platform.platform(),'machine':platform.machine(),'cpu_count':os.cpu_count(),
      'timing':'Solver setup, feature selection, presolve/cuts, optional LNS, LP construction, search and teardown are timed. Input parsing, validation, offline shared incumbent generation, process startup and output serialization are excluded. Process wall time is recorded separately.',
      'parallel_solver_runs':False,'threads_per_search':1,'highs_mip_used':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);meta_path=a.output.with_suffix('.meta.json')
    done=set();proofs={};best_seen={};existing=[]
    if a.output.exists():
        if not a.resume:p.error('Output exists; use --resume or a new path')
        previous=json.loads(meta_path.read_text())
        if previous['protocol']!=json.loads(json.dumps(protocol)):raise ValueError('Cannot resume after protocol, input, platform or binary change')
        for line in a.output.read_text().splitlines():
            r=json.loads(line);key=(r['id'],r['config'],r['repetition'])
            if key in done:raise ValueError('Duplicate stored run')
            done.add(key);existing.append(r)
            if r.get('objective') is not None:best_seen[r['id']]=min(best_seen.get(r['id'],r['objective']),r['objective'])
            if r.get('status')=='optimal':
                if r['id'] in proofs and proofs[r['id']]!=r['objective']:raise ValueError('Conflicting stored optima')
                proofs[r['id']]=r['objective']
    meta={'protocol':protocol,'started_utc':utc(),'completed':False,'expected_runs':len(records)*len(configs)*a.repeats,'previous_runs':len(done)}
    meta_path.write_text(json.dumps(meta,indent=2)+'\n');rng=random.Random(protocol['order_seed']);started=time.monotonic();last_progress=started
    with a.output.open('a') as out:
        for rep in range(a.repeats):
            shuffled=list(records);rng.shuffle(shuffled)
            for record in shuffled:
                order=list(configs);rng.shuffle(order)
                for config in order:
                    key=(record['id'],config,rep)
                    if key in done:continue
                    if a.wall_budget and time.monotonic()-started>=a.wall_budget:
                        meta.update(stopped_utc=utc(),completed_runs=len(done),stop_reason='session wall budget');meta_path.write_text(json.dumps(meta,indent=2)+'\n');print(f'Paused after {len(done)} runs; resume supported',flush=True);return
                    binary,mode,branching,native_binary=CONFIGS[config]
                    if record['kind']=='native':
                        binary=native_binary
                        mode='lns' if config.startswith('native-lns') else 'incumbent' if config=='native-incumbent' else 'native'
                    command=[str((a.bin/binary).resolve()),str((record['_directory']/record['txt']).resolve()),mode,branching,str(a.limit_ms),str(a.warm),'1']
                    start=time.perf_counter();result=subprocess.run(command,capture_output=True,text=True,timeout=a.limit_ms/1000+30)
                    wall_ms=(time.perf_counter()-start)*1000
                    if result.returncode!=0:raise RuntimeError((record['id'],config,result.returncode,result.stderr))
                    row=json.loads(result.stdout);instance=inputs[record['id']]
                    checked=(native.validate_result if record['kind']=='native' else validate.validate_result)(instance,row)
                    row.update(id=record['id'],family=record['family'],tier=record.get('tier'),kind=record['kind'],split=record['split'],seed=record.get('seed'),config=config,repetition=rep,
                      process_wall_ms=wall_ms,validation=checked,initial_objective=instance.get('incumbent_objective') if a.warm else None,
                      reference_status=instance.get('reference',{}).get('status'),reference_objective=instance.get('reference',{}).get('objective'),limit_ms=a.limit_ms,warm=bool(a.warm),binary_sha256=protocol['binaries'][binary])
                    at_limit=instance.get('incumbent_objective') if a.warm else None;time_best=0 if at_limit is not None else None
                    for timestamp,value in row.get('improvements',[]):
                        if timestamp<=a.limit_ms and (at_limit is None or value<at_limit):at_limit=value;time_best=timestamp
                    row.update(completed_within_budget=row['status'] in ('optimal','infeasible') and row['elapsed_ms']<=a.limit_ms,
                               deadline_overrun_ms=max(0,row['elapsed_ms']-a.limit_ms),objective_at_limit=at_limit,time_to_best_within_limit_ms=time_best)
                    if not checked['valid']:
                        a.output.with_suffix('.failure.json').write_text(json.dumps(row,indent=2)+'\n');raise RuntimeError((record['id'],config,'validation failed',checked))
                    if row['status']=='optimal':
                        if row['id'] in proofs and proofs[row['id']]!=row['objective']:
                            a.output.with_suffix('.failure.json').write_text(json.dumps(row,indent=2)+'\n');raise RuntimeError('Solvers disagree on proved optimum: '+row['id'])
                        proofs[row['id']]=row['objective']
                    if row['objective'] is not None:best_seen[row['id']]=min(best_seen.get(row['id'],row['objective']),row['objective'])
                    if row['id'] in proofs and best_seen.get(row['id'],proofs[row['id']])<proofs[row['id']]:raise RuntimeError('Earlier feasible witness improves a claimed optimum')
                    if row['objective'] is not None and row['id'] in proofs and row['objective']<proofs[row['id']]:raise RuntimeError('Feasible witness improves an already claimed optimum')
                    out.write(json.dumps(row,separators=(',',':'))+'\n');out.flush();done.add(key)
                    if time.monotonic()-last_progress>30:
                        print(f'{len(done)}/{meta["expected_runs"]} validated runs; latest {record["family"]}/{config}: {row["status"]}',flush=True);last_progress=time.monotonic()
            print(f'Repetition {rep+1}/{a.repeats}: {len(done)} total validated runs',flush=True)
    meta.update(completed=True,completed_runs=len(done),finished_utc=utc(),session_wall_seconds=time.monotonic()-started);meta_path.write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps({'completed_runs':len(done),'instances':len(records),'configs':configs}),flush=True)


if __name__=='__main__':main()
