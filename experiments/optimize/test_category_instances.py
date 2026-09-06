#!/usr/bin/env python3
"""Independent small family oracles and frozen driver schema; no solver calls."""
import copy
import itertools
import random
import unittest
from unittest.mock import patch

import category_instances as instances


def brute_bins(weights, capacity):
    """Enumerate unlabeled set partitions directly, without subset-DP states."""
    best = len(weights)
    def visit(index, loads):
        nonlocal best
        if len(loads) >= best:
            return
        if index == len(weights):
            best = len(loads)
            return
        for b in range(len(loads)):
            if loads[b] + weights[index] <= capacity:
                changed = loads[:]
                changed[b] += weights[index]
                visit(index + 1, changed)
        visit(index + 1, loads + [weights[index]])
    visit(0, [])
    return best


class CategoryInstancesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = instances.generate_suite(with_references=False)

    def family(self, name):
        return [m for m in self.models if m["family"] == name]

    def test_prespecified_counts_dimensions_and_determinism(self):
        self.assertEqual(len(self.models), 33)
        self.assertEqual(self.models, instances.generate_suite(with_references=False))
        self.assertEqual(set(m["category"] for m in self.models), set(instances.CATEGORIES))
        self.assertEqual([m["n"] for m in self.family("facility_location")], [8, 28, 104, 300])
        self.assertEqual([m["n"] for m in self.family("bin_packing")], [15, 36, 65, 102])
        self.assertEqual([m["n"] for m in self.family("production")], [24, 48, 96, 192])
        for family, inputs, modelled in (("native_tsp", [4, 8, 12, 16], [8, 16, 24, 32]),
                                        ("weighted_queens", [4, 8, 10, 12], [16, 32, 40, 48])):
            models = self.family(family)
            self.assertEqual([m["n"] for m in models], inputs)
            self.assertEqual([m["modelled_variables"] for m in models], modelled)
            self.assertTrue(all(m["dimensions"]["input_variables"] == m["n"] for m in models))
        self.assertEqual([(m["family"], m["n"]) for m in self.models if m["stress"]],
                         [("capacity_uncorrelated", 512)])

    def test_prior_capacity_assignment_semantics_preserved(self):
        prior = instances.scaling.generate_suite(with_references=False)
        keyed = {m["id"]: m for m in self.models}
        for old in prior:
            model = keyed[old["id"]]
            self.assertEqual(instances.semantic_hash(model), instances.scaling.semantic_hash(old))
            self.assertEqual(instances.encode_txt(model), instances.scaling.encode_txt(old))
            self.assertEqual(model["parameters"], old["parameters"])
        main_knapsack = [m for m in self.models if m["category"] == "knapsack" and not m["stress"]]
        for size in (8, 32, 128, 384):
            self.assertEqual({m["variant"] for m in main_knapsack if m["n"] == size},
                             {"uncorrelated", "correlated"})

    def test_prefixes_and_native_placeholder_not_reference(self):
        for family in ("native_tsp", "weighted_queens"):
            models = self.family(family)
            master = models[-1]["data"]
            for model in models:
                n = model["n"]
                self.assertEqual(model["data"], [row[:n] for row in master[:n]])
                tokens = instances.encode_txt(model).split()
                self.assertEqual(tokens[:4], [family, str(n), "0", str(n)])
                self.assertEqual(list(map(int, tokens[4:4 + n * n])), [c for row in model["data"] for c in row])
                self.assertEqual(tokens[4 + n * n:], ["0"] * n)
                mutated = copy.deepcopy(model)
                mutated["reference"] = {"assignment": list(range(n)), "objective": -999999}
                self.assertEqual(instances.encode_txt(model), instances.encode_txt(mutated))
        bins = self.family("bin_packing")
        for model in bins:
            self.assertEqual(model["parameters"]["weights"], bins[-1]["parameters"]["weights"][:model["tier_size"]])
        production = self.family("production")
        for model in production:
            count = model["tier_size"]
            self.assertEqual(model["parameters"]["demands"], production[-1]["parameters"]["demands"][:count])
            self.assertEqual(model["parameters"]["production_costs"], production[-1]["parameters"]["production_costs"][:count])

    def test_binary_txt_roundtrip_and_zero_start(self):
        for model in self.models:
            if model["kind"] != "binary":
                continue
            tokens = iter(instances.encode_txt(model).split())
            n, count = int(next(tokens)), int(next(tokens))
            costs = [int(next(tokens)) for _ in range(n)]
            rows = []
            for _ in range(count):
                b, width = int(next(tokens)), int(next(tokens))
                rows.append({"b": b, "a": [[int(next(tokens)), int(next(tokens))] for _ in range(width)]})
            self.assertEqual((n, costs, rows), (model["n"], model["c"], model["rows"]))
            self.assertEqual(list(tokens), ["incumbent", "0"])

    def test_bin_reference_against_unlabeled_partition_enumeration(self):
        rng = random.Random(9923)
        for n in range(1, 9):
            for _ in range(10):
                capacity = rng.randint(4, 12)
                weights = [rng.randint(1, capacity) for _ in range(n)]
                result = instances.bin_reference(weights, capacity, n)
                self.assertEqual(result["objective"], brute_bins(weights, capacity))
                x = result["assignment"]
                self.assertTrue(all(sum(x[j * n:(j + 1) * n]) == 1 for j in range(n)))
                self.assertTrue(all(sum(weights[j] * x[j * n + b] for j in range(n)) <= capacity * x[n * n + b]
                                    for b in range(n)))
                self.assertEqual(sum(x[n * n:]), result["objective"])
        for args in (([], 1, 1), ([2], 1, 1), ([True], 2, 1), ([1] * 17, 4, 17)):
            with self.assertRaises(ValueError):
                instances.bin_reference(*args)

    def test_small_facility_and_production_domain_oracles(self):
        facility = self.family("facility_location")[0]
        p = facility["parameters"]
        f, customers = p["facilities"], p["customers"]
        best = None
        for opened in itertools.product((0, 1), repeat=f):
            for locations in itertools.product(range(f), repeat=customers):
                point = list(opened) + [int(locations[i] == j) for i in range(customers) for j in range(f)]
                valid = all(opened[j] for j in locations)
                self.assertEqual(instances.validate_assignment(facility, point)["valid"], valid)
                if valid:
                    value = sum(c * x for c, x in zip(p["opening_costs"], opened)) + sum(p["assignment_costs"][i][j] for i, j in enumerate(locations))
                    best = value if best is None else min(best, value)
        self.assertEqual(instances._reference(facility)["objective"], best)
        production = self.family("production")[0]
        p = production["parameters"]
        best = None
        for quantities in itertools.product(range(p["options"]), repeat=p["periods"]):
            inventory, physical, valid = 0, 0, True
            for t, quantity in enumerate(quantities):
                inventory += quantity - p["demands"][t]
                valid = valid and 0 <= inventory <= p["storage"]
                physical += p["production_costs"][t][quantity] + p["holding_cost"] * inventory
            valid = valid and inventory == 0
            point = [int(quantities[t] == q) for t in range(p["periods"]) for q in range(p["options"])]
            self.assertEqual(instances.validate_assignment(production, point)["valid"], valid)
            if valid:
                value = physical - p["objective_constant"]
                best = value if best is None else min(best, value)
        self.assertEqual(instances._reference(production)["objective"], best)

    def test_small_native_oracles_against_permutations(self):
        for family in ("native_tsp", "weighted_queens"):
            model = self.family(family)[0]
            n, best = model["n"], None
            for point in itertools.permutations(range(n)):
                if family == "native_tsp":
                    seen, current = set(), 0
                    for _ in range(n):
                        seen.add(current)
                        current = point[current]
                    valid = len(seen) == n and current == 0
                else:
                    valid = all(abs(point[i] - point[j]) != j - i for i in range(n) for j in range(i + 1, n))
                self.assertEqual(instances.validate_assignment(model, list(point))["valid"], valid)
                if valid:
                    value = sum(model["data"][i][j] for i, j in enumerate(point))
                    best = value if best is None else min(best, value)
            self.assertEqual(instances._reference(model)["objective"], best)

    def test_reference_trust_and_metadata_mutation(self):
        for family in ("facility_location", "bin_packing", "production", "native_tsp", "weighted_queens"):
            model = copy.deepcopy(self.family(family)[0])
            model["reference"] = instances._reference(model)
            self.assertTrue(instances.verify_reference(model, recompute=True)["valid"])
            with patch.object(instances, "_reference", side_effect=AssertionError("oracle called during read")):
                checked = instances.verify_reference(model)
                self.assertTrue(checked["valid"])
                self.assertFalse(checked["optimality_recomputed"])
            bad = copy.deepcopy(model)
            bad["modelled_variables"] += 1
            self.assertFalse(instances.verify_reference(bad)["valid"])
            bad = copy.deepcopy(model)
            bad["reference"]["input_sha256"] = "0" * 64
            self.assertFalse(instances.verify_reference(bad)["valid"])
            self.assertFalse(instances.validate_assignment(model, [False] * model["n"])["valid"])


if __name__ == "__main__":
    unittest.main()
