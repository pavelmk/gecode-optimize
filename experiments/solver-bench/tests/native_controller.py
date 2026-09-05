#!/usr/bin/env python3
"""Tiny exact native-controller checks; run only outside benchmark timing windows.

Six embedded fixtures exercise independent exhaustive optima, warm starts,
branching, controller modes, short budgets and malformed inputs. No corpus
download, benchmark batch or build is launched. --legacy-bin additionally
checks original native assignments and search counts against an earlier build.
"""
import argparse
from pathlib import Path
import datetime, hashlib, itertools, json, math, subprocess, time
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'experiments/solver-bench'
MODELS=[
 {'family':'job_shop','size':2,'machines':2,'rows':4,'data':[0,2,1,1,1,2,0,1],'incumbent':[0,2,3,5]},
 {'family':'native_rcpsp','size':3,'machines':1,'rows':2,'data':[2,2,1,2,1,1,2,0,2,1,2],'incumbent':[0,2,4]},
 {'family':'native_tsp','size':4,'machines':0,'rows':4,'data':[0,1,7,5,5,0,1,7,7,5,0,1,1,7,5,0],'incumbent':[2,3,1,0]},
 {'family':'weighted_queens','size':4,'machines':0,'rows':4,'data':[10,4,7,12,5,8,13,1,5,9,11,13,2,5,8,14],'incumbent':[2,0,3,1]},
 {'family':'native_coloring','size':4,'machines':0,'rows':4,'data':[0,1,1,2,2,3,3,0],'incumbent':[0,1,2,3]},
 {'family':'native_coloring','size':1,'machines':0,'rows':0,'data':[],'incumbent':[0]},
]
def cost(p,x):
 n=p['size'];f=p['family'];d=p['data']
 if not isinstance(x,list) or any(type(v)!=int for v in x) or len(x)!=len(p['incumbent']):return None
 if f in ['native_tsp','weighted_queens']:
  if sorted(x)!=list(range(n)):return None
  if f=='weighted_queens':
   if len({x[i]+i for i in range(n)})!=n or len({x[i]-i for i in range(n)})!=n:return None
  else:
   visited=set();j=0
   for _ in range(n):visited.add(j);j=x[j]
   if j!=0 or len(visited)!=n:return None
  return sum(d[i*n+x[i]] for i in range(n))
 if f=='native_coloring':
  if any(v<0 or v>=n for v in x) or any(x[d[i]]==x[d[i+1]] for i in range(0,len(d),2)):return None
  return max(x)+1
 if f=='job_shop':
  count=n*p['machines'];dur=d[1::2];machines=d[::2];horizon=sum(dur)
  if any(v<0 or v>horizon for v in x):return None
  for j in range(n):
   for k in range(p['machines']-1):
    a=j*p['machines']+k
    if x[a]+dur[a]>x[a+1]:return None
  for a in range(count):
   for b in range(a):
    if machines[a]==machines[b] and not(x[a]+dur[a]<=x[b] or x[b]+dur[b]<=x[a]):return None
  return max(x[i]+dur[i] for i in range(count))
 resources=p['machines'];dur=[d[resources+i*(resources+1)] for i in range(n)];horizon=sum(dur)
 if any(v<0 or v>horizon for v in x):return None
 edges=d[resources+n*(resources+1):]
 for a,b in zip(edges[::2],edges[1::2]):
  if x[a]+dur[a]>x[b]:return None
 for r in range(resources):
  for t in range(horizon+max(dur)):
   if sum(d[resources+i*(resources+1)+r+1] for i in range(n) if x[i]<=t<x[i]+dur[i])>d[r]:return None
 return max(x[i]+dur[i] for i in range(n))
def oracle(p):
 n=p['size'];f=p['family']
 if f in ['native_tsp','weighted_queens']:points=itertools.permutations(range(n))
 elif f=='native_coloring':points=itertools.product(range(n),repeat=n)
 else:
  horizon=sum(p['data'][1::2]) if f=='job_shop' else sum(p['data'][p['machines']+i*(p['machines']+1)] for i in range(n))
  points=itertools.product(range(horizon+1),repeat=len(p['incumbent']))
 values=[v for point in points if (v:=cost(p,list(point))) is not None]
 return min(values)
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--bin',type=Path,default=ROOT/'build/solver-bench/bin',help='Directory containing stock-native and enhanced-native')
 parser.add_argument('--legacy-bin',type=Path,help='Optional prior binary directory for exact native-mode search controls')
 parser.add_argument('--work-dir',type=Path,default=ROOT/'build/solver-bench/native-controller-tests',help='Generated tiny test inputs; no external corpus required')
 parser.add_argument('--output',type=Path,default=HERE/'results/native-controller-tests.json')
 args=parser.parse_args()
 if not __debug__:parser.error('Correctness tests require assertions; remove -O/PYTHONOPTIMIZE')
 args.bin=args.bin.resolve();args.work_dir=args.work_dir.resolve();args.output=args.output.resolve()
 if args.legacy_bin is not None:args.legacy_bin=args.legacy_bin.resolve()
 for directory in [args.bin]+([args.legacy_bin] if args.legacy_bin is not None else []):
  for name in ['stock-native','enhanced-native']:
   if not (directory/name).is_file():parser.error(f'Missing {directory/name}; build the benchmark drivers first')
 INPUTS=args.work_dir;INPUTS.mkdir(parents=True,exist_ok=True)
 records=[];results=[];count=0;legacy=[]
 for index,p in enumerate(MODELS):
  expected=oracle(p);assert cost(p,p['incumbent']) is not None
  path=INPUTS/f'{index}_{p["family"]}.txt'
  path.write_text(f'{p["family"]} {p["size"]} {p["machines"]} {p["rows"]}\n'+ ' '.join(map(str,p['data']))+'\n'+' '.join(map(str,p['incumbent']))+'\n')
  records.append({'model':p,'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'exhaustive_optimum':expected})
  for binary in ['stock-native','enhanced-native']:
   folder=args.bin;old=args.legacy_bin
   for warm in [0,1]:
    for branching in ['afc','size','degree']:
     native=None
     for mode in ['native','lns','incumbent']:
      command=[str(folder/binary),str(path),mode,branching,'2000',str(warm),'1'];run=subprocess.run(command,capture_output=True,text=True,timeout=5)
      assert run.returncode==0,(command,run.stderr)
      r=json.loads(run.stdout);actual=cost(p,r['assignment']);assert actual==expected==r['objective'] and r['status']=='optimal',(command,r,expected,actual)
      previous=cost(p,p['incumbent']) if warm else math.inf
      for stamp,value in r['improvements']:assert value<previous;previous=value
      assert r['neighborhoods']<=8 and r['total_nodes']==r['nodes']+r['heuristic_nodes']
      if mode!='lns' or not warm:assert r['neighborhoods']==0
      if mode=='native':native=r
      results.append({'fixture':index,'binary':binary,'mode':mode,'branching':branching,'warm':warm,'output':r});count+=1
     if old is not None:
      command=[str(old/binary),str(path),'native',branching,'2000',str(warm),'1'];run=subprocess.run(command,capture_output=True,text=True,timeout=5);assert run.returncode==0,run.stderr
      previous=json.loads(run.stdout)
      for field in ['objective','status','assignment','nodes','failures','propagations']:assert previous[field]==native[field],(index,binary,warm,branching,field,previous[field],native[field])
      legacy.append({'fixture':index,'binary':binary,'warm':warm,'branching':branching,'same_fields':['objective','status','assignment','nodes','failures','propagations']})
 # Very small budgets may stop or may finish during uninterruptible propagation;
 # only witness validity and accounting are asserted, not hard real-time behavior.
 for p,record in zip(MODELS,records):
  for mode in ['native','lns','incumbent']:
   command=[str(args.bin/'enhanced-native'),str(ROOT/record['path']),mode,'afc','0.000001','1','1'];run=subprocess.run(command,capture_output=True,text=True,timeout=5);assert run.returncode==0,run.stderr
   r=json.loads(run.stdout);assert cost(p,r['assignment'])==r['objective'];assert r['neighborhoods']<=8
   results.append({'fixture':p['family'],'budget_edge':True,'mode':mode,'output':r})
 invalid=[]
 for budget in ['0','-1','nan','inf','86400001']:
  command=[str(args.bin/'enhanced-native'),str(ROOT/records[0]['path']),'lns','afc',budget,'1','1'];r=subprocess.run(command,capture_output=True,text=True,timeout=5);assert r.returncode!=0;invalid.append({'budget':budget,'returncode':r.returncode,'stderr':r.stderr})
 bad=INPUTS/'bad-start.txt';parts=Path(str(ROOT/records[0]['path'])).read_text().splitlines();parts[-1]='2147483647 2 3 5';bad.write_text('\n'.join(parts)+'\n');r=subprocess.run([str(args.bin/'enhanced-native'),str(bad),'lns','afc','100','1','1'],capture_output=True,text=True,timeout=5);assert r.returncode!=0;invalid.append({'bad_start':True,'returncode':r.returncode,'stderr':r.stderr})
 source=args.bin/'source/experiments/solver-bench/native-driver.cpp'
 snapshot=source.is_file()
 if not snapshot:source=HERE/'native-driver.cpp'
 report={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'passed','optimized_cases':count,'legacy_exact_controls':len(legacy),'models':records,'results':results,'legacy_controls':legacy,'invalid_inputs':invalid,'binaries':{name:hashlib.sha256((args.bin/name).read_bytes()).hexdigest() for name in ['stock-native','enhanced-native']},'native_driver_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'native_source_is_build_snapshot':snapshot,'test_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 if args.legacy_bin is not None:report['legacy_binaries']={name:hashlib.sha256((args.legacy_bin/name).read_bytes()).hexdigest() for name in ['stock-native','enhanced-native']}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(f'PASS {count} exhaustive-optimum controller cases, {len(legacy)} exact legacy controls, 18 short-budget witnesses, 6 invalid-input cases')

if __name__=='__main__': main()
