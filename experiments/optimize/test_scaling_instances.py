#!/usr/bin/env python3
"""Small exhaustive oracles and generator contracts; no solver execution."""
import copy
import hashlib
import itertools
import json
import random
import unittest
from unittest.mock import patch

import scaling_instances as instances


class CapacityOracleTests(unittest.TestCase):
    def test_exact_reference_against_subsets(self):
        rng = random.Random(19037)
        for n in range(1, 9):
            for _ in range(12):
                weights = [rng.randint(1, 9) for _ in range(n)]
                profits = [rng.randint(1, 11) for _ in range(n)]
                capacity = rng.randint(0, sum(weights) + 1)
                feasible = [(sum(p * x for p, x in zip(profits, point)), point)
                            for point in itertools.product((0, 1), repeat=n)
                            if sum(w * x for w, x in zip(weights, point)) <= capacity]
                best = max(profit for profit, _ in feasible)
                reference = instances.capacity_reference(weights, profits, capacity)
                self.assertEqual(reference["objective"], -best)
                self.assertIn((best, tuple(reference["assignment"])), feasible)

    def test_zero_capacity_ties_heavy_items_and_predecessors(self):
        cases = [([2, 2, 2], [3, 3, 3], 2), ([4, 1, 3], [7, 3, 6], 0),
                 ([9, 2, 3], [40, 4, 5], 5), ([3, 4, 2], [7, 8, 5], 5),
                 ([1, 1, 1], [1, 1, 1], 3)]
        for weights, profits, capacity in cases:
            answer = instances.capacity_reference(weights, profits, capacity)
            point = answer["assignment"]
            self.assertLessEqual(sum(w * x for w, x in zip(weights, point)), capacity)
            self.assertEqual(-sum(p * x for p, x in zip(profits, point)), answer["objective"])
            expected = min(-sum(p * bit for p, bit in zip(profits, point))
                           for point in itertools.product((0, 1), repeat=len(weights))
                           if sum(w * bit for w, bit in zip(weights, point)) <= capacity)
            self.assertEqual(expected, answer["objective"])

    def test_rejects_unsupported_or_unbounded_reference_work(self):
        for args in (([], [], 0), ([0], [2], 3), ([1], [-1], 3), ([True], [1], 3),
                     ([1], [1], -1), ([1], [60000], 1), ([1] * 513, [1] * 513, 3)):
            with self.assertRaises(ValueError):
                instances.capacity_reference(*args)


class AssignmentOracleTests(unittest.TestCase):
    def test_exact_reference_against_permutations(self):
        rng = random.Random(90123)
        for n in range(1, 7):
            for _ in range(8):
                costs = [[rng.randint(0, 30) for _ in range(n)] for _ in range(n)]
                best = min(sum(costs[i][j] for i, j in enumerate(permutation))
                           for permutation in itertools.permutations(range(n)))
                reference = instances.assignment_reference(costs)
                self.assertEqual(reference["objective"], best)
                x = reference["assignment"]
                self.assertTrue(all(sum(x[i * n:(i + 1) * n]) == 1 for i in range(n)))
                self.assertTrue(all(sum(x[i * n + j] for i in range(n)) == 1 for j in range(n)))
                self.assertEqual(sum(costs[i][j] * x[i * n + j] for i in range(n) for j in range(n)), best)

    def test_ties_and_admission(self):
        self.assertEqual(instances.assignment_reference([[0] * 4 for _ in range(4)])["objective"], 0)
        for costs in ([], [[1, 2]], [[True]], [[-1]], [[1] * 17 for _ in range(17)]):
            with self.assertRaises(ValueError):
                instances.assignment_reference(costs)


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = instances.generate_suite(with_references=False)

    def test_frozen_counts_determinism_prefixes_and_caps(self):
        self.assertEqual(len(self.models), 13)
        self.assertEqual(self.models, instances.generate_suite(with_references=False))
        self.assertEqual(len({m["id"] for m in self.models}), 13)
        for family, sizes in (("capacity_uncorrelated", [8, 32, 128, 384, 512]),
                              ("capacity_correlated", [8, 32, 128, 384])):
            models = [m for m in self.models if m["family"] == family]
            self.assertEqual([m["n"] for m in models], sizes)
            full = models[-1]["parameters"]
            for m in models:
                p, n = m["parameters"], m["n"]
                self.assertEqual(p["weights"][0], full["weights"][0][:n])
                self.assertEqual(p["profits"], full["profits"][:n])
                self.assertEqual(p["capacity"], 6 * n)
                self.assertEqual(p["table_cells"], (n + 1) * (6 * n + 1))
                self.assertEqual(p["dp_eligible"], n != 512)
                self.assertTrue(all(1 <= w <= 31 for w in p["weights"][0]))
                if family == "capacity_correlated":
                    self.assertTrue(all(0 <= profit - weight <= 10
                                        for weight, profit in zip(p["weights"][0], p["profits"])))
                else:
                    self.assertTrue(all(1 <= profit <= 100 for profit in p["profits"]))
        large = next(m for m in self.models if m["family"] == "capacity_uncorrelated" and m["n"] == 384)
        overflow = next(m for m in self.models if m["n"] == 512)
        self.assertEqual(large["parameters"]["table_cells"], 887425)
        self.assertEqual(overflow["parameters"]["table_cells"], 1576449)

    def test_assignment_master_prefix_and_dimensions(self):
        models = [m for m in self.models if m["family"] == "assignment"]
        self.assertEqual([m["n"] for m in models], [9, 25, 81, 256])
        master = models[-1]["parameters"]["costs"]
        for model in models:
            size = model["parameters"]["size"]
            self.assertEqual(model["parameters"]["costs"], [row[:size] for row in master[:size]])
            self.assertEqual(model["dimensions"], {"variables": size * size, "rows": 4 * size,
                                                   "nonzeros": 4 * size * size})
            self.assertFalse(model["parameters"]["dp_eligible"])

    def test_txt_roundtrip_is_sparse_model_without_start(self):
        for model in self.models:
            text = instances.encode_txt(model)
            tokens = iter(text.split())
            n, count = int(next(tokens)), int(next(tokens))
            costs = [int(next(tokens)) for _ in range(n)]
            rows = []
            for _ in range(count):
                bound, width = int(next(tokens)), int(next(tokens))
                terms = [[int(next(tokens)), int(next(tokens))] for _ in range(width)]
                rows.append({"b": bound, "a": terms})
            self.assertEqual((n, costs, rows), (model["n"], model["c"], model["rows"]))
            self.assertEqual(list(tokens), ["incumbent", "0"])
            self.assertNotIn("incumbent", model)
            self.assertNotIn("reference", model)
            data = {key: model[key] for key in ("n", "c", "rows")}
            identity = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(instances.semantic_hash(model), identity)

    def test_small_raw_truth_tables(self):
        for model in (self.models[0], next(m for m in self.models if m["family"] == "assignment")):
            p, n = model["parameters"], model["n"]
            for point in itertools.product((0, 1), repeat=n):
                if model["family"] == "assignment":
                    size = p["size"]
                    domain = all(sum(point[i * size:(i + 1) * size]) == 1 for i in range(size)) and \
                        all(sum(point[i * size + j] for i in range(size)) == 1 for j in range(size))
                else:
                    domain = sum(w * x for w, x in zip(p["weights"][0], point)) <= p["capacity"]
                checked = instances.validate_assignment(model, list(point))
                self.assertEqual(checked["valid"], domain)
                if domain:
                    self.assertEqual(checked["objective"], sum(c * x for c, x in zip(model["c"], point)))

    def test_reference_identity_corruption_and_no_implicit_oracle(self):
        model = copy.deepcopy(self.models[0])
        model["reference"] = instances._reference(model)
        self.assertTrue(instances.verify_reference(model, recompute=True)["valid"])
        with patch.object(instances, "capacity_reference", side_effect=AssertionError("unexpected oracle")):
            checked = instances.verify_reference(model)
            self.assertTrue(checked["valid"])
            self.assertFalse(checked["optimality_recomputed"])
        mutations = [lambda m: m["reference"].update(input_sha256="0" * 64),
                     lambda m: m["reference"].update(objective=True),
                     lambda m: m["reference"].update(assignment=[True] * m["n"]),
                     lambda m: m["c"].__setitem__(0, m["c"][0] - 1),
                     lambda m: m["rows"][0]["a"].reverse(),
                     lambda m: m["parameters"].update(dp_eligible=False),
                     lambda m: m["dimensions"].update(nonzeros=0)]
        for change in mutations:
            bad = copy.deepcopy(model)
            change(bad)
            self.assertFalse(instances.verify_reference(bad)["valid"])
        # Consistent but suboptimal witness is only refuted by explicit reproof;
        # measured runs must trust the previously frozen reference bytes.
        bad = copy.deepcopy(model)
        bad["reference"].update(assignment=[0] * model["n"], objective=0)
        self.assertTrue(instances.verify_reference(bad)["valid"])
        self.assertFalse(instances.verify_reference(bad, recompute=True)["valid"])
        for point in ([0] * (model["n"] - 1), [0.0] * model["n"], [2] * model["n"]):
            self.assertFalse(instances.validate_assignment(model, point)["valid"])


if __name__ == "__main__":
    unittest.main()
