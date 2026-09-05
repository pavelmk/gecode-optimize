#!/usr/bin/env python3
"""Fixed paired formulations: identical semantic problems, no timing/oracles."""
import argparse
from datetime import datetime,timezone
import itertools
import json
from pathlib import Path
import time
from types import FunctionType

import analyze
import generator
import native
import validate

HERE=Path(__file__).resolve().parent
SEED_BASE=40_000_000


def canonical_colors(colors):
    labels={};answer=[]
    for color in colors:
        if color not in labels:labels[color]=len(labels)
        answer.append(labels[color])
    return answer


def coloring_bits(colors,vertices):
    colors=canonical_colors(colors);used=max(colors)+1
    return [int(colors[v]==c) for v in range(vertices) for c in range(vertices)]+[int(c<used) for c in range(vertices)]


def tour_bits(order,problem):
    n=problem['parameters']['cities'];arcs={(order[t],order[(t+1)%n]) for t in range(n)}
    return [int(order[t]==v) for v in range(n) for t in range(n)]+[int(tuple(arc) in arcs) for arc in problem['parameters']['arcs']]


def successors(order):
    values=[0]*len(order)
    for index,city in enumerate(order):values[city]=order[(index+1)%len(order)]
    return values


def models(family,tier,seed):
    if family=='tsp':
        binary=generator.make_model('tsp',tier,seed);binary['family']='tsp'
        incumbent,method=generator.make_incumbent(binary);n=binary['parameters']['cities']
        order=[next(v for v in range(n) if incumbent[v*n+t]) for t in range(n)]
        semantic={'problem':'tsp','cities':n,'distances':binary['parameters']['distances']}
        cp={'family':'native_tsp','size':n,'machines':0,'n':n,'data':semantic['distances']}
        cp_incumbent=successors(order)
    else:
        vertices=generator.dimension(tier,4,8,20)
        def dimension(tiny_tier,tiny,small,large):
            return vertices if (tiny,small,large)==(3,4,6) else generator.dimension(tiny_tier,tiny,small,large)
        isolated=FunctionType(generator.make_model.__code__,dict(generator.make_model.__globals__,dimension=dimension))
        binary=isolated('coloring',tier,seed);binary['family']='coloring'
        # Both formulations permit up to |V| colors and use first-use labels.
        # Every enabled color is used, giving exactly the native max(label)+1
        # objective on canonical colorings rather than a redundant higher cost.
        additions=generator.Builder(binary['c'])
        for color in range(vertices):
            additions.ge([(v*vertices+color,1) for v in range(vertices)]+[(vertices*vertices+color,-1)],0)
        for vertex in range(vertices):
            for color in range(1,vertices):
                additions.ge([(u*vertices+color-1,1) for u in range(vertex)]+[(vertex*vertices+color,-1)],0)
        binary['rows'].extend(additions.rows)
        original,method=generator.make_incumbent(binary)
        cp_incumbent=canonical_colors([next(c for c in range(vertices) if original[v*vertices+c]) for v in range(vertices)])
        incumbent=coloring_bits(cp_incumbent,vertices)
        semantic={'problem':'coloring','vertices':vertices,'edges':binary['parameters']['edges']}
        cp={'family':'native_coloring','size':vertices,'machines':0,'n':vertices,'data':semantic['edges']}
        binary['paired_symmetry']='enabled iff used; color labels assigned in order of first appearance'
        method+='; canonical first-use color relabeling'
    binary_check=validate.validate_assignment(binary,incumbent);native_check=native.validate_assignment(cp,cp_incumbent)
    if not binary_check['valid'] or not native_check['valid'] or binary_check['objective']!=native_check['objective']:
        raise ValueError('Paired witness/objective disagreement')
    binary.update(incumbent=incumbent,incumbent_objective=binary_check['objective'],incumbent_method=method)
    cp.update(incumbent=cp_incumbent,incumbent_objective=native_check['objective'],incumbent_method='Same semantic incumbent as binary partner; representation conversion only')
    return binary,cp,semantic


def native_text(problem):
    return (f"{problem['family']} {problem['size']} {problem['machines']} {len(problem['data'])}\n"
            +'\n'.join(' '.join(map(str,row)) for row in problem['data'])+'\n'
            +' '.join(map(str,problem['incumbent']))+'\n')


def tiny_equivalence_checks():
    checks=[]
    binary,cp,semantic=models('tsp','tiny',SEED_BASE)
    n=semantic['cities'];count=0
    for remaining in itertools.permutations(range(1,n)):
        order=[0,*remaining];b=validate.validate_assignment(binary,tour_bits(order,binary));c=native.validate_assignment(cp,successors(order))
        if not b['valid'] or not c['valid'] or b['objective']!=c['objective']:raise ValueError('Tiny paired TSP mapping failed')
        count+=1
    checks.append({'family':'tsp','semantic_assignments_checked':count,'passed':True,'method':'all tours with city0 fixed; no optimum computed'})
    binary,cp,semantic=models('coloring','tiny',SEED_BASE+1);n=semantic['vertices'];count=0
    for raw in itertools.product(range(n),repeat=n):
        colors=canonical_colors(raw);semantically_valid=all(colors[u]!=colors[v] for u,v in semantic['edges'])
        b=validate.validate_assignment(binary,coloring_bits(colors,n));c=native.validate_assignment(cp,colors)
        if b['valid']!=semantically_valid or c['valid']!=semantically_valid:raise ValueError('Tiny paired coloring feasibility mapping failed')
        if semantically_valid and b['objective']!=c['objective']:raise ValueError('Tiny paired coloring objective mapping failed')
        count+=1
    checks.append({'family':'coloring','semantic_assignments_checked':count,'passed':True,'method':'all labelings normalized to first use; no optimum computed'})
    return checks


def generate(directory):
    started=time.perf_counter();directory.mkdir(parents=True,exist_ok=True);path=directory/'paired-manifest.json'
    if path.exists():raise ValueError('Refusing to overwrite frozen paired corpus')
    plan=[];semantic_ids=[]
    for family_index,family in enumerate(('tsp','coloring')):
        for tier_index,tier in enumerate(('small','large')):
            for replication in range(5):
                seed=SEED_BASE+family_index*100000+tier_index*10000+replication
                identity=f'formulation_{family}_{tier}_{seed}';semantic_ids.append(identity)
                for kind in ('binary','native'):
                    representation=family if kind=='binary' else 'native_'+family
                    plan.append({'id':identity+'_'+kind,'paired_problem_id':identity,'semantic_problem':family,
                      'family':representation,'kind':kind,'tier':tier,'split':'formulation','seed':seed,'ready':False,
                      'json':f'paired-instances/{identity}_{kind}.json','txt':f'paired-instances/{identity}_{kind}.txt',
                      'semantic_json':f'paired-instances/{identity}_semantic.json'})
    seeds={r['seed'] for r in plan}
    for other in HERE.glob('*manifest.json'):
        if other.name=='paired-manifest.json':continue
        if any(r.get('seed') in seeds for r in json.loads(other.read_text()).get('instances',[])):
            raise ValueError('Paired seed overlaps previous corpus')
    source_hashes={name:analyze.sha(HERE/name) for name in ('generator.py','validate.py','native.py','generate_paired.py')}
    manifest={'schema_version':1,'generation_status':'in_progress','ready':False,'split':'formulation',
      'planned_utc':datetime.now(timezone.utc).isoformat(),'instances':plan,'semantic_problems':len(semantic_ids),
      'encodings':len(plan),'source_hashes':source_hashes,
      'selection':'Two preselected semantic families, two fixed sizes, five fresh seeds; no solver outcomes or timings read.',
      'interpretation':'Paired formulations of identical semantic inputs; this track does not enlarge main held-out or generated-concept counts.'}
    path.write_text(json.dumps(manifest,indent=2)+'\n');(directory/'paired-instances').mkdir(exist_ok=True)
    delivered=[]
    for index in range(0,len(plan),2):
        pair=plan[index:index+2];record=pair[0];case_start=time.perf_counter()
        binary,cp,semantic=models(record['semantic_problem'],record['tier'],record['seed'])
        construction=time.perf_counter()-case_start;semantic_hash=analyze.digest(semantic)
        (directory/record['semantic_json']).write_text(json.dumps(semantic,indent=2)+'\n')
        for item,problem in zip(pair,(binary,cp)):
            problem.update({key:item[key] for key in ('id','paired_problem_id','semantic_problem','family','kind','tier','split','seed')})
            problem.update(semantic_input_sha256=semantic_hash,label=f"{item['semantic_problem']} paired {item['kind']} {item['tier']}",
              construction_ms=construction*1000,
              reference={'status':'unknown','input_sha256':analyze.mathematical_hash(problem,item['kind']),
                         'method':'No optimum oracle run for paired formulation generation'})
            txt=generator.to_text(problem) if item['kind']=='binary' else native_text(problem)
            (directory/item['json']).write_text(json.dumps(problem,indent=2)+'\n');(directory/item['txt']).write_text(txt)
            analyze.txt_matches(problem,directory/item['txt'],item['kind'])
            checked=analyze.assignment_check(problem,problem['incumbent'],item['kind'])
            if not checked['valid'] or checked['objective']!=problem['incumbent_objective']:raise ValueError('Paired final witness failed')
            delivered.append({**item,'ready':True,'n':problem['n'],'reference_status':'unknown',
              'incumbent_objective':problem['incumbent_objective'],'semantic_input_sha256':semantic_hash,
              'input_sha256':analyze.mathematical_hash(problem,item['kind']),
              'json_sha256':analyze.sha(directory/item['json']),'txt_sha256':analyze.sha(directory/item['txt'])})
    checks=tiny_equivalence_checks()
    if any(analyze.sha(HERE/name)!=value for name,value in source_hashes.items()):raise ValueError('Paired source changed during generation')
    manifest.update(instances=delivered,generation_status='complete',ready=True,tiny_mapping_checks=checks,
                    completed_utc=datetime.now(timezone.utc).isoformat(),generation_seconds=time.perf_counter()-started)
    path.write_text(json.dumps(manifest,indent=2)+'\n');return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=Path,default=HERE)
    args=parser.parse_args();manifest=generate(args.out_dir)
    print(json.dumps({'semantic_problems':manifest['semantic_problems'],'encodings':manifest['encodings'],
                      'seconds':manifest['generation_seconds'],'mapping_checks':manifest['tiny_mapping_checks']},sort_keys=True))


if __name__=='__main__':main()
