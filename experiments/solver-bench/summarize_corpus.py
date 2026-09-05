#!/usr/bin/env python3
"""Export corpus coverage and immutable input identities without reading results."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

import analyze
import native
import validate

HERE=Path(__file__).resolve().parent
MANIFESTS=('manifest.json','native-manifest.json','rcpsp-manifest.json','scale-manifest.json',
           'paired-manifest.json','public-manifest.json','public-binary-manifest.json','miplib-manifest.json','fzn-manifest.json')
CORE={'manifest.json','native-manifest.json','rcpsp-manifest.json'}
CONCEPT_ALIASES={'native_tsp':'tsp','native_coloring':'coloring','native_rcpsp':'rcpsp'}
SCHEMAS={
 'binary-linear-v1':{'meaning':'minimize c*x with sparse integer a*x>=b and binary x',
   'mathematical_keys':['n','c','rows'],'n':'positive integer','c':'n integer costs',
   'rows':'array of {a: sorted unique [column,nonzero integer] pairs, b: integer}',
   'optional_incumbent':'n binary integers; objective recomputed','mathematical_hash':'SHA256 of sorted compact JSON mathematical keys'},
 'native-cp-v1':{'meaning':'family-specific integer CP model with independent assignment validator',
   'mathematical_keys':['family','size','machines','n','data'],'data':'family-specific integer matrix',
   'incumbent':'n integer values; family objective recomputed',
   'mathematical_hash':'SHA256 of sorted compact JSON mathematical keys; missing keys are null'},
 'native-rcpsp-v1':{'meaning':'nonpreemptive project scheduling with precedence and renewable cumulative resources',
   'mathematical_keys':['family','size','machines','n','data'],
   'data':'{capacities: positive integers, tasks: [duration,resource demands], precedences: directed pairs}',
   'incumbent':'n nonnegative integer start times; makespan recomputed',
   'mathematical_hash':'SHA256 of sorted compact JSON mathematical keys; missing keys are null'},
 'flatzinc-upstream-regression-v1':{'meaning':'unchanged upstream FlatZinc model and expected textual output',
   'required_files':['fzn','expected','license_notice'],'solve':'satisfy, minimize, or maximize',
   'identity':'SHA256 of exact model bytes; expected-output hash is separate',
   'optimality_limit':'expected output is a regression oracle, not an independent mathematical optimum certificate'},
}


def source_of(name,record,instance):
    provenance=instance.get('provenance',{})
    if name in CORE:return 'generated/'+('binary templates' if name=='manifest.json' else 'native CP templates')
    if name=='scale-manifest.json':return 'generated/unseen size'
    if name=='paired-manifest.json':return 'generated/paired semantic formulations'
    if name=='public-manifest.json':return 'OR-Library/Gecode bundled job shops'
    if name=='public-binary-manifest.json':return 'OR-Library/'+provenance.get('collection','binary collection')
    if name=='miplib-manifest.json':return 'MIPLIB3.0 classics'
    if name=='fzn-manifest.json':return 'Gecode 6.4.0 FlatZinc regression suite'
    return name


def track_of(name,record):
    if name=='fzn-manifest.json':return 'flatzinc_'+record['track']
    if name=='scale-manifest.json':return 'scale_unseen_size'
    if name=='paired-manifest.json':return 'paired_formulation'
    if name in CORE:return {'dev':'generated_development','test':'generated_held_out','tiny':'tiny_correctness'}[record['split']]
    return 'public_optimization'


def summarize(records,group_fields):
    groups=defaultdict(list)
    for record in records:groups[tuple(record.get(key) for key in group_fields)].append(record)
    output=[]
    for values,items in sorted(groups.items(),key=lambda pair:str(pair[0])):
        result=dict(zip(group_fields,values));result.update(instances=len(items),
          known_optimum_references=sum(r['optimum_reference_status']=='known' for r in items),
          unknown_optimum_references=sum(r['optimum_reference_status']=='unknown' for r in items),
          optimum_not_applicable=sum(r['optimum_reference_status']=='not_applicable' for r in items),
          upstream_output_regression_references=sum(r['reference_kind']=='upstream expected output' for r in items),
          supplied_incumbents=sum(r['supplied_incumbent'] for r in items))
        for key in ('n','binary_rows','native_size','native_machines','fzn_bytes'):
            numeric=[r[key] for r in items if r.get(key) is not None]
            result[key+'_min']=min(numeric) if numeric else None
            result[key+'_max']=max(numeric) if numeric else None
        output.append(result)
    return output


def export(directory):
    records=[];manifests=[];skipped=[];core_representations=set()
    for name in MANIFESTS:
        path=HERE/name
        if not path.exists():continue
        manifest=json.loads(path.read_text())
        if manifest.get('generation_status')=='in_progress' or manifest.get('ready') is False:
            raise ValueError('Incomplete manifest: '+name)
        manifests.append({'file':name,'sha256':analyze.sha(path),'instances':len(manifest['instances']),
                          'schema_version':manifest.get('schema_version')})
        skipped.extend({'manifest':name,**entry} for entry in manifest.get('skipped_sources',[]))
        skipped.extend({'manifest':name,**entry} for entry in manifest.get('omitted',[]))
        for record in manifest['instances']:
            kind=record.get('kind','native' if name.startswith('native') else 'binary')
            if name in CORE:core_representations.add(record['family'])
            if kind=='flatzinc':
                instance=record;model_path=HERE/record['fzn'];expected_path=HERE/record['expected']
                mathematical_hash=analyze.sha(model_path)
                if mathematical_hash!=record['fzn_sha256'] or analyze.sha(expected_path)!=record['expected_sha256']:
                    raise ValueError('Changed FlatZinc model/expected output: '+record['id'])
                schema='flatzinc-upstream-regression-v1';reference_kind='upstream expected output'
                optimum_status='not_applicable' if record['solve']=='satisfy' else 'unknown'
                hashes={'fzn_sha256':mathematical_hash,'expected_sha256':analyze.sha(expected_path),
                        'license_notice_sha256':analyze.sha(HERE/record['license_notice'])}
                dimensions={'n':None,'binary_rows':None,'native_size':None,'native_machines':None,'fzn_bytes':model_path.stat().st_size}
                has_incumbent=False
            else:
                instance_path=HERE/record['json'];txt_path=HERE/record['txt'];instance=json.loads(instance_path.read_text())
                if (instance['id'],instance['family'],instance['split'])!=(record['id'],record['family'],record['split']):
                    raise ValueError('Manifest/instance identity disagreement: '+record['id'])
                mathematical_hash=analyze.mathematical_hash(instance,kind)
                for recorded in (record.get('input_sha256'),instance.get('reference',{}).get('input_sha256')):
                    if recorded and recorded!=mathematical_hash:raise ValueError('Stale mathematical/reference hash: '+record['id'])
                analyze.txt_matches(instance,txt_path,kind)
                if name=='paired-manifest.json':
                    semantic=json.loads((HERE/record['semantic_json']).read_text());semantic_hash=analyze.digest(semantic)
                    if semantic_hash!=record['semantic_input_sha256'] or semantic_hash!=instance['semantic_input_sha256']:
                        raise ValueError('Paired semantic hash differs: '+record['id'])
                    if semantic['problem']=='tsp':
                        actual=instance['parameters']['distances'] if kind=='binary' else instance['data']
                        if actual!=semantic['distances']:raise ValueError('Paired distances differ')
                    else:
                        vertices=instance['parameters']['vertices'] if kind=='binary' else instance['n']
                        edges=instance['parameters']['edges'] if kind=='binary' else instance['data']
                        if (vertices,edges)!=(semantic['vertices'],semantic['edges']):raise ValueError('Paired graph differs')
                if kind=='binary':validate.check_instance(instance)
                has_incumbent=bool(instance.get('incumbent'))
                if has_incumbent:
                    checked=analyze.assignment_check(instance,instance['incumbent'],kind)
                    if not checked['valid'] or checked['objective']!=instance.get('incumbent_objective'):
                        raise ValueError('Invalid supplied incumbent: '+record['id'])
                reference=instance.get('reference',{})
                optimum_status='known' if reference.get('status')=='optimal' else 'unknown'
                if optimum_status=='known' and not validate.integer(reference.get('objective')):
                    raise ValueError('Known reference lacks integer optimum: '+record['id'])
                reference_kind=('published optimum' if 'source_url' in reference else 'independent exact oracle') if optimum_status=='known' else 'no exact reference'
                schema='binary-linear-v1' if kind=='binary' else 'native-rcpsp-v1' if instance['family']=='native_rcpsp' else 'native-cp-v1'
                hashes={'json_sha256':analyze.sha(instance_path),'txt_sha256':analyze.sha(txt_path)}
                dimensions={'n':instance['n'],'binary_rows':len(instance['rows']) if kind=='binary' else None,
                            'native_size':instance.get('size') if kind=='native' else None,
                            'native_machines':instance.get('machines') if kind=='native' else None,'fzn_bytes':None}
            records.append({'id':record['id'],'manifest':name,'track':track_of(name,record),
              'split':record['split'],'kind':kind,'family':record['family'],'tier':record.get('tier'),
              'source':source_of(name,record,instance),'core_normalized_concept':CONCEPT_ALIASES.get(record['family'],record['family']) if record['family'] in core_representations else None,
              'seed':record.get('seed'),'schema_id':schema,'schema_contract_sha256':analyze.digest(SCHEMAS[schema]),
              'paired_problem_id':record.get('paired_problem_id'),'semantic_input_sha256':record.get('semantic_input_sha256'),
              'mathematical_input_sha256':mathematical_hash,**hashes,**dimensions,
              'optimum_reference_status':optimum_status,'reference_kind':reference_kind,'supplied_incumbent':has_incumbent,
              'source_url':instance.get('provenance',{}).get('source_url') if isinstance(instance.get('provenance'),dict) else record.get('source_url')})
    if len({r['id'] for r in records})!=len(records):raise ValueError('Duplicate corpus IDs')
    concepts=sorted({CONCEPT_ALIASES.get(family,family) for family in core_representations})
    counts={'catalogued_artifacts':len(records),'by_track':dict(Counter(r['track'] for r in records)),
            'by_split':dict(Counter(r['split'] for r in records)),'by_kind':dict(Counter(r['kind'] for r in records)),
            'core_generated_representations':len(core_representations),'core_normalized_domain_model_concepts':len(concepts)}
    counts['paired_semantic_problems']=len({r['paired_problem_id'] for r in records if r['paired_problem_id']})
    payload={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),'counts':counts,
             'core_representations':sorted(core_representations),'core_normalized_concepts':concepts,
             'concept_aliases':CONCEPT_ALIASES,'manifests':manifests,
             'schema_contracts':{key:{'sha256':analyze.digest(value),'definition':value} for key,value in SCHEMAS.items()},
             'validator_source_hashes':{name:analyze.sha(HERE/name) for name in ('validate.py','native.py','native_rcpsp.py','analyze.py')},
             'summary_by_track':summarize(records,['track']),
             'summary_by_split_kind_family_source':summarize(records,['split','kind','family','source']),
             'family_size_summary':summarize(records,['track','kind','family','tier']),
             'summary_by_source':summarize(records,['source']),
             'instances':records,'explicit_omissions_or_skips':skipped,
             'notes':[
               'This is a corpus inventory, not evidence that every instance has been benchmarked or solved.',
               'Core23 representations normalize to21 domain/model concepts by merging alternate TSP/coloring encodings; these are not21 unrelated mathematical classes. Set packing/auction overlap, and vertex cover/independent set are closely related.',
               'Public source collections and FlatZinc regression groups are reported separately and do not inflate the core generated concept count.',
               'MIPLIB3.0 binary is a source collection label, not an additional mathematical problem concept or MIPLIB2017 benchmark-set coverage.',
               'Scale90 uses larger sizes from existing binary templates; it is separate from the frozen core held-out230.',
               'The paired formulation track contains40 encodings of20 shared semantic problems; do not count the two encodings as independent instances.',
               'Known optimum means an embedded independent oracle or published reference, not a newly checked formal proof log. Upstream FlatZinc text is a regression oracle and never counted as independent optimum verification.',
               'Schema contract hashes identify the documented mathematical encoding contracts; they are distinct from exact file hashes and canonical mathematical input hashes.',
               'Native n counts modeled integer decision variables; native size/machines are family parameters. FlatZinc bytes are reported without pretending that file size is a variable/constraint count.',
               'No solver result logs are read by this exporter.']}
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'corpus-summary.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    analyze.flat_csv(directory/'corpus-instances.csv',records)
    analyze.flat_csv(directory/'corpus-families.csv',payload['family_size_summary'])
    analyze.flat_csv(directory/'corpus-counts.csv',payload['summary_by_split_kind_family_source'])
    lines=['# Corpus inventory','',
           f"The core generated suite has **{len(core_representations)} representations covering {len(concepts)} normalized domain/model concepts**. TSP and coloring each have binary and native representations. These are not unrelated complexity classes; related formulations such as set packing/auction are deliberately identified.",'',
           '| Track | Instances | Known optimum references | Unknown optimum references | Optimum not applicable | Supplied incumbents |',
           '|---|---:|---:|---:|---:|---:|']
    for row in payload['summary_by_track']:
        lines.append('| '+row['track'].replace('_',' ')+' | '+' | '.join(str(row[key]) for key in ('instances','known_optimum_references','unknown_optimum_references','optimum_not_applicable','supplied_incumbents'))+' |')
    lines+=['','The **90 scale cases remain a separate evaluation track**. Public collections and FlatZinc regression/compatibility cases do not increase the core generated family headline. Corpus availability does not imply benchmark completion.','',
            'Known references are independent-oracle or published optima. FlatZinc expected text is checked for file identity and recorded as an upstream output regression reference; it is not an independent mathematical certificate.','',
            '`corpus-summary.json` includes manifest hashes, encoding-contract hashes, validator hashes, per-file/mathematical hashes, reference categories, all instances and explicit skips. `corpus-instances.csv`, `corpus-families.csv` and `corpus-counts.csv` provide the corresponding publication tables.','',
            'The exporter validates matrix schema, JSON/TXT equivalence, embedded reference identities and supplied incumbents. It reads no solver outcomes. It does not rerun independent optimum oracles.','']
    (directory/'CORPUS.md').write_text('\n'.join(lines))
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=Path,default=HERE/'reports/corpus')
    args=parser.parse_args();payload=export(args.out_dir);print(json.dumps(payload['counts'],sort_keys=True))


if __name__=='__main__':main()
