#!/usr/bin/env python3
"""Native CP workloads: scheduling, circuit TSP, coloring and weighted queens."""
import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAMILIES = ['job_shop', 'native_tsp', 'native_coloring', 'weighted_queens']


def mathematical_hash(instance):
    return hashlib.sha256(json.dumps({k: instance.get(k) for k in ['family','size','machines','n','data']},
                                    sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_assignment(p, x):
    if p['family']=='native_rcpsp':
        from native_rcpsp import validate_assignment as rcpsp_validate
        return rcpsp_validate(p,x)
    n=p['size']; d=p['data']; family=p['family']
    if not isinstance(x,list) or len(x)!=p['n'] or any(type(v)!=int for v in x):
        return {'valid':False,'error':'wrong assignment shape'}
    if family=='job_shop':
        jobs=n; machines=p['machines']; horizon=sum(t for _,t in d)
        if any(v<0 or v>horizon for v in x):return {'valid':False,'error':'start domain'}
        for j in range(jobs):
            for k in range(machines-1):
                a=j*machines+k
                if x[a]+d[a][1]>x[a+1]:return {'valid':False,'error':'precedence'}
        for a in range(len(x)):
            for b in range(a):
                if d[a][0]==d[b][0] and not (x[a]+d[a][1]<=x[b] or x[b]+d[b][1]<=x[a]):
                    return {'valid':False,'error':'machine overlap'}
        objective=max(v+d[i][1] for i,v in enumerate(x))
    elif family=='native_tsp':
        if sorted(x)!=list(range(n)):return {'valid':False,'error':'not a permutation'}
        seen=set();j=0
        for _ in range(n):seen.add(j);j=x[j]
        if len(seen)!=n or j!=0:return {'valid':False,'error':'not one Hamiltonian circuit'}
        objective=sum(d[i][v] for i,v in enumerate(x))
    elif family=='native_coloring':
        if any(v<0 or v>=n for v in x) or any(x[a]==x[b] for a,b in d):
            return {'valid':False,'error':'color conflict or domain'}
        objective=max(x)+1
    else:
        if sorted(x)!=list(range(n)) or len({x[j]+j for j in range(n)})!=n or len({x[j]-j for j in range(n)})!=n:
            return {'valid':False,'error':'queen conflict'}
        objective=sum(d[j][v] for j,v in enumerate(x))
    return {'valid':True,'objective':objective}


def validate_result(instance,result):
    if instance['family']=='native_rcpsp':
        from native_rcpsp import validate_result as rcpsp_validate
        return rcpsp_validate(instance,result)
    status=result.get('status');x=result.get('assignment',[])
    if status not in ['optimal','feasible','infeasible','unknown']:return {'valid':False,'error':'status'}
    ref=instance['reference'];known=ref['status']=='optimal'
    if ref.get('input_sha256')!=mathematical_hash(instance):return {'valid':False,'error':'stale reference'}
    if status in ['infeasible','unknown']:
        if x or result.get('objective') is not None:return {'valid':False,'error':'unexpected witness'}
        if status=='infeasible':return {'valid':False,'error':'generated instance has feasible witness'}
        return {'valid':True,'claims_verified':True,'optimality_independent':False}
    check=validate_assignment(instance,x)
    if not check['valid'] or check['objective']!=result.get('objective'):return {'valid':False,'error':'assignment or objective mismatch'}
    if known and (result['objective']<ref['objective'] or (status=='optimal' and result['objective']!=ref['objective'])):
        return {'valid':False,'error':'contradicts independent optimum'}
    return {'valid':True,'claims_verified':status!='optimal' or known,
            'optimality_independent':status=='optimal' and known}


def queens_reference(cost):
    n=len(cost);best=math.inf;answer=None
    def visit(row,cols,diag1,diag2,chosen,value):
        nonlocal best,answer
        if value>=best:return
        if row==n:best=value;answer=list(chosen);return
        for col in range(n):
            if col not in cols and col+row not in diag1 and col-row not in diag2:
                visit(row+1,cols|{col},diag1|{col+row},diag2|{col-row},chosen+[col],value+cost[row][col])
    visit(0,set(),set(),set(),[],0)
    return best,answer


def tsp_reference(cost):
    n=len(cost);states={(1,0):(0,None)}
    for mask in range(1,1<<n,2):
        for j in range(n):
            if (mask,j) not in states:continue
            value,_=states[mask,j]
            for k in range(1,n):
                if mask&(1<<k):continue
                key=(mask|(1<<k),k);candidate=value+cost[j][k]
                if key not in states or candidate<states[key][0]:states[key]=(candidate,j)
    full=(1<<n)-1;j=min(range(1,n),key=lambda j:states[full,j][0]+cost[j][0]);best=states[full,j][0]+cost[j][0]
    tour=[j];mask=full
    while j:
        parent=states[mask,j][1];mask^=1<<j;j=parent;tour.append(j)
    tour.reverse();succ=[0]*n
    for a,b in zip(tour,tour[1:]+[0]):succ[a]=b
    return best,succ


def make(family,tier,seed):
    rng=random.Random(seed);large=tier=='large';start=time.perf_counter()
    n={'job_shop':7 if large else 4,'native_tsp':12 if large else 8,
       'native_coloring':30 if large else 18,'weighted_queens':12 if large else 8}[family]
    p={'family':family,'size':n,'n':n,'tier':tier,'seed':seed,'kind':'native'}
    if family=='job_shop':
        machines=n;p['machines']=machines;p['n']=n*machines;data=[];witness=[];clock=0
        for _ in range(n):
            order=list(range(machines));rng.shuffle(order)
            for machine in order:
                duration=rng.randint(1,15);data.append([machine,duration]);witness.append(clock);clock+=duration
        p['data']=data
    elif family=='native_tsp':
        points=[(rng.randrange(100),rng.randrange(100)) for _ in range(n)]
        data=[[abs(a[0]-b[0])+abs(a[1]-b[1])+(i!=j) for j,b in enumerate(points)] for i,a in enumerate(points)]
        remaining=set(range(1,n));tour=[0]
        while remaining:
            k=min(remaining,key=lambda k:(data[tour[-1]][k],k));remaining.remove(k);tour.append(k)
        witness=[0]*n
        for a,b in zip(tour,tour[1:]+[0]):witness[a]=b
        p['data']=data
    elif family=='native_coloring':
        data=[[a,b] for a in range(n) for b in range(a) if rng.random()<(.32 if large else .28)]
        witness=[]
        for a in range(n):
            forbidden={witness[b] for aa,b in data if aa==a};v=0
            while v in forbidden:v+=1
            witness.append(v)
        p['data']=data
    else:
        p['data']=[[rng.randint(1,50) for _ in range(n)] for _ in range(n)]
        # Find a feasible placement without inspecting its weighted optimum.
        witness=None
        def first(row,chosen):
            if row==n:return chosen
            for col in range(n):
                if all(col!=v and abs(col-v)!=row-j for j,v in enumerate(chosen)):
                    result=first(row+1,chosen+[col])
                    if result is not None:return result
        witness=first(0,[])
    check=validate_assignment(p,witness);assert check['valid']
    p.update(incumbent=witness,incumbent_objective=check['objective'],construction_ms=(time.perf_counter()-start)*1000)
    p['reference']={'status':'unknown','input_sha256':mathematical_hash(p),'method':'not independently certified'}
    if family in ['native_tsp','weighted_queens']:
        oracle=time.perf_counter();best,answer=(tsp_reference if family=='native_tsp' else queens_reference)(p['data'])
        assert validate_assignment(p,answer)=={'valid':True,'objective':best}
        p['reference'].update(status='optimal',objective=best,assignment=answer,
            method='Held-Karp dynamic programming' if family=='native_tsp' else 'independent exhaustive queen enumeration',
            elapsed_ms=(time.perf_counter()-oracle)*1000)
    return p


def generate():
    records=[];directory=HERE/'native-instances';directory.mkdir(exist_ok=True)
    for f,family in enumerate(FAMILIES):
        for t,tier in enumerate(['small','large']):
            for split,count,offset in [('dev',3,1000),('test',5,2000)]:
                for rep in range(count):
                    seed=9000000+f*100000+t*10000+offset+rep;p=make(family,tier,seed)
                    identity=f'{split}_{family}_{tier}_{seed}';p.update(id=identity,split=split,label=f'{family} {tier} seed {seed}')
                    stem=directory/identity;(stem.with_suffix('.json')).write_text(json.dumps(p,indent=2)+'\n')
                    flat=[v for row in p['data'] for v in row]
                    text=f"{family} {p['size']} {p.get('machines',0)} {len(p['data'])}\n"+' '.join(map(str,flat))+'\n'+' '.join(map(str,p['incumbent']))+'\n'
                    stem.with_suffix('.txt').write_text(text)
                    records.append({k:p[k] for k in ['id','family','tier','split','seed','label','kind']}|{'json':str(stem.with_suffix('.json').relative_to(HERE)),'txt':str(stem.with_suffix('.txt').relative_to(HERE))})
    (HERE/'native-manifest.json').write_text(json.dumps({'schema_version':1,'instances':records},indent=2)+'\n')
    print(f'Generated {len(records)} native CP instances')


if __name__=='__main__':generate()
