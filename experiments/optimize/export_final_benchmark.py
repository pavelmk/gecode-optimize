#!/usr/bin/env python3
"""Export all three observed cohorts for the existing dashboard; never run solvers."""
import argparse
import json
from pathlib import Path
import statistics

from benchmark_final import COHORTS, ROOT, require, sha, generator, validate, legacy

CATEGORIES = {
    'knapsack': ('Knapsack', 'Both random and correlated profits'),
    'assignment': ('Assignment', 'One task per worker'),
    'facility_location': ('Facility location', 'Two customers per candidate site'),
    'bin_packing': ('Bin packing', 'Weighted items; candidate bins grow with size'),
    'production': ('Production planning', 'Eight quantity options per period'),
    'native_tsp': ('Routing', 'Minimum-cost tour through all cities'),
    'weighted_queens': ('Weighted queens', 'Minimum-cost non-attacking placement'),
}


def export(path):
    report=json.loads(path.read_text())
    require(report['complete'] and all(report['provenance']['integrity'].values()),'Incomplete study')
    require(set(report['protocol']['cohort_labels'])==set(COHORTS),'Incorrect cohorts')
    records=[r for r in report['records'] if not r['probe']]
    require(all(r['status'] in ('optimal','time_limit','memory_limit') for r in records),'Invalid attempt')
    keys=[(r['case'],r['cohort'],r['repetition']) for r in records]
    require(len(keys)==len(set(keys)),'Duplicate observation')
    models={m['id']:m for m in report['models']}
    for key,value in models.items():
        for suffix in ('json','txt'):
            require(sha(path.parent/'models'/(key+'.'+suffix))==value[suffix+'_sha256'],'Input changed')
    for r in report['records']:
        model=models[r['case']]['model'];raw=r['backend_result']
        selected=report['protocol']['policy']['families'][r['category']]['route']
        route='native' if r['cohort']=='before' else 'auto-race' if r['cohort']=='auto' else selected
        require(route==r['route']==raw['route'],'Route differs from frozen policy')
        checked=legacy.validate(raw,model) if r['cohort']=='before' else validate(raw,model,route)
        for key in ('passed','status','solve_seconds','primal_checked','objective','best_bound'):
            require(checked[key]==r[key],'Validation projection differs')
    families=[]
    for category,(name,detail) in CATEGORIES.items():
        selected=[r for r in records if r['category']==category]
        sizes=sorted({r['size'] for r in selected});variants=2 if category=='knapsack' else 1
        def rows(size,cohort):
            return [r for r in selected if r['size']==size and r['cohort']==cohort]
        def passing(size,cohort,confirmed=False):
            found=rows(size,cohort)
            identities={(r['variant'],r['repetition']) for r in found}
            names=('uncorrelated','correlated') if variants==2 else ('single',)
            needed={(v,r) for v in names for r in range(1,3 if confirmed else 2)}
            return needed<=identities and all(r['passed'] for r in found)
        def label(size):
            if size is None:return 'No confirmed size'
            model=models[next(r['case'] for r in selected if r['size']==size)]['model']
            return f"{size} {model['size_unit']}"
        cases=[]
        for size in sizes:
            model=models[next(r['case'] for r in selected if r['size']==size)]['model']
            item=dict(id=f'{category}-{size}',size=size,tier='adaptive',variables=model['model_variables'],
                size_label=label(size),dimensions=label(size),eligible=category=='knapsack',variant_count=variants)
            for cohort in COHORTS:
                found=rows(size,cohort)
                require(len(found) in (0,variants,2*variants),'Incomplete variant group')
                solved=bool(found) and all(r['passed'] for r in found)
                ms=[r['solve_seconds']*1000 for r in found];wall=[r['external_seconds']*1000 for r in found]
                status='not_tested' if not found else 'solved' if solved else 'limited' if any(r['status'] in ('time_limit','memory_limit') for r in found) else 'mixed'
                item[cohort]=dict(completed=sum(r['passed'] for r in found),attempts=len(found),status=status,
                    median_solve_ms=statistics.median(ms) if solved else None,
                    min_solve_ms=min(ms) if solved else None,max_solve_ms=max(ms) if solved else None,
                    median_wall_ms=statistics.median(wall) if solved else None)
            cases.append(item)
        family=dict(id=category,name=name,detail=detail,role='target',cases=cases,
            configuration=report['protocol']['policy']['families'][category],
            capacity_note='Largest sampled size confirmed twice in every variant. Ceiling bars are lower bounds; untested sizes remain unknown.')
        for cohort in COHORTS:
            best=max((s for s in sizes if passing(s,cohort,True)),default=None)
            bigger=[s for s in sizes if best is not None and s>best and rows(s,cohort) and not passing(s,cohort)]
            failure=min(bigger,default=None)
            capped=best==report['protocol']['limits'][category][2]
            if best is None:note='No size passed both confirmation runs.'
            elif failure is not None:note=f'Next tested failure: {label(failure)}.'
            elif capped:note='Search ceiling reached; upper limit unknown.'
            else:note='No larger failure confirmed; upper limit unknown.'
            exploratory=[s for s in sizes if passing(s,cohort) and (best is None or s>best)]
            if exploratory:note+=' Larger discovery pass unconfirmed: '+label(max(exploratory))+'.'
            reversals=sum(bool(rows(s,cohort)) and not passing(s,cohort) and any(t>s and passing(t,cohort) for t in sizes) for s in sizes)
            family[cohort+'_boundary']=dict(label=label(best),next=note,reversals=reversals,
                confirmed_size=best,next_failure_size=failure,censored=capped)
            family[cohort+'_max']=next((c['variables'] for c in cases if c['size']==best),None)
        families.append(family)
    anomalies=[dict(case=r['case'],cohort=r['cohort'],repetition=r['repetition']) for r in records
               if r['backend_result']['driver_seconds']>r['external_seconds']+0.1]
    require(all(not r['passed'] for r in records if
        r['backend_result']['driver_seconds']>r['external_seconds']+0.1),
        'A claimed passing result has inconsistent process/solve clocks; review required')
    payload=dict(schema_version=1,families=families,runs=len(records),cases=len({r['case'] for r in records}),
        elapsed_seconds=report['elapsed_seconds'],clock_anomalies=anomalies,seconds=10,
        source_commit=report['provenance']['source_head'],report_sha256=sha(path),
        cohort_labels=report['protocol']['cohort_labels'],configured=True,final=True,policy=report['protocol']['policy'])
    output=json.dumps(dict(projection=payload,report=report),indent=2,allow_nan=False)+'\n'
    require(all(p not in output for p in ('/Users/','/home/','file://')),'Private path in export')
    (path.parent/'projection.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    (path.parent/'gecode-final.json').write_text(output)
    (path.parent/'public.json').write_text(output)
    lines=['# Final native algorithm comparison','',
        'Three freshly measured cohorts use the same deterministic original models, one thread and ten seconds per solve. The automatic clock includes every racing probe and selected restart. All processes run serially.', '',
        'Original Gecode is the preserved optimization-facade baseline before the algorithm changes, not a pristine upstream distribution. Automatic uses structural preprocessing and a bounded sequential race; configured uses the frozen family policy, with compact DP for knapsack.', '',
        '| Problem size unit | Original | Auto + race | Configured |', '|---|---:|---:|---:|']
    for f in families:
        cells=[]
        for c in COHORTS:
            b=f[c+'_boundary'];cells.append(('≥' if b['censored'] else '')+b['label'])
        lines.append('| '+f['name']+' | '+' | '.join(cells)+' |')
    lines += ['',f'{len(records)} measured attempts plus three runtime probes; total elapsed {report["elapsed_seconds"]:.2f} seconds.', '',
        'Each bar is the largest sampled size passing two repetitions and every variant. ≥ marks a search ceiling, not a measured upper limit. Bisection is a sampling heuristic; difficulty need not be monotonic and raw reversals are retained. Every returned original witness is independently checked; exact optimality is backend-reported. No independent optimum oracle or holdout-family claim is made.', '',
        'Racing can increase total CPU use and elapsed solve time by repeating exploratory work and restarting a strategy. A short exploration may identify a much more effective route for a longer solve; gains are workload-dependent.', '',
        'The JSON export contains every probe, attempt, status, timing, bound, objective, original witness, frozen input hash, policy, source hash and verified loader identity. No unsuccessful attempt is silently removed.', '',
        'Report SHA256: '+sha(path), '']
    (path.parent/'FINAL-BENCHMARK.md').write_text('\n'.join(lines))
    print(json.dumps({'runs':len(records),'families':len(families),'report_sha256':sha(path)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report',type=Path)
    export(parser.parse_args().report.resolve(strict=True))
