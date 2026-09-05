#!/usr/bin/env python3
"""Freeze a separate size-shift corpus without reading solver outcomes.

Reuses generator.make_model's exact code object and the existing incumbent and
independent validation procedures. An isolated globals dictionary replaces only
the dimension lookup; the original module and core manifests are never changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from types import FunctionType

import generator
import validate


HERE=Path(__file__).resolve().parent
SEED_BASE=30_000_000
FACTOR=2
CASES_PER_FAMILY=5
MAX_VARIABLES=1000
MAX_ROWS=10000

# Each entry names a dimension call (tiny, small, large) from the original
# template. Other dimension calls keep their large-tier value. Entity counts
# scale mechanically, never in response to a measured solver outcome.
DIMENSIONS={
    'set_cover':{(8,40,100):200,(4,16,30):60},
    'multicover':{(8,40,90):180,(4,16,28):56},
    'set_packing':{(8,40,100):200,(5,20,50):100},
    'knapsack':{(10,40,80):160},
    'multidimensional_knapsack':{(10,40,80):160},
    'vertex_cover':{(9,40,100):200},
    'independent_set':{(9,40,100):200},
    'maxcut':{(4,14,24):48,(5,30,90):180},
    'facility_location':{(3,6,15):30},
    'pmedian':{(3,6,15):30},
    'assignment':{(3,6,12):math.ceil(math.sqrt(FACTOR)*12)},
    'generalized_assignment':{(4,12,28):56},
    'bin_packing':{(4,10,20):40},
    'coloring':{(4,8,20):40},
    'tsp':{(3,5,8):math.ceil(math.sqrt(FACTOR)*8)},
    'auction':{(8,40,120):240,(5,20,35):70},
    'rostering':{(2,4,6):12},
    'production':{(3,4,6):12},
}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()


def make_model(family,seed):
    overrides=DIMENSIONS[family];seen=set()
    def dimension(tier,tiny,small,large):
        if tier!='large':raise ValueError('Scale templates must retain large-tier non-dimensional rules')
        key=(tiny,small,large);seen.add(key)
        return overrides.get(key,large)
    namespace=dict(generator.make_model.__globals__,dimension=dimension)
    isolated=FunctionType(generator.make_model.__code__,namespace,'make_scale_model')
    instance=isolated(family,'large',seed)
    if not set(overrides)<=seen:raise ValueError('Original template dimension calls changed: '+family)
    return instance


def records():
    return [{'id':f'scale_{family}_xlarge_{SEED_BASE+fi*100000+index}',
             'family':family,'kind':'binary','tier':'xlarge','split':'scale',
             'seed':SEED_BASE+fi*100000+index,'ready':False,
             'json':f'scale-instances/scale_{family}_xlarge_{SEED_BASE+fi*100000+index}.json',
             'txt':f'scale-instances/scale_{family}_xlarge_{SEED_BASE+fi*100000+index}.txt'}
            for fi,family in enumerate(generator.FAMILIES) for index in range(CASES_PER_FAMILY)]


def build_instance(record,base_n):
    started=time.perf_counter();instance=make_model(record['family'],record['seed'])
    construction=time.perf_counter()-started
    if instance['n']>MAX_VARIABLES or len(instance['rows'])>MAX_ROWS:
        return None,f'dimensions n={instance["n"]}, rows={len(instance["rows"])} exceed fixed caps'
    if instance['n']<=base_n:raise ValueError('Scale instance does not exceed original large size')
    instance.update({key:record[key] for key in ('id','family','kind','tier','split','seed')})
    instance.update(generator_version=1,label=f'{record["family"]}:xlarge:size-shift',
                    scale_protocol={'factor':FACTOR,'base_tier':'large','base_large_variables':base_n,
                      'actual_variable_ratio':instance['n']/base_n,
                      'dimension_overrides':[{'original_large':key[2],'scaled':value,'call_signature':list(key)}
                                             for key,value in DIMENSIONS[record['family']].items()],
                      'non_dimension_rules':'Original large-tier coefficient, density and feasibility rules unchanged'})
    start_incumbent=time.perf_counter();assignment,method=generator.make_incumbent(instance)
    incumbent=time.perf_counter()-start_incumbent
    validate.check_instance(instance)
    checked=validate.validate_assignment(instance,assignment)
    if not checked['valid'] or not checked['domain_semantics_checked']:
        raise ValueError((record['id'],'independent original-domain incumbent validation failed',checked))
    instance.update(incumbent=assignment,incumbent_objective=checked['objective'],incumbent_method=method)
    instance['reference']={'status':'unknown','input_sha256':validate.input_hash(instance),
                           'reason':'No exact oracle run during pre-evaluation size-shift generation'}
    instance['generation_timing']={'construction_seconds':construction,'incumbent_seconds':incumbent,
                                  'reference_seconds':0,'total_seconds':time.perf_counter()-started}
    return instance,None


def check_text(instance,text):
    """Independent parse of the serialized matrix and common witness."""
    words=iter(text.split());n=int(next(words));count=int(next(words))
    costs=[int(next(words)) for _ in range(n)];rows=[]
    for _ in range(count):
        b=int(next(words));terms=int(next(words))
        rows.append({'a':[[int(next(words)),int(next(words))] for _ in range(terms)],'b':b})
    if (next(words),int(next(words)))!=('incumbent',1):raise ValueError('Missing scale incumbent')
    witness=[int(next(words)) for _ in range(n)]
    if list(words) or (n,costs,rows,witness)!=(instance['n'],instance['c'],instance['rows'],instance['incumbent']):
        raise ValueError('Scale JSON/TXT disagreement')


def generate(directory):
    started=time.perf_counter();directory.mkdir(parents=True,exist_ok=True)
    output=directory/'scale-manifest.json'
    if output.exists():raise ValueError('Refusing to overwrite a frozen scale manifest; choose another --out-dir')
    base_path=HERE/'manifest.json';base=json.loads(base_path.read_text())
    base_n={r['family']:r['n'] for r in base['instances'] if r['tier']=='large'}
    planned=records();seeds={r['seed'] for r in planned}
    if len(seeds)!=len(planned):raise ValueError('Duplicate scale seeds')
    for manifest_path in HERE.glob('*manifest.json'):
        if manifest_path.name=='scale-manifest.json':continue
        other=json.loads(manifest_path.read_text())
        if any(record.get('seed') in seeds for record in other.get('instances',[])):
            raise ValueError('Scale seeds overlap existing corpus: '+str(manifest_path))
    source_hashes={name:sha(HERE/name) for name in ('generator.py','validate.py','generate_scale.py','manifest.json')}
    snapshots={name:sha(HERE/name) for name in ('policy.json','policy.hpp') if (HERE/name).exists()}
    manifest={'schema_version':1,'generation_status':'in_progress','ready':False,'split':'scale','tier':'xlarge',
              'evaluation_track':'Unseen-size generalization on existing binary template families; separate from core held-out/public',
              'planned_utc':now(),'seed_base':SEED_BASE,'cases_per_family':CASES_PER_FAMILY,
              'families':list(generator.FAMILIES),'primary_entity_scale_factor':FACTOR,
              'max_variables':MAX_VARIABLES,'max_rows':MAX_ROWS,'instances':planned,'omitted':[],
              'source_hashes':source_hashes,'unchanged_policy_snapshot':snapshots,
              'selection_rule':'All five fixed seeds per family. Fixed mechanical dimensions; no solver outcomes read, no timing-based resampling.',
              'known_optimum_policy':'All references unknown at generation; feasible incumbents validated independently.',
              'dimension_rules':{family:[{'call_signature':list(key),'scaled':value} for key,value in mapping.items()]
                                 for family,mapping in DIMENSIONS.items()}}
    output.write_text(json.dumps(manifest,indent=2)+'\n')
    (directory/'scale-instances').mkdir(exist_ok=True)
    delivered=[]
    for record in planned:
        instance,reason=build_instance(record,base_n[record['family']])
        if reason:
            manifest['omitted'].append({**record,'reason':reason});continue
        text=generator.to_text(instance);check_text(instance,text)
        (directory/record['json']).write_text(json.dumps(instance,indent=2)+'\n')
        (directory/record['txt']).write_text(text)
        delivered.append({**record,'ready':True,'n':instance['n'],'rows':len(instance['rows']),
                          'input_sha256':validate.input_hash(instance),'incumbent_objective':instance['incumbent_objective'],
                          'reference_status':'unknown','generation_timing':instance['generation_timing'],
                          'json_sha256':sha(directory/record['json']),'txt_sha256':sha(directory/record['txt'])})
    manifest.update(instances=delivered,planned_instances=len(planned),generation_status='complete',ready=True,
                    completed_utc=now(),generation_seconds=time.perf_counter()-started)
    if any(sha(HERE/name)!=value for name,value in source_hashes.items()):
        raise ValueError('Generator/base input changed during generation')
    if any(sha(HERE/name)!=value for name,value in snapshots.items()):
        raise ValueError('Frozen policy changed during generation')
    output.write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,default=HERE)
    args=parser.parse_args();manifest=generate(args.out_dir)
    print(json.dumps({'manifest':str(args.out_dir/'scale-manifest.json'),'instances':len(manifest['instances']),
                      'omitted':len(manifest['omitted']),'seconds':manifest['generation_seconds'],
                      'max_variables':max(r['n'] for r in manifest['instances']),
                      'max_rows':max(r['rows'] for r in manifest['instances'])},sort_keys=True))


if __name__=='__main__':main()
