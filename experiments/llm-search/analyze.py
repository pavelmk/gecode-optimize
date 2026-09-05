#!/usr/bin/env python3
"""Produce CSV and Markdown from raw validated timing records, without filtering wins."""
import csv
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
RESULTS=HERE/"results"


def read(name):
    return [json.loads(line) for line in (RESULTS/(name+".jsonl")).read_text().splitlines()]


def complete(row):
    return row["status"] in ("optimal","infeasible") or (row["family"]=="coloring" and row["status"]=="feasible")


def aggregate(rows):
    groups={}
    for row in rows: groups.setdefault((row["id"],row["mode"]),[]).append(row)
    result={}
    for key,items in groups.items():
        result[key]={"id":key[0],"mode":key[1],"family":items[0]["family"],"label":items[0]["label"],
                     "runs":len(items),"completed_runs":sum(complete(r) for r in items),
                     "independently_verified_runs":sum(bool(r["validation"].get("claims_verified")) for r in items),
                     "statuses":",".join(sorted(set(r["status"] for r in items))),
                     "objectives":",".join(str(x) for x in sorted(set(r["objective"] for r in items),key=str))}
        for field in ["elapsed_ms","build_ms","nodes","propagations","process_wall_ms","peak_rss_kb"]:
            result[key]["median_"+field]=statistics.median(r[field] for r in items)
        median=result[key]["median_elapsed_ms"]
        result[key]["mad_elapsed_ms"]=statistics.median(abs(r["elapsed_ms"]-median) for r in items)
    return result


def main():
    rows=read("held-out"); demos=read("demonstrations")
    groups=aggregate(rows); demo_groups=aggregate(demos)
    all_entries=list(groups.values())+list(demo_groups.values())
    with (RESULTS/"comparison.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(all_entries[0])); writer.writeheader(); writer.writerows(all_entries)
    selection=json.loads((RESULTS/"selection.json").read_text())
    metadata=json.loads((RESULTS/"held-out.meta.json").read_text())
    evidence_path=RESULTS/"checkpoint-validation.json"
    prior_upstream=json.loads(evidence_path.read_text()).get("upstream_search",{}) if evidence_path.exists() else {}
    upstream_passed=prior_upstream.get("exit_code")==0
    if (RESULTS/"upstream-search-status.json").exists():
        upstream_passed=json.loads((RESULTS/"upstream-search-status.json").read_text()).get("exit_code")==0
    # Disabled features must reproduce stock search behavior, irrespective of noisy time.
    for (name,mode),stock in groups.items():
        if mode!="stock": continue
        disabled=groups[(name,"disabled")]
        for key in ["statuses","objectives","median_nodes","median_propagations"]:
            if stock[key]!=disabled[key]: raise AssertionError((name,key,"disabled behavior differs"))
    lines=["# Gecode source-enhancement experiment", "",
           "Two opt-in implementations were compared against unmodified Gecode 6.4.0, commit `3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e`.", "",
           "- **Propagation-count checkpoints:** sequential DFS/BAB can clone a branch state after a status call executes at least `c_p` propagators. Default 0 disables it. This measures invocations, not time. Existing adaptive recomputation remains enabled.",
           "- **Clique inference:** a new experimental posting helper discovers greedy cliques in a supplied disequality graph and adds redundant domain-consistent `distinct` constraints. It reuses Gecode's existing propagator; it does not automatically rewrite arbitrary existing C++ models.", "",
           "## Method", "",
           f"One solver thread, Release libraries and `-O3 -DNDEBUG` drivers, on `{metadata['platform']}`. There are 18 development and 18 held-out instances (six per family), plus 24 tiny correctness cases, two controls, and five separately labeled demonstrations. The development and held-out seeds are disjoint; the problem families are shared.", "",
           f"The checkpoint threshold was selected automatically from 1, 5, 10, 25, 100 on five development repetitions; selected `c_p={selection['selected_cp']}`. It was frozen before {metadata['repeats']} held-out repetitions. Within each repetition, instances and configurations were shuffled deterministically. All solver runs were serial, after compilation and correctness tests finished. The per-run limit was {metadata['limit_ms']:g} ms.", "",
           "Times include model construction, clique discovery, engine initialization, search, and engine teardown. Input parsing, process startup, and output serialization are excluded from solver time; process wall time and process peak RSS are also recorded in the CSV. Small sub-millisecond differences can be measurement noise. No LLM inference occurs during a solve.", "",
           "`stock` uses first-fail (smallest domain) branching and default copying distances. `disabled` links the modified build with both enhancements off. `checkpoint` changes only checkpointing; `cliques` changes only the coloring model; `combined` enables both applicable features. `stock-copy1` uses existing Gecode copying at every branch, and `stock-afc` uses an existing AFC/domain-size brancher. They prevent confusing a new-code gain with an already available configuration gain.", "",
           "## Held-out results", "",
           "Cells are the arithmetic mean of the six per-instance median solve times, in milliseconds. All instances are retained, including regressions.", "",
           "| Family | Stock | Modified, off | Checkpoint | Cliques | Combined | Stock copy every branch | Stock AFC |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for family in ["coloring","scheduling","vertex_cover"]:
        cells=[]
        for mode in ["stock","disabled","checkpoint","cliques","combined","stock-copy1","stock-afc"]:
            entries=[e for e in groups.values() if e["family"]==family and e["mode"]==mode]
            cells.append(f"{statistics.mean(e['median_elapsed_ms'] for e in entries):.4f}" if entries else "—")
        lines.append("| "+family+" | "+" | ".join(cells)+" |")
    completion_note=("All held-out pairs completed in this run." if all(complete(r) for r in rows)
                     else "Incomplete pairs are excluded from ratios; inspect completion counts and the raw results.")
    lines += ["", "Speed ratios below are geometric means of paired per-instance medians, using only instances completed in every repetition by both compared configurations. Above 1 means the named configuration is faster than the comparator. "+completion_note+" Ratios describe this generated sample, not unseen problem families.", "",
              "| Configuration | Versus stock | Versus stock-copy1 | Completed instance/repetition runs |",
              "|---|---:|---:|---:|"]
    for mode in ["disabled","checkpoint","cliques","combined","stock-copy1","stock-afc"]:
        entries=[e for e in groups.values() if e["mode"]==mode]
        ratios=[]
        for comparator in ["stock","stock-copy1"]:
            values=[groups[(e["id"],comparator)]["median_elapsed_ms"]/e["median_elapsed_ms"] for e in entries
                    if e["completed_runs"]==e["runs"] and groups[(e["id"],comparator)]["completed_runs"]==e["runs"]]
            ratios.append(f"{math.exp(statistics.mean(math.log(v) for v in values)):.3f}×" if values else "—")
        lines.append(f"| {mode} | {ratios[0]} | {ratios[1]} | {sum(e['completed_runs'] for e in entries)}/{sum(e['runs'] for e in entries)} |")
    lines += ["", "The checkpoint variant improved over the default copying policy in these samples, but the existing stock-copy1 configuration matched or exceeded it. This experiment therefore does not establish a new-code advantage over tuned stock Gecode. Clique inference's substantial gains are confined here to the deliberately structured demonstrations; on the small held-out coloring cases it added overhead.", "",
              "## Deliberately favorable and unfavorable examples", "",
              "The pigeonhole cases require k+1 mutually different variables to take only k values. Pairwise inequalities conceal the Hall contradiction; an inferred `distinct` sees it immediately. These are mechanism demonstrations, not a representative performance benchmark. The sparse cycle has no clique of size three and exposes preprocessing overhead.", "",
              "| Example | Stock median ms | Clique median ms | Stock median nodes | Clique median nodes | Stock completed runs |",
              "|---|---:|---:|---:|---:|---:|"]
    for name in sorted({r["id"] for r in demos}):
        s=demo_groups[(name,"stock")]; c=demo_groups[(name,"cliques")]
        timed=" (limit)" if s["completed_runs"]<s["runs"] else ""
        lines.append(f"| {name} | {s['median_elapsed_ms']:.4f}{timed} | {c['median_elapsed_ms']:.4f} | {s['median_nodes']:g} | {c['median_nodes']:g} | {s['completed_runs']}/{s['runs']} |")
    lines += ["", "A timed-out run is censored: its observed time is not a completed solve time. Any ratio using the time limit is only a lower bound on speedup. Even a huge gain on these structured contradictions does not demonstrate general superiority to stock Gecode or to an explicitly modeled `distinct`.", "",
              "## Correctness and limits", "",
              "- 180 focused configurations compare complete DFS solution sets and BAB min/max optima against independent exhaustive oracles, with enabled checkpoint thresholds and different copying distances.",
              "- 3,300 graph/color combinations compare clique strengthening with both binary Gecode models and independent enumeration. Additional checks cover Hall pruning and malformed inputs.",
              ("- Recorded evidence confirms 25,808 upstream search tests passed with default options; this broad regression suite is separate from the focused enabled-feature tests." if upstream_passed else "- No successful upstream search test evidence was recorded for this checkout."),
              "- Every returned assignment is checked against the original constraints; objectives are recomputed. All 12 medium vertex-cover optima are checked with a separate exact bitmask algorithm. Tiny cases use exhaustive enumeration; coloring contradictions use explicit clique or odd-wheel certificates; scheduling results can be certified by a matching elementary lower bound.",
              f"- Held-out independently verified result claims: {sum(bool(r['validation'].get('claims_verified')) for r in rows)}/{len(rows)}. The modified build with features disabled reproduced stock statuses, objectives, node counts, and propagation counts.",
              "- No LP engine, cutting-plane framework, or explanation-based conflict learning was added. The checkpoint option applies to sequential DFS/BAB. It changes the C++ Options ABI, so rebuild clients against matching headers/libraries. The new API remains experimental and disabled unless called.",
              "- This is a small synthetic study on one machine. It does not establish a generally faster release. More cloning can consume memory; redundant global constraints can add overhead. Raw RSS, timings, failures, and propagation counts are retained.", "",
              "## Reproduce", "", "From the repository root, with CMake, a C++17 compiler, and Python 3.12+:", "", "```sh",
              "python3 experiments/llm-search/run.py", "```", "",
              "The script builds stock from the pinned Git commit, builds the modified version, generates data, checks correctness, selects a threshold on development instances, and then benchmarks held-out inputs. It writes all raw results, selection evidence, CSV, and this report under `experiments/llm-search/results/`.", ""]
    (RESULTS/"REPORT.md").write_text("\n".join(lines))
    print("Wrote results/REPORT.md and results/comparison.csv")


if __name__=="__main__": main()
