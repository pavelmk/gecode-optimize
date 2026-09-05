"""Fast report-integrity tests; no solver processes or benchmark timings."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import analyze
import validate


def fixture():
    instance = {"id": "fixture", "family": "external_binary", "kind": "binary", "split": "test",
                "tier": "tiny", "seed": 1, "n": 2, "c": [1, 2],
                "rows": [{"a": [[0, 1], [1, 1]], "b": 1}],
                "incumbent": [1, 1], "incumbent_objective": 3}
    instance["reference"] = {"status": "optimal", "objective": 1, "input_sha256": validate.input_hash(instance)}
    protocol = {"limit_ms": 100, "warm": 1, "configs": {name: ["binary", "native", "afc", "native"] for name in ("stock", "candidate")},
                "binaries": {"binary": "a" * 64}}
    row = {"id": "fixture", "family": "external_binary", "kind": "binary", "split": "test", "tier": "tiny",
           "config": "stock", "repetition": 0, "status": "optimal", "elapsed_ms": 25, "process_wall_ms": 28,
           "limit_ms": 100, "warm": True, "initial_objective": 3, "objective": 1, "assignment": [1, 0],
           "improvements": [[20, 1]], "objective_at_limit": 1, "completed_within_budget": True,
           "binary_sha256": "a" * 64, "reference_status": "optimal", "reference_objective": 1}
    row["validation"] = validate.validate_result(instance, row)
    return instance, protocol, row


class AuditTests(unittest.TestCase):
    def test_valid_and_late_proof(self):
        instance, protocol, row = fixture()
        self.assertTrue(analyze.audit_row(row, protocol, instance, "binary")[0]["valid"])
        row.update(elapsed_ms=101, completed_within_budget=False)
        self.assertTrue(analyze.audit_row(row, protocol, instance, "binary")[0]["valid"])
        row["completed_within_budget"] = True
        with self.assertRaisesRegex(ValueError, "deadline proof flag"):
            analyze.audit_row(row, protocol, instance, "binary")

    def test_hash_and_reference_changes_rejected(self):
        for key, value in [("binary_sha256", "b" * 64), ("reference_objective", 9), ("objective_at_limit", 2),
                           ("initial_objective", 2), ("assignment", [0, 1])]:
            instance, protocol, row = fixture()
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                analyze.audit_row(row, protocol, instance, "binary")

    def test_trajectory_does_not_count_post_deadline_solution(self):
        instance, protocol, row = fixture()
        row.update(elapsed_ms=102, completed_within_budget=False, improvements=[[101, 1]], objective_at_limit=3)
        self.assertTrue(analyze.audit_row(row, protocol, instance, "binary")[1])
        row["objective_at_limit"] = 1
        with self.assertRaisesRegex(ValueError, "deadline objective"):
            analyze.audit_row(row, protocol, instance, "binary")

    def test_incomplete_and_stale_inputs_fail_closed(self):
        instance, protocol, row = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "fixture.json").write_text(json.dumps(instance))
            (directory / "fixture.txt").write_text("2 1\n1 2\n1 2 0 1 1 1\nincumbent 1\n1 1\n")
            record = {key: instance[key] for key in ("id", "family", "kind", "split", "tier", "seed")}
            record.update(json="fixture.json", txt="fixture.txt")
            manifest = directory / "manifest.json"
            manifest.write_text(json.dumps({"instances": [record]}))
            protocol.update(manifests={str(manifest): analyze.sha(manifest)},
                            inputs={"fixture": {ext: analyze.sha(directory / ("fixture." + ext)) for ext in ("json", "txt")}},
                            repeats=1, split="test")
            rows = directory / "test.jsonl"
            second = dict(row, config="candidate")
            rows.write_text(json.dumps(row) + "\n" + json.dumps(second) + "\n")
            metadata = {"protocol": protocol, "completed": True, "expected_runs": 2, "completed_runs": 2}
            rows.with_suffix(".meta.json").write_text(json.dumps(metadata))
            cohorts, _ = analyze.load_runs([rows], {"test"}, [], {})
            self.assertEqual(len(next(iter(cohorts.values()))["rows"]), 2)
            metadata["completed"] = False
            rows.with_suffix(".meta.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "not complete"):
                analyze.load_runs([rows], {"test"}, [], {})
            metadata["completed"] = True
            rows.with_suffix(".meta.json").write_text(json.dumps(metadata))
            (directory / "fixture.txt").write_text("stale")
            with self.assertRaisesRegex(ValueError, "changed input"):
                analyze.load_runs([rows], {"test"}, [], {})

    def test_timeout_scores_and_common_subset(self):
        instance, protocol, template = fixture()
        source = {"record": instance, "instance": instance, "kind": "binary", "independent_reference": instance["reference"],
                  "independent_reference_source": "enumeration", "best_observed_at_limit": 1, "gecode_claimed_optimum": 1}
        cohort = {"id": "test", "inputs": {"fixture": source}, "rows": {}, "expected": set(), "protocol": protocol,
                  "source_files": [], "incomplete": False}
        for config in ("stock", "candidate"):
            for rep in range(3):
                row = copy.deepcopy(template)
                row.update(config=config, repetition=rep, elapsed_ms=101 if config == "stock" else 25,
                           completed_within_budget=config != "stock", _deadline_witness_checked=True,
                           primal_lp_calls=7, primal_exact_checks=3, primal_found=config != "stock")
                key = ("fixture", config, rep)
                cohort["rows"][key] = row
                cohort["expected"].add(key)
        report = analyze.build_report({"test": cohort}, [], "stock", 0, False)
        by_config = {entry["config"]: entry for entry in report["cohorts"][0]["overall"]}
        self.assertEqual(by_config["stock"]["completed_instances"], 0)
        self.assertEqual(by_config["stock"]["mean_median_par2_score_ms"], 200)
        self.assertEqual(by_config["stock"]["late_proof_runs"], 3)
        self.assertEqual(by_config["candidate"]["newly_proved_instances"], 1)
        self.assertEqual(by_config["candidate"]["common_completed_instances"], 0)
        self.assertIsNone(by_config["candidate"]["common_completed_mean_config_ms"])
        item = next(item for item in report["instances"] if item["config"] == "candidate")
        self.assertEqual(item["censored_speed_ratio_lower_bound"], 4)
        self.assertIsNone(item["paired_completed_speed_ratio"])
        self.assertEqual(item["median_primal_lp_calls"], 7)
        self.assertEqual(item["median_primal_calls"], 7)
        self.assertEqual(item["median_primal_exact_checks"], 3)
        self.assertEqual(item["primal_found_runs"], 3)
        cohort["rows"][("fixture", "stock", 0)].update(elapsed_ms=10, completed_within_budget=True)
        report = analyze.build_report({"test": cohort}, [], "stock", 0, False)
        item = next(item for item in report["cohorts"][0]["overall"] if item["config"] == "candidate")
        self.assertEqual(item["newly_proved_instances"], 0)
        self.assertEqual(item["newly_reliably_solved_instances"], 1)
        self.assertEqual(item["newly_solvable_families_in_budget"], [])

    def test_external_independence_requires_named_non_gecode_source(self):
        self.assertFalse(analyze.independent_external({"independent": True}))
        self.assertFalse(analyze.independent_external({"independent": True, "solver": "Gecode"}))
        self.assertTrue(analyze.independent_external({"independent": True, "solver": "exact enumeration"}))


if __name__ == "__main__":
    unittest.main()
