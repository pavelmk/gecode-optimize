#!/usr/bin/env python3
"""Pure bounded generator/validator tests; no solver or large exact oracle."""
import copy
import itertools
import unittest
from unittest.mock import patch

import boundary_instances as instances


class BoundaryInstancesTests(unittest.TestCase):
    def test_existing_semantics_and_encodings(self):
        old = instances.category.generate_suite(with_references=False)
        for model in old:
            name, size = model["category"], model["tier_size"]
            if name == "facility_location" and model["parameters"]["customers"] != 2 * size:
                continue
            if name == "bin_packing" and model["parameters"]["bins"] != (size + 2) // 3:
                continue
            new = instances.make(name, size, model["variant"])
            self.assertEqual(instances.semantic_hash(new), instances.category.semantic_hash(model))
            self.assertEqual(instances.encode_txt(new), instances.category.encode_txt(model))

    def test_preserved_blocks_and_larger_prefixes(self):
        old = instances.category.generate_suite(with_references=False)
        for name in ("assignment", "facility_location", "production", "native_tsp", "weighted_queens"):
            models = [m for m in old if m["category"] == name]
            master = instances.make(name, instances.BOUNDS[name][1])
            for m in models:
                p, q = m["parameters"], master["parameters"]
                if name == "assignment":
                    self.assertEqual(p["costs"], [row[:p["size"]] for row in q["costs"][:p["size"]]])
                elif name == "facility_location":
                    self.assertEqual(p["opening_costs"], q["opening_costs"][:p["facilities"]])
                    self.assertEqual(p["assignment_costs"], [row[:p["facilities"]] for row in q["assignment_costs"][:p["customers"]]])
                elif name == "production":
                    for key in ("demands", "production_costs"):
                        self.assertEqual(p[key], q[key][:p["periods"]])
                else:
                    self.assertEqual(m["data"], [row[:m["n"]] for row in master["data"][:m["n"]]])
            mid = instances.make(name, (sum(instances.BOUNDS[name]) // 2))
            self.assertEqual(mid, instances.make(name, mid["natural_size"]))

    def test_ranges_dimensions_and_no_reference_work(self):
        with patch.object(instances.category, "_reference", side_effect=AssertionError("oracle")), \
             patch.object(instances.category.scaling, "_reference", side_effect=AssertionError("oracle")):
            for name, (low, high) in instances.BOUNDS.items():
                variant = "uncorrelated" if name == "knapsack" else "single"
                for size in (low, low + 1, high - 1, high):
                    m = instances.make(name, size, variant)
                    self.assertNotIn("reference", m)
                    multiplier = 2 if name == "native_tsp" else 4 if name == "weighted_queens" else 1
                    self.assertEqual(m["model_variables"], multiplier * m["n"])
                    self.assertEqual(len(instances.semantic_hash(m)), 64)
                    self.assertTrue(instances.encode_txt(m).endswith("\n"))
                for invalid in (low - 1, high + 1, True, float(low), None):
                    with self.assertRaises(ValueError):
                        instances.make(name, invalid, variant)
        with self.assertRaises(ValueError):
            instances.make("knapsack", 8)
        with self.assertRaises(ValueError):
            instances.make("assignment", 3, "correlated")

    def test_large_original_witnesses_and_corruption(self):
        cases = []
        m = instances.make("assignment", 32)
        cases.append((m, [int(i == j) for i in range(32) for j in range(32)]))
        m = instances.make("facility_location", 16)
        cases.append((m, [1] + [0] * 15 + [int(j == 0) for _ in range(32) for j in range(16)]))
        m = instances.make("production", 48)
        cases.append((m, [int(q == d) for d in m["parameters"]["demands"] for q in range(8)]))
        m = instances.make("native_tsp", 96)
        cases.append((m, [(i + 1) % 96 for i in range(96)]))
        m = instances.make("weighted_queens", 32)
        queens = [v - 1 for v in list(range(2, 33, 2)) + [3, 1] + list(range(7, 32, 2)) + [5]]
        self.assertTrue(all(queens[i] != queens[j] and abs(queens[i] - queens[j]) != abs(i - j)
                            for i in range(32) for j in range(i)))
        cases.append((m, queens))
        m = instances.make("bin_packing", 32)
        p, loads, choices = m["parameters"], [], [0] * 32
        for item in sorted(range(32), key=lambda i: -p["weights"][i]):
            weight = p["weights"][item]
            b = next((b for b, load in enumerate(loads) if load + weight <= p["capacity"]), len(loads))
            if b == len(loads):
                loads.append(0)
            loads[b] += weight
            choices[item] = b
        self.assertLessEqual(len(loads), p["bins"])
        cases.append((m, [int(b == choice) for choice in choices for b in range(p["bins"])] +
                      [int(b < len(loads)) for b in range(p["bins"])]))
        m = instances.make("knapsack", 512, "correlated")
        cases.append((m, [0] * 512))
        for m, witness in cases:
            checked = instances.validate_assignment(m, witness)
            self.assertTrue(checked["valid"], checked)
            self.assertTrue(checked["domain_semantics_checked"])
            self.assertFalse(instances.validate_assignment(m, witness[:-1])["valid"])
            bad = copy.deepcopy(m)
            bad["model_variables"] += 1
            self.assertFalse(instances.validate_assignment(bad, witness)["valid"])
            bad = copy.deepcopy(m)
            if m["kind"] == "binary":
                bad["c"][0] += 1
            else:
                bad["data"][0][1] += 1
            with self.assertRaises(ValueError):
                instances.encode_txt(bad)
            with_hint = copy.deepcopy(m)
            with_hint["reference"] = {"assignment": witness, "objective": -999}
            self.assertEqual(instances.encode_txt(m), instances.encode_txt(with_hint))

    def test_small_independent_truth_tables(self):
        m = instances.make("knapsack", 8, "uncorrelated")
        p = m["parameters"]
        for x in itertools.product((0, 1), repeat=8):
            expected = sum(w * v for w, v in zip(p["weights"][0], x)) <= p["capacity"]
            checked = instances.validate_assignment(m, list(x))
            self.assertEqual(checked["valid"], expected)
            if expected:
                self.assertEqual(checked["objective"], -sum(v * c for v, c in zip(x, p["profits"])))
        m = instances.make("weighted_queens", 4)
        for x in itertools.product(range(4), repeat=4):
            expected = all(x[i] != x[j] and abs(x[i] - x[j]) != abs(i - j)
                           for i in range(4) for j in range(i))
            self.assertEqual(instances.validate_assignment(m, list(x))["valid"], expected)


if __name__ == "__main__":
    unittest.main()
