#!/usr/bin/env python3
"""Resume after a TXT transport guard, using a driver with wider parser guards.

The rejected invocation never entered solve. Archive it as a harness attempt,
then run that model once with the expanded driver and identical solver libraries.
All earlier solve observations and their original driver identity remain recorded.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time

import resume_final_benchmark as metadata

continuation=metadata.continuation
ROOT,HERE,sha,require=metadata.ROOT,metadata.HERE,metadata.sha,metadata.require


def resume(report_path,output,binary,runtime):
    report_path=report_path.resolve(strict=True);old=json.loads(report_path.read_text())
    require(not old['complete'],'Use the regular continuation for completed input')
    require(all(sha(ROOT/p)==h for p,h in old['provenance']['sources'].items()),'Old measurement source changed')
    require(all(sha(ROOT/p)==h for p,h in old['provenance']['runtime_sources'].items()),'Solver source changed')
    errors=[r for r in old['records'] if r['status']=='error']
    require(len(errors)==1 and errors[0]['returncode']==2 and
        errors[0]['stdout_bytes_observed']==0 and 'Invalid/out-of-range TXT integer' in errors[0]['error'],
        'Unexpected failure; cannot treat as a pre-solve parser rejection')
    rejected=errors[0];label=f"{rejected['case']}-{rejected['cohort']}-{rejected['route']}-r{rejected['repetition']}"
    state=continuation.ContinuedSearch.__new__(continuation.ContinuedSearch)
    state.output=output.resolve();require(not state.output.exists(),'Resume output exists')
    shutil.copytree(report_path.parent,state.output)
    shutil.copy2(report_path,state.output/'parser-rejected-phase3-report.json')
    archive=state.output/'harness-attempts';archive.mkdir(exist_ok=True)
    event=dict(rejected,classification='driver parser guard; solver not entered',counted_as_solver_failure=False)
    for suffix in ('stdout','stderr'):
        original=state.output/(label+'.'+suffix);destination=archive/(label+'.'+suffix)
        original.rename(destination)
        event[suffix+'_file']=str(destination.relative_to(state.output));event[suffix+'_sha256']=sha(destination)
    state.started=time.monotonic()-old['elapsed_seconds'];state.utc=old['started_utc']
    state.binary=binary.resolve(strict=True);state.runtime=runtime.resolve(strict=True)
    state.old_binary=ROOT/'build/capacity-scaling/fixed-driver/optimize-native-benchmark'
    state.directories={'before':[ROOT/'build/comparison-algorithms/before/lib'],
        'auto':[state.runtime/'gecode/optimize',state.runtime],
        'configured':[state.runtime/'gecode/optimize',state.runtime]}
    state.models={m['id']:m for m in old['models']}
    state.records=[r for r in old['records'] if r is not rejected];state.decisions=old['decisions']
    state.sources=dict(old['provenance']['sources'])
    build_path=state.binary.parent/'build.local.json';build=json.loads(build_path.read_text())
    require(build['binary_sha256']==sha(state.binary) and build['runtime_libraries_unchanged'],'Large driver build mismatch')
    for p in (Path(__file__),HERE/'build_large_final_benchmark.py',build_path,Path(build['source'])):
        state.sources[str(p.resolve().relative_to(ROOT))]=sha(p)
    state.runtime_sources=old['provenance']['runtime_sources'];state.provenance=old['provenance']
    state.current_libraries=build['runtime_libraries_sha256'];state.expected=state.provenance['expected_libraries']
    require(sha(state.old_binary)==state.provenance['original_driver_sha256'],'Original driver changed')
    require(all(sha(Path(p))==h for p,h in state.current_libraries.items()),'Current runtime changed')
    require({str(Path(p).relative_to(ROOT)):h for p,h in state.current_libraries.items()}==state.provenance['current_runtime_libraries_sha256'],
            'Expanded driver was linked to a different solver product')
    for c in continuation.COHORTS:
        require(all(any((d/x['name']).is_file() and sha(d/x['name'])==x['sha256'] for d in state.directories[c])
                    for x in state.expected[c]['libraries']),'Previously loaded product changed')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    state.provenance['phases'].append(dict(name='expanded transport parser; solver unchanged',source_head=head,
        started_utc=datetime.now(timezone.utc).isoformat(),previous_report_sha256=sha(report_path),
        previous_driver_sha256=state.provenance['driver_sha256'],driver_sha256=sha(state.binary),
        first_new_solve_record=len(state.records),parser_build_manifest_sha256=sha(build_path),
        reason='Assignment128 exceeded the old 10000-variable TXT guard before solve. Guard-only driver rebuild; identical input encoding and solver libraries. Earlier clocks surround solve and exclude model parsing.'))
    state.provenance['driver_sha256']=sha(state.binary)
    state.provenance['source_head']=head;state.provenance['sources']=state.sources
    state.protocol=old['protocol'];state.policy=state.protocol['policy'];state.complete=False
    state.protocol.setdefault('harness_attempts',[]).append(event)
    state.protocol['transport_amendment']='A pre-solve parser rejection is archived separately, never treated as solver capacity. Larger parser guards do not alter solving or timing boundaries.'
    state.publish();return state


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    for flag in ('output-dir','binary','runtime-build'):parser.add_argument('--'+flag,type=Path)
    parser.add_argument('--validate-only',action='store_true');parser.add_argument('--export-only',action='store_true')
    args=parser.parse_args()
    if args.export_only:
        import export_extended_benchmark
        export_extended_benchmark.export(args.report)
    else:
        if not all((args.output_dir,args.binary,args.runtime_build)):parser.error('resume needs output-dir,binary,runtime-build')
        state=resume(args.report,args.output_dir,args.binary,args.runtime_build)
        if args.validate_only:print('Parser attempt archived separately; previous solves preserved; no solve run')
        else:state.run()
