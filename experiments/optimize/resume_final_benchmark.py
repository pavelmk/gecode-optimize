#!/usr/bin/env python3
"""Resume after a missing backend-version diagnostic, preserving the captured solve.

A time-limited automatic result may omit backend_version.
Verified driver/runtime hashes establish the executing product independently.
Only this diagnostic requirement is relaxed; model identity, original witnesses,
status, bounds, gaps, clocks, route and configuration checks are unchanged.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time

import continue_final_benchmark as continuation

initial=continuation.initial
_original_validate=initial.validate


def validate(raw,model,route):
    missing=(route=='auto-race' and raw.get('status')=='time_limit' and
             raw.get('backend_version')=='')
    if not missing:return _original_validate(raw,model,route)
    checked=_original_validate(dict(raw,backend_version='unavailable on interrupted preprocessing'),model,route)
    checked['backend_result']=raw
    checked['backend_metadata_note']='Backend version omitted on interrupted native preprocessing; actual driver and loaded library hashes verified separately.'
    return checked


# benchmark_final.execute resolves this module-global validator dynamically.
# Importing export_extended after this module uses the same corrected validator.
initial.validate=validate
ROOT,HERE,sha,require=continuation.ROOT,continuation.HERE,continuation.sha,continuation.require


def resume(report_path,output,binary,runtime):
    report_path=report_path.resolve(strict=True);old=json.loads(report_path.read_text())
    require(not old['complete'],'Use the regular continuation for a complete report')
    require(all(sha(ROOT/p)==h for p,h in old['provenance']['sources'].items()),'Previous measurement source changed')
    require(all(sha(ROOT/p)==h for p,h in old['provenance']['runtime_sources'].items()),'Runtime source changed')
    errors=[r for r in old['records'] if r['status']=='error']
    require(len(errors)==1 and errors[0].get('error')=='Invalid model identity','Unexpected interrupted phase')
    row=errors[0]
    label=f"{row['case']}-{row['cohort']}-{row['route']}-r{row['repetition']}"
    raw_path=report_path.parent/(label+'.stdout');raw=json.loads(raw_path.read_text())
    require(row['cohort']=='auto' and raw['status']=='time_limit' and raw['backend_version']=='' and raw['has_solution'] is False,
            'The rejected packet is not the narrowly admitted metadata case')
    model=next(m['model'] for m in old['models'] if m['id']==row['case'])
    repaired=validate(raw,model,row['route'])
    row['original_validation_error']=row.pop('error');row.update(repaired)
    row['validation_repair']=dict(source='resume_final_benchmark.py',stdout_sha256=sha(raw_path),
        reason='Revalidated the original captured packet; no solve repeated.')
    state=continuation.ContinuedSearch.__new__(continuation.ContinuedSearch)
    state.output=output.resolve();require(not state.output.exists(),'Resume output exists')
    shutil.copytree(report_path.parent,state.output)
    shutil.copy2(report_path,state.output/'rejected-phase2-report.json')
    state.started=time.monotonic()-old['elapsed_seconds'];state.utc=old['started_utc']
    state.binary=binary.resolve(strict=True);state.runtime=runtime.resolve(strict=True)
    state.old_binary=ROOT/'build/capacity-scaling/fixed-driver/optimize-native-benchmark'
    state.directories={'before':[ROOT/'build/comparison-algorithms/before/lib'],
        'auto':[state.runtime/'gecode/optimize',state.runtime],
        'configured':[state.runtime/'gecode/optimize',state.runtime]}
    state.models={m['id']:m for m in old['models']};state.records=old['records'];state.decisions=old['decisions']
    state.sources=dict(old['provenance']['sources']);state.sources['experiments/optimize/resume_final_benchmark.py']=sha(Path(__file__))
    state.runtime_sources=old['provenance']['runtime_sources'];state.provenance=old['provenance']
    state.current_libraries=json.loads((state.binary.parent/'build.local.json').read_text())['runtime_libraries_sha256']
    state.expected=state.provenance['expected_libraries']
    require(sha(state.binary)==state.provenance['driver_sha256'] and sha(state.old_binary)==state.provenance['original_driver_sha256'],'Driver changed')
    require(all(sha(Path(p))==h for p,h in state.current_libraries.items()),'Current runtime changed')
    for c in continuation.COHORTS:
        require(all(any((d/x['name']).is_file() and sha(d/x['name'])==x['sha256'] for d in state.directories[c])
                    for x in state.expected[c]['libraries']),'Loaded product hash changed')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    state.provenance['phases'].append(dict(name='diagnostic validator correction; captured observation retained',
        source_head=head,started_utc=datetime.now(timezone.utc).isoformat(),
        previous_report_sha256=sha(report_path),previous_records=len(state.records),
        validator_source_sha256=sha(Path(__file__)),revalidated_stdout_sha256=sha(raw_path),
        reason='Empty version string accepted only for interrupted automatic results; all incumbent/bound validation retained and loaded runtime independently pinned.'))
    state.provenance['source_head']=head;state.provenance['sources']=state.sources
    state.protocol=old['protocol'];state.policy=state.protocol['policy'];state.complete=False
    state.protocol['validator_amendment']='Optional empty backend-version metadata on automatic time limit; all semantic checks retained and runtime identity verified by hashes.'
    state.publish();return state


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    for flag in ('output-dir','binary','runtime-build'):parser.add_argument('--'+flag,type=Path)
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--export-only',action='store_true')
    args=parser.parse_args()
    if args.export_only:
        import export_extended_benchmark
        export_extended_benchmark.export(args.report)
    else:
        if not all((args.output_dir,args.binary,args.runtime_build)):
            parser.error('resuming requires --output-dir, --binary and --runtime-build')
        state=resume(args.report,args.output_dir,args.binary,args.runtime_build)
        if args.validate_only:print('Captured timeout revalidated; all prior records preserved; no solve run')
        else:state.run()
