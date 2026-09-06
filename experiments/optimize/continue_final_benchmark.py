#!/usr/bin/env python3
"""Continue the preserved final study without size ceilings or repeating observations.

The user amended the protocol after bounded discovery began. Preserve that phase,
then extend each cohort until a confirmed failed upper input exists. Bisection
stops at max(1,ceil(2% of lower)) size units. These are observations, not a proof
of monotonic difficulty or an absolute maximum. No algorithm/preset is changed.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

import benchmark_final as initial
import final_instances as generator

ROOT, HERE, sha, require = initial.ROOT, initial.HERE, initial.sha, initial.require
legacy, common, COHORTS = initial.legacy, initial.common, initial.COHORTS
initial.generator = initial.configured.generator = legacy.generator = generator
legacy.MAX_ATTEMPTS = 2400
legacy.WHOLE_SECONDS = 14400


class ContinuedSearch(initial.FinalSearch):
    def __init__(self, report_path, output, binary, runtime):
        report_path=report_path.resolve(strict=True)
        old=json.loads(report_path.read_text())
        require(old['complete'] and all(old['provenance']['integrity'].values()),'Initial phase incomplete')
        self.output=output.resolve();require(not self.output.exists(),'Continuation output already exists')
        shutil.copytree(report_path.parent,self.output)
        shutil.copy2(report_path,self.output/'phase1-report.json')
        self.started=time.monotonic()-old['elapsed_seconds']
        self.utc=old['started_utc'];self.binary=binary.resolve(strict=True)
        self.old_binary=ROOT/'build/capacity-scaling/fixed-driver/optimize-native-benchmark'
        self.runtime=runtime.resolve(strict=True)
        self.directories={'before':[ROOT/'build/comparison-algorithms/before/lib'],
            'auto':[self.runtime/'gecode/optimize',self.runtime],
            'configured':[self.runtime/'gecode/optimize',self.runtime]}
        self.models={m['id']:m for m in old['models']}
        self.records=old['records'];self.decisions=old['decisions']
        self.sources=dict(old['provenance']['sources']);self.runtime_sources=old['provenance']['runtime_sources']
        for name in ('continue_final_benchmark.py','final_instances.py','export_extended_benchmark.py'):
            self.sources['experiments/optimize/'+name]=sha(HERE/name)
        self.provenance=old['provenance'];self.expected=self.provenance['expected_libraries']
        self.current_libraries=json.loads((self.binary.parent/'build.local.json').read_text())['runtime_libraries_sha256']
        require(sha(self.binary)==self.provenance['driver_sha256'],'Driver changed between phases')
        require(sha(self.old_binary)==self.provenance['original_driver_sha256'],'Original driver changed')
        require(all(sha(Path(p))==h for p,h in self.current_libraries.items()),'Current runtime changed')
        require(all(sha(ROOT/p)==h for p,h in self.sources.items()),'Measurement source changed')
        require(all(sha(ROOT/p)==h for p,h in self.runtime_sources.items()),'Solver source changed')
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        self.provenance['phases']=[dict(name='bounded discovery',source_head=self.provenance['source_head'],
            report_sha256=sha(report_path),records=len(self.records),protocol=old['protocol']),
            dict(name='user-requested extension without study ceilings',source_head=head,
            started_utc=datetime.now(timezone.utc).isoformat(),initial_records=len(self.records),
            reason='User requested observed failed upper sizes instead of censored study ceilings.')]
        self.provenance['source_head']=head;self.provenance['sources']=self.sources
        self.protocol=dict(old['protocol']);self.policy=self.protocol['policy']
        self.protocol['initial_study_limits']=self.protocol['limits']
        self.protocol['limits']={k:list(v) for k,v in self.protocol['limits'].items()}
        self.protocol.update(whole_seconds=legacy.WHOLE_SECONDS,max_attempts=legacy.MAX_ATTEMPTS,
            size_ceiling=None,boundary_relative_width=0.02,
            capacity='Largest confirmed sampled pass, with a separately observed two-repeat failed upper input. No study size ceiling. Bisection narrows to max(1,ceil(2% of lower)) units; difficulty can be nonmonotonic.',
            selection='Preserve every initial observation. Independently extend each cohort until a two-repeat failed upper input, then bisect to a 2% or one-unit bracket. Never select a configured route from new timings.',
            extended_boundaries={})
        self.complete=False;self.publish()

    def query(self,category,size,reason,repeats=2,cohorts=COHORTS):
        require(type(size) is int and size>=self.protocol['limits'][category][0],'Invalid size')
        self.decisions.append(dict(category=category,size=size,reason=reason,repeats=repeats,
            after_records=len(self.records),cohorts=list(cohorts),phase=2))
        self.publish()
        variants=('uncorrelated','correlated') if category=='knapsack' else ('single',)
        for repetition in range(1,repeats+1):
            for cohort in (cohorts if repetition==1 else cohorts[::-1]):
                for variant in variants:
                    if not any(r['category']==category and r['size']==size and r['cohort']==cohort and
                        r['variant']==variant and r['repetition']==repetition for r in self.records):
                        self.execute(category,size,variant,cohort,repetition)

    def failed(self,category,size,cohort):
        rows=self.rows(category,size,cohort)
        variants=('uncorrelated','correlated') if category=='knapsack' else ('single',)
        require(len(rows)==len({(r['variant'],r['repetition']) for r in rows}),'Duplicate observation')
        complete={(v,r) for v in variants for r in (1,2)} <= {(r['variant'],r['repetition']) for r in rows}
        return complete and all(any(not r['passed'] for r in rows if r['repetition']==rep) for rep in (1,2))

    def run(self):
        for category in self.protocol['limits']:
            self.protocol['extended_boundaries'][category]={}
            for cohort in COHORTS:
                sizes=self.sizes(category)
                passes=[s for s in sizes if self.passed(category,s,cohort,True)]
                require(passes,'No initial confirmed passing size for '+category+'/'+cohort)
                low=max(passes)
                failed=[s for s in sizes if s>low and self.failed(category,s,cohort)]
                high=min(failed,default=None)
                # Reuse any discovered but not yet repeated larger failure first.
                for candidate in sorted(s for s in sizes if s>low and self.rows(category,s,cohort)):
                    if high is not None:break
                    self.query(category,candidate,'confirm existing upper observation',cohorts=(cohort,))
                    if self.passed(category,candidate,cohort,True):low=candidate
                    elif self.failed(category,candidate,cohort):high=candidate
                next_size=low*2
                while high is None:
                    self.query(category,next_size,'uncapped exponential upper search',cohorts=(cohort,))
                    if self.passed(category,next_size,cohort,True):low=next_size
                    elif self.failed(category,next_size,cohort):high=next_size
                    next_size*=2
                while high-low>max(1,math.ceil(0.02*low)):
                    mid=(low+high)//2
                    seen={r['size'] for r in self.records if not r['probe'] and r['category']==category and r['cohort']==cohort and r['repetition']==2}
                    candidate=None
                    for distance in range(len(seen)+1):
                        for value in (mid-distance,mid+distance):
                            if low<value<high and value not in seen:
                                candidate=value;break
                        if candidate is not None:break
                    if candidate is None:break
                    mid=candidate
                    self.query(category,mid,'two-repeat interpolation within observed bracket',cohorts=(cohort,))
                    if self.passed(category,mid,cohort,True):low=mid
                    elif self.failed(category,mid,cohort):high=mid
                    # Mixed confirmations remain in the uncertainty band; they
                    # are neither silently retried nor used as a stable bound.
                require(self.passed(category,low,cohort,True) and self.failed(category,high,cohort),'Unconfirmed bracket')
                self.protocol['extended_boundaries'][category][cohort]=dict(lower=low,upper=high,
                    width=high-low,target_width=max(1,math.ceil(0.02*low)),
                    target_width_met=high-low<=max(1,math.ceil(0.02*low)),
                    unresolved_reason=None if high-low<=max(1,math.ceil(0.02*low)) else 'Interior sizes have mixed confirmations; bracket could not be narrowed without repeating observations.',
                    nonmonotonicity_caveat=True)
                self.protocol['limits'][category][2]=max(self.protocol['limits'][category][2],high)
                self.publish();print('BRACKET',category,cohort,low,high,flush=True)
            print('FAMILY COMPLETE',category,flush=True)
        self.provenance['integrity']=dict(
            sources_unchanged=all(sha(ROOT/p)==h for p,h in self.sources.items()),
            runtime_sources_unchanged=all(sha(ROOT/p)==h for p,h in self.runtime_sources.items()),
            driver_unchanged=sha(self.binary)==self.provenance['driver_sha256'],
            original_driver_unchanged=sha(self.old_binary)==self.provenance['original_driver_sha256'],
            all_current_libraries_unchanged=all(sha(Path(p))==h for p,h in self.current_libraries.items()),
            models_unchanged=all(sha(self.output/'models'/(k+'.json'))==v['json_sha256'] and
                sha(self.output/'models'/(k+'.txt'))==v['txt_sha256'] for k,v in self.models.items()),
            libraries_unchanged=all(any((d/x['name']).is_file() and sha(d/x['name'])==x['sha256']
                for d in self.directories[c]) for c in COHORTS for x in self.expected[c]['libraries']))
        require(all(self.provenance['integrity'].values()),'Final integrity failed')
        self.complete=True;self.publish();print('Uncapped continuation complete',len(self.records),'total attempts',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('report','output-dir','binary','runtime-build'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();ContinuedSearch(args.report,args.output_dir,args.binary,args.runtime_build).run()
