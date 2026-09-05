#!/usr/bin/env python3
"""Fit a small cost-sensitive policy using development-only algebraic features."""
import argparse
import json
import math
import statistics
from pathlib import Path
import analyze

HERE=Path(__file__).resolve().parent
FEATURES=['variables','rows','rows_per_variable','density','negative_objective_fraction',
          'nonzero_objective_fraction','unit_coefficient_fraction','positive_rows_fraction',
          'negative_rows_fraction','two_term_rows_fraction','max_abs_coefficient','mean_row_terms']
MODES={'stock':'native','disabled':'native','lp':'lp','fix':'fix','fix4':'fix4','fix8':'fix8',
       'rootfix':'rootfix','cuts':'cuts-native','presolve':'presolve','cuts-lp':'cuts-lp',
       'cuts-fix':'cuts-fix','cuts-fix4':'cuts-fix4','lns':'lns-native','lns-fix4':'lns-fix4',
       'pump':'pump','pump-fix4':'pump-fix4','cuts-pump-fix4':'cuts-pump-fix4'}


def algebraic_features(p):
    n=p['n'];rows=p['rows'];m=len(rows);values=[a for row in rows for _,a in row['a']];nnz=len(values)
    return [n,m,m/max(1,n),nnz/max(1,n*m),sum(c<0 for c in p['c'])/max(1,n),
        sum(c!=0 for c in p['c'])/max(1,n),sum(abs(a)==1 for a in values)/max(1,nnz),
        sum(all(a>0 for _,a in row['a']) for row in rows)/max(1,m),
        sum(all(a<0 for _,a in row['a']) for row in rows)/max(1,m),
        sum(len(row['a'])==2 for row in rows)/max(1,m),max(map(abs,values),default=0),nnz/max(1,m)]


def loss(row):
    # Missing a proof is more expensive than a small setup-time difference.
    # Workload labels, exact reference optima and test outcomes are not inputs.
    capped=min(row['elapsed_ms'],row['limit_ms'])
    return (0 if row['completed_within_budget'] else 8)+math.log1p(capped/10)


def fit(samples,configurations,max_depth,min_leaf,complexity_penalty):
    def leaf(indices):
        totals=[sum(samples[i]['costs'][c] for i in indices) for c in range(len(configurations))]
        best=min(range(len(totals)),key=lambda c:(totals[c],c))
        return {'config':configurations[best],'count':len(indices),'training_loss':totals[best]},totals[best]
    def grow(indices,depth):
        terminal,base=leaf(indices)
        if depth==0 or len(indices)<2*min_leaf:return terminal,base
        winner=None;best_total=base-complexity_penalty
        for feature in range(len(FEATURES)):
            values=sorted({samples[i]['features'][feature] for i in indices})
            for a,b in zip(values,values[1:]):
                threshold=(a+b)/2;left=[i for i in indices if samples[i]['features'][feature]<=threshold]
                if min(len(left),len(indices)-len(left))<min_leaf:continue
                right=[i for i in indices if samples[i]['features'][feature]>threshold]
                _,left_loss=leaf(left);_,right_loss=leaf(right);total=left_loss+right_loss
                if total<best_total:best_total=total;winner=(feature,threshold,left,right)
        if winner is None:return terminal,base
        feature,threshold,left,right=winner
        child_left,left_loss=grow(left,depth-1);child_right,right_loss=grow(right,depth-1)
        return {'feature':feature,'feature_name':FEATURES[feature],'threshold':threshold,
                'left':child_left,'right':child_right,'count':len(indices)},left_loss+right_loss
    return grow(list(range(len(samples))),max_depth)[0]


def predict(tree,features):
    while 'config' not in tree:tree=tree['left'] if features[tree['feature']]<=tree['threshold'] else tree['right']
    return tree['config']


def checked_features(problem, row):
    """Verify the complete online feature vector, including finite values."""
    expected=algebraic_features(problem);actual=row.get('features')
    if not isinstance(actual,list) or len(actual)!=len(FEATURES):
        raise ValueError('Expected exactly 12 online features')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in actual):
        raise ValueError('Online features must be finite numbers')
    if any(abs(x-y)>1e-5*max(1,abs(x)) for x,y in zip(expected,actual)):
        raise ValueError('C++/Python feature mismatch')
    return expected


def check_folds(records):
    """This protocol holds out one of exactly three seeds per family/tier."""
    groups={}
    for record in records.values():
        seed=record.get('seed')
        if isinstance(seed,bool) or not isinstance(seed,int) or seed%10 not in (0,1,2):
            raise ValueError('Development seeds must have fold residue 0, 1, or 2')
        group=groups.setdefault((record['family'],record.get('tier')),[])
        group.append(seed%10)
    if not groups or any(sorted(folds)!=[0,1,2] for folds in groups.values()):
        raise ValueError('Expected exactly three development seeds, one per fold, for each family/tier')
    seeds=[record['seed'] for record in records.values()]
    if len(seeds)!=len(set(seeds)):
        raise ValueError('Duplicate development seeds')


def load_training_data(paths, manifest_path, configs):
    """Audit immutable inputs and deadline results before constructing labels.

    Source batches may use different executable builds and action sets during
    development. Other measurement settings must agree. Identical observations
    are deduplicated; fresh observations of an unchanged action contribute only
    to its per-instance median, never another training sample.
    """
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('generation_status')=='in_progress' or manifest.get('ready') is False:
        raise ValueError('Development manifest is incomplete')
    raw_records=[r for r in manifest['instances'] if r['split']=='dev' and r.get('kind','binary')=='binary']
    records={r['id']:r for r in raw_records}
    if len(records)!=len(raw_records):raise ValueError('Duplicate development instance IDs')
    check_folds(records)
    problems={};input_hashes={}
    for identity,record in records.items():
        path=manifest_path.parent/record['json'];problems[identity]=json.loads(path.read_text())
        input_hashes[identity]=analyze.sha(path)
    sources={};metadata_hashes={};protocols=[];compatible=None;action_specs={}
    # Keep every metadata file subject to audit even when run content is copied.
    unique_paths=list(dict.fromkeys(Path(path).resolve() for path in paths))
    for path in unique_paths:
        meta_path=path.with_suffix('.meta.json');meta=json.loads(meta_path.read_text());protocol=meta['protocol']
        if set(protocol['split'].split(','))!={'dev'}:
            raise ValueError('Refusing non-development or mixed-split training batches')
        if not meta.get('completed'):raise ValueError('Training needs complete development batches')
        fingerprint={key:protocol.get(key) for key in ('limit_ms','warm','platform','machine','threads_per_search',
                    'parallel_solver_runs','highs_mip_used','timing')}
        if compatible is None:compatible=fingerprint
        elif compatible!=fingerprint:raise ValueError('Do not mix training budgets, warm starts, platforms or timing policies')
        for config in configs:
            if config not in protocol['configs']:continue
            specification=protocol['configs'][config]
            specified_mode=specification.get('mode') if isinstance(specification,dict) else specification[1]
            if specified_mode!=MODES[config]:raise ValueError('Unsupported action-mode definition: '+config)
            if config in action_specs and specification!=action_specs[config]:
                raise ValueError('Action definition changed between development batches: '+config)
            action_specs[config]=specification
        for identity,hashes in protocol['inputs'].items():
            if identity in records and hashes['json']!=input_hashes[identity]:
                raise ValueError('Current development input differs from measured input: '+identity)
        sources[str(path)]=analyze.sha(path);metadata_hashes[str(meta_path)]=analyze.sha(meta_path)
        protocols.append({'file':str(path),'sha256':analyze.digest(protocol),'protocol':protocol})
    if not unique_paths:raise ValueError('No development run files')
    # Full audits include complete expected coverage, original-domain witnesses,
    # JSON/TXT agreement, reference hashes, binary hashes, and deadline traces.
    cohorts=[]
    for path in unique_paths:
        audited,_=analyze.load_runs([path],{'dev'},[manifest_path],{},False)
        cohorts.extend(audited.values())
    groups={};observations=set();duplicate_observations=0
    for cohort in cohorts:
        for row in cohort['rows'].values():
            if row['split']!='dev':raise ValueError('Refusing non-development training rows')
            if row['kind']!='binary' or row['config'] not in configs:continue
            identity=row['id']
            if identity not in records:raise ValueError('Training instance not in development manifest')
            record=records[identity]
            if (row.get('seed'),row['family'],row.get('tier'))!=(record['seed'],record['family'],record.get('tier')):
                raise ValueError('Training seed/family/tier differs from development manifest')
            specification=action_specs[row['config']]
            branching=specification.get('branching') if isinstance(specification,dict) else specification[2]
            if row.get('requested_mode',row.get('mode'))!=MODES[row['config']] or row.get('branching')!=branching:
                raise ValueError('Measured mode/branching differs from policy action: '+row['config'])
            checked_features(problems[identity],row)
            raw={key:value for key,value in row.items() if not key.startswith('_')}
            observation=analyze.digest(raw)
            if observation in observations:
                duplicate_observations+=1;continue
            observations.add(observation)
            groups.setdefault(identity,{}).setdefault(row['config'],[]).append(row)
    samples=[];observation_counts={}
    for identity,record in sorted(records.items()):
        if identity not in groups or set(groups[identity])!=set(configs):
            raise ValueError('Incomplete action matrix for '+identity)
        observations_for_instance=[row for values in groups[identity].values() for row in values]
        proved={row['objective'] for row in observations_for_instance if row['status']=='optimal'}
        feasible=[row['objective'] for row in observations_for_instance if row['objective'] is not None]
        if len(proved)>1 or (proved and feasible and min(feasible)<next(iter(proved))):
            raise ValueError('Development batches disagree on optimum: '+identity)
        observation_counts[identity]={config:len(groups[identity][config]) for config in configs}
        samples.append({'id':identity,'seed':record['seed'],'features':algebraic_features(problems[identity]),
          'costs':[statistics.median(loss(row) for row in groups[identity][config]) for config in configs]})
    provenance={'run_hashes':sources,'metadata_hashes':metadata_hashes,'input_hashes':input_hashes,
                'source_protocols':protocols,'compatible_measurement_settings':compatible,
                'action_observation_counts':observation_counts,'duplicate_observations_dropped':duplicate_observations,
                'weighting':'One training sample per instance; median loss per action across distinct observations. Builds/action sets may differ between development batches; final evaluation uses one frozen build.',
                'manifest_sha256':analyze.sha(manifest_path)}
    return samples,provenance


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',type=Path,nargs='+',required=True)
    p.add_argument('--configs',default='stock,fix4,lns-fix4,cuts-fix4,pump-fix4')
    p.add_argument('--manifest',type=Path,default=HERE/'manifest.json')
    p.add_argument('--out',type=Path,default=HERE/'policy.json')
    p.add_argument('--header',type=Path,default=HERE/'policy.hpp')
    p.add_argument('--min-leaf',type=int,default=8)
    p.add_argument('--max-depth',type=int,default=3)
    p.add_argument('--complexity-penalty',type=float,default=.5)
    a=p.parse_args();configs=a.configs.split(',')
    if not configs or len(set(configs))!=len(configs) or any(c not in MODES for c in configs):raise ValueError('Unsupported/duplicate action')
    if a.min_leaf<1 or a.max_depth<0 or not math.isfinite(a.complexity_penalty) or a.complexity_penalty<0:
        raise ValueError('Expected positive min-leaf, nonnegative max-depth and finite nonnegative complexity penalty')
    samples,provenance=load_training_data(a.runs,a.manifest,configs)
    # Each family/tier uses seed offsets0/1/2; hold out one replication together.
    cv=[]
    for depth in range(a.max_depth+1):
        errors=[]
        for fold in range(3):
            train=[s for s in samples if s['seed']%10!=fold];test=[s for s in samples if s['seed']%10==fold]
            if not train or not test:raise ValueError('Expected three development seed replications')
            tree=fit(train,configs,depth,a.min_leaf,a.complexity_penalty)
            errors.extend(s['costs'][configs.index(predict(tree,s['features']))] for s in test)
        cv.append({'depth':depth,'held_out_development_loss':statistics.mean(errors)})
    best=min(cv,key=lambda row:(row['held_out_development_loss'],row['depth']))['depth']
    tree=fit(samples,configs,best,a.min_leaf,a.complexity_penalty)
    selected={s['id']:predict(tree,s['features']) for s in samples}
    result={'schema_version':1,'purpose':'Development-only structural feature selector; never trained on test/public outcomes',
      'training_rows':len(samples),'configs':configs,'features':FEATURES,'tree':tree,'selected_depth':best,
      'cross_validation':cv,'min_leaf':a.min_leaf,'complexity_penalty':a.complexity_penalty,
      'loss':'8 * incomplete_within_budget + log1p(min(elapsed_ms,cutoff_ms)/10)',
      **provenance,'training_selection':selected,'held_out_test_used':False,
      'limitations':[
        'Cross-validation chooses depth; its best loss is tuning evidence, not an unbiased final performance estimate.',
        'Seed folds test new seeds from the same generator families and fixed size tiers, not unseen families or sizes.',
        'Algebraic features may identify encoding templates even without explicit family labels.',
        'The policy applies to binary-linear models. Native CP uses its separately defined unchanged dispatch.',
        'Shared supplied incumbents make the primary warm-start experiment a proof/improvement benchmark.',
        'Comparison is to the same matrix encoding and search on stock Gecode, not every bespoke CP formulation or specialized algorithm.']}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    def cpp(node,indent='  '):
        if 'config' in node:return indent+'return "'+MODES[node['config']]+'";\n'
        return (indent+f'if(f[{node["feature"]}] <= {node["threshold"]:.17g}) {{\n'+cpp(node['left'],indent+'  ')+indent+'} else {\n'+cpp(node['right'],indent+'  ')+indent+'}\n')
    payload='// Generated from development data only. See policy.json.\n#ifndef SOLVER_BENCH_POLICY_HPP\n#define SOLVER_BENCH_POLICY_HPP\n#include <vector>\ninline const char* select_policy(const std::vector<double>& f) {\n'+cpp(tree)+'}\n#endif\n'
    a.header.write_text(payload)
    print(json.dumps({'samples':len(samples),'selected_depth':best,'cross_validation':cv,'action_counts':{c:list(selected.values()).count(c) for c in configs}},indent=2))


if __name__=='__main__':main()
