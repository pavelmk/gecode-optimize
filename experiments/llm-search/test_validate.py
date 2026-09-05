#!/usr/bin/env python3
"""Small correctness tests for the independent oracle and result validator."""
import unittest

from validate import exact_solve, validate_assignment, validate_result, verify_infeasibility_certificate


class ValidatorTests(unittest.TestCase):
    def test_balancing_known_optimum_and_false_optimal_claim(self):
        problem = {"family": "scheduling", "n": 6, "machines": 2,
                   "durations": [8, 7, 6, 5, 4, 3]}
        reference = exact_solve(problem)
        self.assertEqual(reference["objective"], 17)
        problem["reference"] = reference
        false_optimum = {"status": "optimal", "assignment": [0, 1, 0, 1, 0, 1], "objective": 18}
        self.assertFalse(validate_result(problem, false_optimum)["valid"])
        self.assertTrue(validate_result(problem, reference)["claims_verified"])

    def test_weighted_cover_and_reported_objective(self):
        problem = {"family": "vertex_cover", "n": 3, "weights": [2, 3, 8],
                   "edges": [[0, 1], [0, 2], [1, 2]]}
        self.assertEqual(exact_solve(problem)["objective"], 5)
        self.assertFalse(validate_assignment(problem, [1, 0, 0])["valid"])
        result = {"status": "feasible", "assignment": [1, 1, 0], "objective": 4}
        self.assertFalse(validate_result(problem, result)["valid"])

    def test_coloring_witness_and_false_infeasibility(self):
        problem = {"family": "coloring", "n": 3, "colors": 2, "edges": [[0, 1], [1, 2]]}
        problem["reference"] = exact_solve(problem)
        self.assertFalse(validate_result(problem, {"status": "infeasible"})["valid"])
        self.assertFalse(validate_assignment(problem, [0, 0, 1])["valid"])
        self.assertTrue(validate_assignment(problem, [0, 1, 0])["valid"])

    def test_odd_cycle_is_infeasible_with_two_colors(self):
        problem = {"family": "coloring", "n": 5, "colors": 2,
                   "edges": [[0, 1], [0, 4], [1, 2], [2, 3], [3, 4]]}
        self.assertEqual(exact_solve(problem)["status"], "infeasible")

    def test_odd_wheel_certificate_checks_actual_edges(self):
        problem = {"family": "coloring", "n": 6, "colors": 3,
                   "edges": [[0, 1], [0, 2], [0, 3], [0, 4], [0, 5],
                             [1, 2], [1, 5], [2, 3], [3, 4], [4, 5]],
                   "infeasibility_certificate": {"type": "odd_wheel", "hub": 0,
                                                 "rim": [1, 2, 3, 4, 5]}}
        self.assertTrue(verify_infeasibility_certificate(problem))
        self.assertEqual(exact_solve(problem)["status"], "infeasible")
        problem["edges"].remove([4, 5])
        self.assertFalse(verify_infeasibility_certificate(problem))
        self.assertEqual(exact_solve(problem)["status"], "optimal")

    def test_unverified_optimal_claim_is_flagged(self):
        problem = {"family": "vertex_cover", "n": 2, "weights": [2, 8], "edges": [[0, 1]]}
        result = {"status": "optimal", "assignment": [0, 1], "objective": 8}
        checked = validate_result(problem, result)
        self.assertTrue(checked["valid"])
        self.assertFalse(checked["claims_verified"])
        self.assertFalse(validate_result(problem, result, brute_force=True)["valid"])

    def test_boolean_or_wrong_length_assignments_rejected(self):
        problem = {"family": "vertex_cover", "n": 2, "weights": [2, 8], "edges": [[0, 1]]}
        self.assertFalse(validate_assignment(problem, [True, False])["valid"])
        self.assertFalse(validate_assignment(problem, [1])["valid"])

    def test_exact_oracle_honors_state_budget(self):
        problem = {"family": "vertex_cover", "n": 20, "weights": [1] * 20, "edges": []}
        self.assertEqual(exact_solve(problem, max_states=100)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
