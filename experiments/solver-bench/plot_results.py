#!/usr/bin/env python3
"""Publication figures from audited leaderboard JSON; never reads solver logs.

Requires matplotlib. Creates SVG/PDF/PNG with no external assets or services.
Run only outside benchmark timing windows. Each incompatible cohort receives
separate figures; no timeout is silently omitted from completion/score plots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

BASE_COLOR='#63758a'
CANDIDATE_COLOR='#245bce'
OTHER_COLOR='#abc3db'
CENSOR_COLOR='#b66b18'
INK='#17283c'
MUTED='#526479'


def label(value):return str(value).replace('_',' ')
def short(value):return f'{value:,.3f}'.rstrip('0').rstrip('.') if value<10 else f'{value:,.1f}'.rstrip('0').rstrip('.')


def configure_matplotlib():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':INK,
      'axes.labelcolor':MUTED,'xtick.color':MUTED,'ytick.color':INK,'axes.edgecolor':'#bac5d1',
      'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold',
      'axes.titlesize':13,'axes.labelsize':10,'figure.facecolor':'white','axes.facecolor':'white',
      'savefig.facecolor':'white','grid.color':'#e1e7ee','grid.linewidth':.6,
      'svg.fonttype':'none','pdf.fonttype':42,'ps.fonttype':42})
    return plt


def footnote(fig,text):
    fig.text(.02,.012,text,ha='left',va='bottom',fontsize=8,color=MUTED,linespacing=1.5)


def protocol_caption(cohort):
    p=cohort['protocol']
    return (f"{cohort['instance_count']} instances · {short(p['limit_ms'])} ms budget · "
            f"{'/'.join(map(str,cohort['repetitions']))} repetitions · splits {', '.join(cohort['splits'])}\n"
            + ('Shared supplied incumbents where available.' if p['warm'] else 'No supplied warm start.'))


def save_figure(fig,stem,formats,dpi,plt):
    paths=[]
    for extension in formats:
        path=stem.with_suffix('.'+extension)
        fig.savefig(path,dpi=dpi,bbox_inches='tight',pad_inches=.16)
        paths.append(path.name)
    plt.close(fig)
    return paths


def completion_figure(plt,cohort,baseline,candidate):
    from matplotlib.ticker import MaxNLocator
    entries=cohort['overall'];count=len(entries)
    fig,ax=plt.subplots(figsize=(8.8,max(3.6,.52*count+1.7)))
    positions=list(range(count));maximum=max(row['instances'] for row in entries)
    colors=[BASE_COLOR if row['config']==baseline else CANDIDATE_COLOR if row['config']==candidate else OTHER_COLOR for row in entries]
    ax.barh(positions,[row['instances'] for row in entries],color='#edf1f6',height=.65,zorder=1)
    ax.barh(positions,[row['completed_instances'] for row in entries],color=colors,height=.65,zorder=2)
    for y,row in zip(positions,entries):
        ax.text(maximum*1.02,y,f"{row['completed_instances']} / {row['instances']}",va='center',fontsize=10)
    ax.set_yticks(positions,labels=[row['config'] for row in entries]);ax.invert_yaxis()
    ax.set_xlim(0,maximum*1.17 if maximum else 1);ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel('Instances proved within budget in every repetition');ax.set_title('Proof completion under a fixed budget',loc='left',pad=16)
    ax.grid(axis='x',zorder=0);ax.set_axisbelow(True)
    footnote(fig,protocol_caption(cohort)+'\nBackground bars retain every instance, including timeouts. Ranking: completion count, then capped SGM score.')
    fig.tight_layout(rect=(0,.14,1,1))
    return fig


def score_figure(plt,cohort,baseline,candidate,score):
    entries=cohort['overall'];count=len(entries)
    if score=='sgm':
        key='shifted_geometric_mean_capped_ms';title='Capped shifted-geometric-mean score';xlabel='Score in milliseconds · 10 ms shift · lower is better'
        explanation='Incomplete runs contribute their cutoff. Median per instance; shifted geometric mean across instances.'
    else:
        key='mean_median_par2_score_ms';title='PAR2 timeout-penalty score';xlabel='Penalty score in milliseconds · lower is better'
        explanation='Incomplete runs cost twice the cutoff. Median per instance; arithmetic mean across instances.'
    values=[row[key] for row in entries]
    if any(value is None or not math.isfinite(value) or value<0 for value in values):
        raise ValueError('Cannot plot missing/invalid aggregate scores')
    fig,ax=plt.subplots(figsize=(8.8,max(3.6,.52*count+1.7)))
    positions=list(range(count));colors=[BASE_COLOR if row['config']==baseline else CANDIDATE_COLOR if row['config']==candidate else OTHER_COLOR for row in entries]
    ax.barh(positions,values,color=colors,height=.65);ax.set_yticks(positions,labels=[row['config'] for row in entries]);ax.invert_yaxis()
    maximum=max(values) or 1
    for y,value in zip(positions,values):ax.text(value+maximum*.018,y,short(value),va='center',fontsize=10)
    ax.set_xlim(0,maximum*1.18);ax.set_xlabel(xlabel);ax.set_title(title,loc='left',pad=16)
    ax.grid(axis='x');ax.set_axisbelow(True)
    footnote(fig,protocol_caption(cohort)+'\n'+explanation+'\nThis score is not an estimate of unobserved completion times; every timeout remains included.')
    fig.tight_layout(rect=(0,.18,1,1))
    return fig


def family_figure(plt,cohort,baseline,candidate):
    from matplotlib.ticker import MaxNLocator
    families=sorted(cohort['families']);height=max(4.8,.4*len(families)+2.0)
    fig,ax=plt.subplots(figsize=(10,height))
    maximum=max(1,max(row['instances'] for values in cohort['families'].values() for row in values))
    for index,family in enumerate(families):
        mapping={row['config']:row for row in cohort['families'][family]}
        for offset,config,color in [(-.17,baseline,BASE_COLOR),(.17,candidate,CANDIDATE_COLOR)]:
            row=mapping[config];maximum=max(maximum,row['instances'])
            ax.barh(index+offset,row['instances'],height=.29,color='#edf1f6',zorder=1)
            ax.barh(index+offset,row['completed_instances'],height=.29,color=color,zorder=2,
                    label=config if index==0 else None)
        before,after=mapping[baseline],mapping[candidate]
        ax.text(maximum+.2,index,f"{before['completed_instances']} / {after['completed_instances']}  of {before['instances']}",
                va='center',fontsize=8.5,color=MUTED)
    ax.set_yticks(range(len(families)),labels=[label(family) for family in families]);ax.invert_yaxis()
    ax.set_xlim(0,maximum+max(2.5,maximum*.32));ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel('Instances proved within budget in every repetition');ax.set_title('Completion by problem representation',loc='left',pad=34)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.005),frameon=False,ncol=2,fontsize=9)
    ax.grid(axis='x');ax.set_axisbelow(True)
    footnote(fig,protocol_caption(cohort)+'\nRight labels: baseline / comparison completed, of total. Representation names are not distinct complexity classes.\nZero-to-positive counts concern this sample and budget, not a mathematical change in solvability.')
    fig.tight_layout(rect=(0,.09,1,1));fig.subplots_adjust(left=.29)
    return fig


def scatter_figure(plt,report,cohort,baseline,candidate):
    from matplotlib.lines import Line2D
    rows=[row for row in report['instances'] if row['cohort']==cohort['id']]
    index={(row['id'],row['config']):row for row in rows};identities=sorted({row['id'] for row in rows})
    limit=cohort['protocol']['limit_ms'];groups={'complete':[],'baseline_censored':[],'candidate_censored':[],'both_censored':[]}
    positive=[]
    for identity in identities:
        before,after=index[identity,baseline],index[identity,candidate]
        b_ok,a_ok=before['completed_all_runs'],after['completed_all_runs']
        b=before['median_completed_time_ms'] if b_ok else limit
        a=after['median_completed_time_ms'] if a_ok else limit
        if b<=0 or a<=0:raise ValueError('Log scatter requires positive measured times')
        positive.extend([b,a]);kind='complete' if b_ok and a_ok else 'both_censored' if not b_ok and not a_ok else 'baseline_censored' if not b_ok else 'candidate_censored'
        groups[kind].append((b,a))
    lower=10**math.floor(math.log10(min(positive))) if positive else .01;upper=limit*1.55
    fig,ax=plt.subplots(figsize=(7.8,7.7));ax.set_xscale('log');ax.set_yscale('log')
    ax.set_xlim(lower,upper);ax.set_ylim(lower,upper);ax.set_aspect('equal',adjustable='box')
    ax.plot([lower,upper],[lower,upper],color='#9aa9b9',linewidth=1,linestyle='--',zorder=1)
    ax.axvline(limit,color='#bc8c55',linestyle=':',linewidth=1);ax.axhline(limit,color='#bc8c55',linestyle=':',linewidth=1)
    styles={'complete':('o',CANDIDATE_COLOR,'Both complete'),
            'baseline_censored':('>',CENSOR_COLOR,'Baseline not complete in all runs'),
            'candidate_censored':('^','#a7425f','Comparison not complete in all runs'),
            'both_censored':('X','#626b75','Neither complete in all runs')}
    handles=[]
    for kind,(marker,color,text) in styles.items():
        points=groups[kind]
        if points:ax.scatter([x for x,y in points],[y for x,y in points],s=29 if kind=='complete' else 52,
                             marker=marker,color=color,alpha=.66,linewidths=.6,edgecolors='white',zorder=3)
        handles.append(Line2D([0],[0],marker=marker,color='none',markerfacecolor=color,markersize=6,label=f'{text}: {len(points)}'))
    ax.set_xlabel(f'{baseline}: median proof time when all runs complete (ms)')
    ax.set_ylabel(f'{candidate}: median proof time when all runs complete (ms)')
    ax.set_title('Paired instance outcomes with deadline markers',loc='left',pad=15)
    ax.grid(which='major');ax.text(.04,.96,'Above diagonal: comparison slower\nBelow diagonal: comparison faster\n(for both-completed circles)',
                                transform=ax.transAxes,ha='left',va='top',fontsize=8,color=MUTED)
    fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.1,.065),frameon=False,ncol=2,fontsize=8)
    footnote(fig,'Only circles contain two observed completion medians. A non-complete side is placed at the cutoff as a status marker,\nnot an estimate or bound on its median completion time; partial-repetition completion is included in this category.\nMarkers can overlap. Counts above and the full instance CSV retain all cases. '+str(limit)+' ms budget.')
    fig.tight_layout(rect=(0,.15,1,1))
    return fig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True,help='audited leaderboard.json')
    parser.add_argument('--out-dir',type=Path)
    parser.add_argument('--cohort',default=None)
    parser.add_argument('--baseline',default=None)
    parser.add_argument('--candidate',default='portfolio')
    parser.add_argument('--formats',default='svg,pdf,png')
    parser.add_argument('--score',choices=['sgm','par2'],default='sgm')
    parser.add_argument('--no-scatter',action='store_true')
    parser.add_argument('--allow-exploratory',action='store_true')
    parser.add_argument('--dpi',type=int,default=180)
    args=parser.parse_args();report=json.loads(args.report.read_text())
    if report.get('schema_version')!=1:parser.error('Unsupported audited report schema')
    if report.get('exploratory') and not args.allow_exploratory:parser.error('Development plotting requires --allow-exploratory')
    formats=args.formats.split(',')
    if not formats or len(formats)!=len(set(formats)) or not set(formats)<={'svg','pdf','png'}:parser.error('Choose unique formats from svg,pdf,png')
    if not 40<=args.dpi<=600:parser.error('DPI must be40..600')
    cohorts=[cohort for cohort in report['cohorts'] if not args.cohort or cohort['id']==args.cohort]
    if not cohorts:parser.error('No matching cohort')
    baseline=args.baseline or report['baseline'];out=args.out_dir or args.report.parent/'figures'
    for cohort in cohorts:
        if cohort.get('incomplete') or any(row.get('missing_runs',0) for row in cohort['overall']):parser.error('Refusing incomplete-batch publication figures')
        configs={row['config'] for row in cohort['overall']}
        if not {baseline,args.candidate}<=configs:parser.error('Baseline/candidate absent from '+cohort['id'])
        if baseline==args.candidate:parser.error('Choose a comparison different from baseline')
    plt=configure_matplotlib();out.mkdir(parents=True,exist_ok=True);written=[]
    for cohort in cohorts:
        prefix=re.sub(r'[^A-Za-z0-9_.-]','_',cohort['id'])
        figures=[('completion',completion_figure(plt,cohort,baseline,args.candidate)),
                 (args.score+'-score',score_figure(plt,cohort,baseline,args.candidate,args.score)),
                 ('family-completion',family_figure(plt,cohort,baseline,args.candidate))]
        if not args.no_scatter:figures.append(('paired-outcomes',scatter_figure(plt,report,cohort,baseline,args.candidate)))
        for name,figure in figures:
            written.extend(save_figure(figure,out/(prefix+'-'+name),formats,args.dpi,plt))
    manifest={'report_file':str(args.report),'report_sha256':hashlib.sha256(args.report.read_bytes()).hexdigest(),
              'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'baseline':baseline,'candidate':args.candidate,'score':args.score,'formats':formats,
              'cohorts':[cohort['id'] for cohort in cohorts],'exploratory':report.get('exploratory',False),'files':written,
              'notes':['No incompatible cohorts pooled.','Completion requires every repetition within budget.',
                       'Capped SGM/PAR2 are scores, not imputed completion times.',
                       'Non-complete scatter coordinates at the cutoff are status markers, not observed medians or lower bounds.']}
    (out/'figures-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'out_dir':str(out),'figures':len(written),'cohorts':len(cohorts)},sort_keys=True))


if __name__=='__main__':main()
