# Paired formulations of identical semantic instances

`paired-manifest.json` freezes **20 semantic optimization problems and 40 encodings**: TSP and graph coloring, two sizes, five fresh seeds for each family/size, with one binary-linear and one native CP encoding of every problem. The split is `formulation`. This is a separate formulation-comparison track; the 40 encodings are not 40 independent semantic instances and do not increase the main family or held-out counts.

Every pair has a shared `paired_problem_id`, a `_semantic.json` file and a canonical `semantic_input_sha256`. Each encoding also retains its own mathematical/input-file hashes. The same feasible semantic assignment is converted into each representation, and independent validators verify equal objective values. No solver timings or optimum oracle influenced construction; all exact references remain explicitly unknown.

| Family | Small / large semantic size | Binary representation | Native representation |
|---|---|---|---|
| TSP | 5 / 8 cities | 45 / 120 Boolean city-position and directed-arc decisions | 5 / 8 integer successor decisions with a global `circuit` constraint |
| Coloring | 8 / 20 vertices | 72 / 420 Boolean vertex-color and enabled-color decisions | 8 / 20 integer color decisions with pairwise disequalities and a maximum objective |

TSP encodings use exactly the same complete distance matrix and minimize the sum of directed tour edges. The binary encoding fixes city0 at tour position0; the successor encoding represents the same cycle without a rotational duplication. Conversion maps the ordered tour to one successor per city. A nearest-neighbor tour supplies the common incumbent.

Coloring encodings use exactly the same graph and permit up to `|V|` colors. Labels are canonicalized in order of first appearance, matching the native driver's existing symmetry restriction. For the paired binary model, valid symmetry constraints enforce the same first-use rule; additional constraints make an enabled color equivalent to a used color. Thus the binary sum of enabled colors equals the native `max(color)+1` objective on every canonical coloring. These additions affect only the new paired binary inputs, not the core suite.

The graph builder reuses the original generator with its color capacity increased to the vertex count. Vertex counts and edge-density rules retain the original small/large settings. The TSP builder is reused unchanged. A greedy coloring is relabeled canonically to create both incumbents.

The seed rule is `40_000_000 + family_index*100_000 + tier_index*10_000 + replication`, with family order TSP/coloring, tier order small/large and replications0–4. All20 seeds were checked against previous manifests. A pair intentionally shares its seed. No cases are selected by observed speed, and the generator refuses to overwrite its frozen manifest.

All40 encodings passed final witness, objective, hash and JSON/TXT checks. Small mapping tests additionally covered all two city0-fixed tours of a three-city TSP and all256 labelings of a four-vertex coloring instance, comparing feasibility and objective across the encodings. They check representations without computing optimum references. The delivered corpus took approximately0.216 seconds to construct and validate.

Example separate run after freezing the solver policy:

```sh
python3 bench.py --manifest paired-manifest.json --split formulation --configs stock,portfolio --repeats 3 --limit-ms 2000 --output results/paired-formulations.jsonl
```

Report comparisons **by `paired_problem_id`**, retaining both encodings, every timeout and the setup/heuristic costs. Ordinary solver-configuration tables alone do not answer formulation selection: the central comparisons here are binary versus native on each shared semantic problem, with the solver configuration held fixed. Treat unknown optima as unknown unless subsequently certified. Do not choose a formulation using this track's test outcomes and then report the same outcomes as an independent evaluation of that choice.

This tests representation effects for two modest families, not automatic universal reformulation. Native TSP uses a strong global constraint; the coloring model still uses pairwise edge constraints. A successful result would motivate a later selector trained on separate semantic instances and evaluated on fresh pairs.
