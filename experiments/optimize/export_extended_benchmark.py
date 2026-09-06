#!/usr/bin/env python3
"""Validate and publish the continued three-cohort study with actual failed uppers."""
import argparse
import json
from pathlib import Path
import re

import continue_final_benchmark as continued
import export_final_benchmark as base


def export(path):
    path=path.resolve(strict=True)
    base.export(path)
    report=json.loads(path.read_text())
    projection=json.loads((path.parent/'projection.json').read_text())
    brackets=report['protocol']['extended_boundaries']
    race={'skipped':0,'one_probe':0,'two_probes':0,'selected_automatic':0,'selected_ordinary':0,'other':0}
    for row in report['records']:
        if row['probe'] or row['cohort']!='auto':continue
        message=row['backend_result']['message']
        if 'Native race skipped' in message:race['skipped']+=1;continue
        found=re.search(r'Native sequential race: (\d+) probes; selected ([^;]+);',message)
        if not found:race['other']+=1;continue
        probes=int(found[1]);race['one_probe' if probes==1 else 'two_probes' if probes==2 else 'other']+=1
        selected=found[2].replace('ordinary native','ordinary')
        if selected in ('automatic','ordinary'):race['selected_'+selected]+=1
    projection['race_activity']=race
    for family in projection['families']:
        family['capacity_note']='Largest confirmed sampled pass with a separately observed failed upper input. No study size ceiling; nonmonotonic instances remain possible.'
        for cohort in continued.COHORTS:
            bracket=brackets[family['id']][cohort]
            continued.require(bracket['width']==bracket['upper']-bracket['lower'] and bracket['upper']>bracket['lower'], 'Invalid observed bracket')
            continued.require(bracket['target_width_met']==(bracket['width']<=bracket['target_width']), 'Incorrect convergence flag')
            continued.require(bracket['target_width_met'] or bool(bracket['unresolved_reason']), 'Unexplained broad bracket')
            upper_rows=[r for r in report['records'] if not r['probe'] and r['category']==family['id'] and r['cohort']==cohort and r['size']==bracket['upper']]
            variants=('uncorrelated','correlated') if family['id']=='knapsack' else ('single',)
            continued.require({(r['variant'],r['repetition']) for r in upper_rows}=={(v,n) for v in variants for n in (1,2)}, 'Incomplete failed upper')
            continued.require(all(any(not r['passed'] for r in upper_rows if r['repetition']==n) for n in (1,2)), 'Upper did not fail both repetitions')
            boundary=family[cohort+'_boundary']
            continued.require(boundary['confirmed_size']==bracket['lower'],'Projection lower differs')
            boundary.update(censored=False,next_failure_size=bracket['upper'],
                failed_upper_size=bracket['upper'],bracket_width=bracket['width'],
                target_width_met=bracket['target_width_met'],unresolved_reason=bracket['unresolved_reason'],
                next=f"Confirmed failed upper: {bracket['upper']}; sampled bracket width {bracket['width']}.")
    projection['unresolved_brackets']=[dict(category=f,cohort=c,**b) for f,groups in brackets.items() for c,b in groups.items() if not b['target_width_met']]
    projection['protocol_amendment']='After bounded discovery started, the user requested observed failed upper inputs. All initial measurements were retained and each cohort was extended without a study size ceiling.'
    full=json.dumps(dict(projection=projection,report=report),indent=2,allow_nan=False)+'\n'
    (path.parent/'projection.json').write_text(json.dumps(projection,indent=2,allow_nan=False)+'\n')
    for name in ('public.json','gecode-final.json'):(path.parent/name).write_text(full)
    lines=['# Final native algorithm comparison','',
        'All three cohorts use the same deterministic original models, one thread, and ten seconds per owning solve. The automatic clock includes every sequential racing probe and selected restart. Measured processes ran serially.', '',
        'Original Gecode is the preserved optimization-facade baseline before the algorithm changes, not a pristine upstream release. Auto + race combines exact structural preprocessing, compact DP, checked LP/branching selection, and opt-in sequential exploration. Configured uses the frozen family presets; no strategy was changed in response to this final study.', '',
        '| Problem | Original solved / failed upper | Auto + race solved / failed upper | Configured solved / failed upper |',
        '|---|---:|---:|---:|']
    for family in projection['families']:
        cells=[]
        for cohort in continued.COHORTS:
            b=family[cohort+'_boundary'];cells.append(f"{b['label']} / {b['failed_upper_size']}")
        lines.append('| '+family['name']+' | '+' | '.join(cells)+' |')
    lines += ['',f"{projection['runs']} measured attempts plus three runtime-loader probes; cumulative active study wall time {report['elapsed_seconds']:.2f} seconds (preparation between phases excluded).",'',
        'The user removed the initial study ceilings after discovery had started. The original phase is preserved by hash, and every prior observation was retained. Each cohort was extended until a failed upper input was observed in both repetitions. Bisection narrows large brackets to approximately 2% of the solved lower size (one-unit brackets for small sizes). Any unresolved wider bracket caused by mixed confirmations is explicitly flagged in the export. No harness cap is reported as solver failure.', '',
        'Bars show the largest sampled size passing both repetitions and every variant. The table also reports the observed failed upper. Seeded-instance difficulty need not be monotonic: reversals and mixed confirmations remain in the raw report, so these are sampled brackets, not mathematical maximum-size guarantees.', '',
        'Every returned original witness was independently checked. Exact optimal status is backend-reported; no independent optimum oracle is claimed. The same seeded families informed the earlier frozen configured policy, so this is not a holdout study.', '',
        f"Automatic diagnostics across measured attempts: {race['skipped']} races skipped for direct-path compatibility; {race['one_probe']} one-probe results; {race['two_probes']} two-probe results; {race['selected_automatic']} selected automatic; {race['selected_ordinary']} selected ordinary. Counts are parsed from the saved solver diagnostics, and runtime probes are excluded.", '',
        'This comparison measures combined policies, not an ablation. A first automatic probe that proves optimality does not establish a benefit from racing; the gains may come from DP, preprocessing, LP bounds or branching. A separate ablation would be required to isolate individual contributions.', '',
        'Racing may increase total CPU burden or solve time because exploration and restarting repeat work. Several seconds or longer can still be worthwhile when exploration identifies a much more effective strategy for the remaining solve. Early progress is a heuristic, not a promise of future speedup.', '',
        'The public JSON retains every initial and extension probe/attempt, wall time, objective, bound, original witness, frozen model hash, policy, source hash, phase amendment, and verified loader identity.', '',
        'Original source: '+report['provenance']['original_source_head'],
        'Current source / extension runner: '+report['provenance']['source_head'],
        'Report SHA256: '+continued.sha(path), '']
    (path.parent/'FINAL-BENCHMARK.md').write_text('\n'.join(lines))
    print(json.dumps({'race_activity':race,'runs':projection['runs'],'sha256':continued.sha(path)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report',type=Path)
    export(parser.parse_args().report)
