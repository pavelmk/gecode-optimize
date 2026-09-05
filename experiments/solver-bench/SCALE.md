# Separate evaluation of larger, unseen sizes

`scale-manifest.json` freezes **90 binary-linear cases: 18 existing template families × five fresh seeds**. Their split is `scale` and tier is `xlarge`. This is a separate size-shift evaluation track; it does not replace or enlarge the core held-out headline denominator. No solver results, learned-policy decisions, or timing measurements were read to choose these instances.

`generate_scale.py` reuses the exact code object of `generator.make_model`, with an isolated replacement for its dimension lookup. It invokes the model with the original `large` tier so coefficient distributions, graph densities and other non-dimensional choices remain unchanged. It does not modify the original generator. Existing incumbent procedures and independent domain/schema validators are reused. The source generator, validator, base manifest, scale generator and available frozen policy/header hashes are recorded; source and policy hashes are checked again after generation.

The mechanical rule doubles the primary entity count. Counts that preserve a sets/items or vertices/edges ratio grow together. Quadratic assignment and TSP representations instead use `ceil(sqrt(2) × size)` to obtain approximately twice the binary columns. Other dimensions stay at their original large-tier values.

| Family | Fixed size change | Original large → scale binary columns |
|---|---|---:|
| Set cover | Sets 100→200; elements 30→60 | 100→200 |
| Multicover | Sets 90→180; elements 28→56; demand stays 3 | 90→180 |
| Set packing | Bundles 100→200; items 50→100 | 100→200 |
| Knapsack | Items 80→160; one resource | 80→160 |
| Multidimensional knapsack | Items 80→160; five resources | 80→160 |
| Vertex cover | Vertices 100→200; original edge probability | 100→200 |
| Independent set | Vertices 100→200; original edge probability | 100→200 |
| Maxcut | Vertices 24→48; target edges 90→180 | 114→228 |
| Facility location | Customers 15→30; eight facilities | 128→248 |
| P-median | Customers 15→30; eight facilities; p stays 3 | 128→248 |
| Assignment | Square assignment size 12→17 | 144→289 |
| Generalized assignment | Jobs 28→56; five machines | 140→280 |
| Bin packing | Items 20→40; six possible bins | 126→246 |
| Coloring | Vertices 20→40; six possible colors | 126→246 |
| TSP | Cities 8→12 | 120→276 |
| Auction | Bids 120→240; items 35→70 | 120→240 |
| Rostering | Days 6→12; eight employees; three shifts | 144→288 |
| Production | Periods 6→12; 20 quantity options | 120→240 |

The fixed cap was 1,000 binary columns and 10,000 rows per case. **No cases or families were omitted**; actual maxima are 289 columns and 1,681 rows. The seed rule is `30_000_000 + family_index*100_000 + replication`, with replications 0–4 and the original ordered family list. All 90 seeds were checked against the existing manifests. There is no resampling on difficulty or solver success.

Every instance has a checked feasible incumbent. The sparse inequalities, binary assignment and original domain meaning are validated, and the serialized TXT is independently parsed back and compared with JSON. All reference optima are explicitly **unknown**: no exact solver or oracle ran during this generation. Generation and incumbent times remain separately recorded; the delivered generation took approximately 0.82 seconds on this host.

This tests extrapolation to larger instances from known templates. It does not test unseen problem families, arbitrary instance distributions, industrial scale, or every formulation of these domains. Fixed secondary dimensions are material: facilities, machine/bin/color counts, and resource counts do not all increase. Stronger or weaker observed performance must be retained rather than used to revise these rules.

Run this as its own evaluation and report, using the same frozen policy, budget, repetitions and warm-start rules as the chosen comparison:

```sh
python3 bench.py --manifest scale-manifest.json --split scale --configs stock,disabled,lp,portfolio --repeats 3 --limit-ms 2000 --output results/scale.jsonl
python3 analyze.py --runs results/scale.jsonl --split scale --out-dir reports/scale
```

The exact command and configuration set should follow the final frozen protocol; this example is not an executed benchmark. The analyzer excludes `scale` by default, preventing accidental inclusion in a `test,public` report. Preserve the separate report rather than pooling this track into the core result.

Reproduction writes to a new directory; the generator refuses to overwrite an existing scale manifest:

```sh
python3 generate_scale.py --out-dir alternate-scale
```
