"""Runner correctness/failure-path tests; no solver timing claims."""
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("fast_regression", Path(__file__).with_name("fast_regression.py"))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def payload(**updates):
    data = {"case": "lp_min_offset", "status": "optimal", "checks": 4,
            "backend": "HiGHS", "backend_version": "1", "guarantee": "numerical",
            "elapsed_seconds": 0.001, "objectives": [4]}
    data.update(updates)
    return {"returncode": 0, "stdout": json.dumps(data), "stderr": ""}


class ProtocolTests(unittest.TestCase):
    def test_windows_gate_remains_explicitly_unsupported(self):
        self.assertIsNone(F.platform_support_error("posix"))
        self.assertIn("Unsupported", F.platform_support_error("nt"))
        self.assertFalse(F.containment_module().WINDOWS_RUNTIME_VERIFIED)
        self.assertIn("Unsupported", F.platform_support_error("unknown"))

    def test_watchdog_receives_windows_owner_before_creation(self):
        budget = F.Budget(2)
        calls = []
        class Process:
            job, returncode = 1, 0
            def start(self, *args):
                self_test.assertIs(budget.containment, self)
                calls.append("start")
            def poll(self):
                return 0
            def cleanup(self, timeout):
                self_test.assertGreaterEqual(timeout, 0)
                self_test.assertLessEqual(timeout, .2)
                calls.append("cleanup")
                self.job = None
        self_test = self
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(F, "os", SimpleNamespace(name="nt", fstat=os.fstat)), \
                 mock.patch.object(F, "containment_module", return_value=SimpleNamespace(WindowsJobProcess=Process)):
                result = F.run_command(["ignored"], budget, 1, directory)
        self.assertNotIn("error", result)
        self.assertEqual(calls, ["start", "cleanup"])
        self.assertIsNone(budget.containment)

    def test_failed_windows_cleanup_retains_watchdog_owner_and_blocks_next_launch(self):
        budget = F.Budget(2)
        class Process:
            job, returncode = 1, 0
            def start(self, *args):
                pass
            def poll(self):
                return 0
            def cleanup(self, timeout):
                raise OSError("job handle could not close")
            def terminate(self):
                calls.append("terminate")
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(F, "os", SimpleNamespace(name="nt", fstat=os.fstat)), \
                 mock.patch.object(F, "containment_module", return_value=SimpleNamespace(WindowsJobProcess=Process)):
                result = F.run_command(["ignored"], budget, 1, directory)
                self.assertIn("cleanup failed", result["error"])
                self.assertIsNotNone(budget.containment)
                budget.kill_group()
                with self.assertRaisesRegex(F.Failure, "refusing another launch"):
                    F.run_command(["ignored"], budget, 1, directory)
        self.assertEqual(calls, ["terminate"])

    def test_required_native_case_exact_and_positive(self):
        name = F.NATIVE_CASES[0][1]
        for text in ("", name, name+" -", name+" +\nother +", name+" +\n"+name+" +"):
            with self.assertRaises(F.Failure):
                F.validate_output("cp_distinct", {"returncode": 0, "stdout": text, "stderr": ""}, name)
        self.assertEqual(F.validate_output("cp_distinct", {"returncode": 0, "stdout": name+" +\n", "stderr": ""}, name)["checks"], 1)

    def test_nonfinite_bad_status_missing_checks_and_wrong_oracle(self):
        for changes in ({"objectives": [math.nan]}, {"objectives": [math.inf]}, {"elapsed_seconds": math.inf},
                        {"objectives": []}, {"objectives": [5]}, {"case": "other"}, {"checks": 0},
                        {"checks": True}, {"status": "time_limit"}, {"backend": ""}, {"backend": "Gecode native"},
                        {"guarantee": "exact"}, {"elapsed_seconds": -1}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("lp_min_offset", payload(**changes))
        self.assertEqual(F.validate_output("lp_min_offset", payload())["objectives"], [4])

    def test_required_new_cases_and_native_provenance(self):
        self.assertIn("lp_evidence", F.REQUIRED)
        evidence = dict(case="lp_evidence", status="evidence_checked", objectives=[])
        self.assertEqual(F.validate_output("lp_evidence", payload(**evidence))["status"], "evidence_checked")
        for changes in ({"backend": "Gecode native"}, {"guarantee": "exact"},
                        {"status": "optimal"}, {"objectives": [-2, 1]}, {"checks": 0}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("lp_evidence", payload(**(evidence | changes)))
        regular = dict(case="native_regular", backend="Gecode native", guarantee="exact", objectives=[-3, 1])
        self.assertIn("native_regular", F.REQUIRED)
        self.assertIn("scenario_batches", F.REQUIRED)
        self.assertEqual(F.validate_output("native_regular", payload(**regular))["objectives"], [-3, 1])
        for changes in ({"backend": "HiGHS"}, {"guarantee": "numerical"}, {"objectives": [-3, 3]}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("native_regular", payload(**(regular | changes)))
        scenario = dict(case="scenario_batches", objectives=[5, 9, -11, 7])
        self.assertEqual(F.validate_output("scenario_batches", payload(**scenario))["objectives"], [5, 9, -11, 7])
        for changes in ({"objectives": [5, 9, -11]}, {"objectives": [5, 9, -7, 7]}, {"status": "time_limit"}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("scenario_batches", payload(**(scenario | changes)))
        for case in ("lp_observations", "session_reoptimization", "diagnostics_groups", "native_exact_reified",
                     "native_globals", "c_api_ownership", "feasibility_repair", "native_checked_lp", "solution_pool", "integer_presolve", "native_frontier_bounds", "convex_quadratic", "native_root_covers", "native_binary_branching", "native_complete_start"):
            self.assertIn(case, F.REQUIRED)
        self.assertEqual(F.OPTIMIZE_CASES["native_exact_reified"][1], [-11, 12])
        observed = dict(case="lp_observations", backend="HiGHS", guarantee="numerical", objectives=[15, 19])
        self.assertEqual(F.validate_output("lp_observations", payload(**observed))["objectives"], [15, 19])
        for changes in ({"backend": "Gecode native"}, {"guarantee": "exact"}, {"objectives": [15, 18]}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("lp_observations", payload(**(observed | changes)))
        for name, backend, guarantee, values in (
            ("convex_quadratic", "HiGHS QP", "numerical", [3.5, 2.5]),
            ("native_root_covers", "Gecode native + checked LP", "exact", [15, 19]),
            ("native_binary_branching", "Gecode native frontier", "exact", [-17, 17]),
            ("native_complete_start", "Gecode native", "exact", [-4, 7]),
        ):
            good = dict(case=name, backend=backend, guarantee=guarantee, objectives=values)
            self.assertEqual(F.validate_output(name, payload(**good))["objectives"], values)
            for changes in ({"backend": "HiGHS"}, {"guarantee": "certified"}, {"objectives": values[:-1]}):
                with self.subTest(case=name, changes=changes), self.assertRaises(F.Failure):
                    F.validate_output(name, payload(**(good | changes)))
        good = dict(case="native_exact_reified", backend="Gecode native", guarantee="exact", objectives=[-11, 12])
        self.assertEqual(F.validate_output("native_exact_reified", payload(**good))["backend"], "Gecode native")
        for changes in ({"backend": "HiGHS"}, {"guarantee": "numerical"}, {"objectives": [-11+1e-8, 12]}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("native_exact_reified", payload(**(good | changes)))
        self.assertEqual(F.validate_output("diagnostics_groups", payload(case="diagnostics_groups", status="irreducible", objectives=[]))["status"], "irreducible")
        globals_payload = dict(case="native_globals", backend="Gecode native", guarantee="exact", objectives=[7, 30])
        self.assertEqual(F.validate_output("native_globals", payload(**globals_payload))["objectives"], [7, 30])
        for changes in ({"backend": "HiGHS"}, {"objectives": [7+1e-8, 30]}, {"guarantee": "numerical"}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("native_globals", payload(**(globals_payload | changes)))
        hybrid = dict(case="native_checked_lp", backend="Gecode native + checked LP", guarantee="exact", objectives=[13, 26])
        self.assertEqual(F.OPTIMIZE_CASES["native_checked_lp"][1], [13, 26])
        self.assertEqual(F.validate_output("native_checked_lp", payload(**hybrid))["objectives"], [13, 26])
        for changes in ({"backend": "HiGHS"}, {"backend": "Gecode native"}, {"guarantee": "numerical"}, {"objectives": [13+1e-8, 26]}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("native_checked_lp", payload(**(hybrid | changes)))
        self.assertEqual(F.validate_output("solution_pool", payload(case="solution_pool", objectives=[1, 2, 3]))["objectives"], [1, 2, 3])
        self.assertEqual(F.validate_output("integer_presolve", payload(case="integer_presolve", backend="Gecode native", guarantee="exact", objectives=[3, 7]))["objectives"], [3, 7])
        frontier = dict(case="native_frontier_bounds", backend="Gecode native frontier", guarantee="exact", objectives=[-17, -15, -17, 17, 15, 17])
        self.assertEqual(F.validate_output("native_frontier_bounds", payload(**frontier))["objectives"], frontier["objectives"])
        for changes in ({"backend": "Gecode native"}, {"guarantee": "numerical"}, {"objectives": [-17, -15, -15, 17, 15, 15]}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("native_frontier_bounds", payload(**(frontier | changes)))
        for changes in ({"backend": "HiGHS"}, {"guarantee": "numerical"}, {"objectives": [3+1e-8, 7]}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("integer_presolve", payload(**(dict(case="integer_presolve", backend="Gecode native", guarantee="exact", objectives=[3, 7]) | changes)))
        for changes in ({"objectives": [1, 3, 2]}, {"objectives": [1, 2]}, {"status": "solution_limit"}):
            with self.subTest(changes=changes), self.assertRaises(F.Failure):
                F.validate_output("solution_pool", payload(**(dict(case="solution_pool", objectives=[1, 2, 3]) | changes)))

    def test_nonzero_exit_stderr_and_malformed_output_fail(self):
        for patch in ({"returncode": 7}, {"stderr": "warning"}, {"stdout": "not JSON"},
                      {"stdout": payload()["stdout"]+payload()["stdout"]}, {"error": "timeout"}):
            result = payload(); result.update(patch)
            with self.assertRaises(F.Failure):
                F.validate_output("lp_min_offset", result)


@unittest.skipUnless(os.name == "posix", "POSIX process group runner")
class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fast-runner-test-")
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, source, seconds=1):
        return F.run_command([sys.executable, "-c", source], F.Budget(2), seconds, self.directory)

    def test_deadline_and_stderr_are_captured(self):
        started = time.monotonic()
        result = self.command("import time; time.sleep(10)", 0.08)
        self.assertIn("deadline", result["error"])
        self.assertLess(time.monotonic()-started, 1)
        result = self.command("import sys; print('diagnostic', file=sys.stderr); sys.exit(3)")
        self.assertEqual(result["returncode"], 3)
        self.assertIn("diagnostic", result["stderr"])

    def test_missing_executable_and_output_flood(self):
        result = F.run_command([str(self.directory/"missing")], F.Budget(2), 1, self.directory)
        self.assertIn("error", result)
        result = self.command("import os; os.write(1,b'x'*200000)")
        self.assertIn("output limit", result["error"])
        self.assertLessEqual(len(result["stdout"]), F.MAX_OUTPUT)

    def test_descendants_killed_even_after_parent_success(self):
        marker = self.directory/"escaped"
        child = "import time,pathlib; time.sleep(.3); pathlib.Path("+repr(str(marker))+").write_text('escaped')"
        source = "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"+repr(child)+"]); print('parent done')"
        result = self.command(source)
        self.assertEqual(result["returncode"], 0)
        time.sleep(0.4)
        self.assertFalse(marker.exists(), "descendant survived completed parent cleanup")

    def test_exhausted_outer_budget_does_not_launch(self):
        marker = self.directory/"launched"
        with self.assertRaises(F.Failure):
            F.run_command([sys.executable, "-c", "open("+repr(str(marker))+",'w').close()"], F.Budget(1, time.monotonic()-2), 1, self.directory)
        self.assertFalse(marker.exists())

    def test_whole_command_missing_required_cases_fails(self):
        source = Path(F.__file__)
        result = subprocess.run([sys.executable, str(source), "--native-binary", "/usr/bin/true",
                                 "--optimize-binary", "/usr/bin/true", "--budget-seconds", "3", "--case-seconds", "1"],
                                capture_output=True, text=True, timeout=4)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        self.assertEqual([c["case"] for c in report["cases"]], F.REQUIRED)
        self.assertTrue(all(c["correctness"] != "pass" for c in report["cases"]))
        self.assertLess(report["elapsed_seconds"], 3)

    def test_whole_command_rejects_nonfinite_budget(self):
        result = subprocess.run([sys.executable, F.__file__, "--native-binary", "/usr/bin/true", "--optimize-binary", "/usr/bin/true",
                                 "--budget-seconds", "nan"], capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite", result.stderr)

    def test_whole_deadline_marks_remaining_cases_and_preserves_output(self):
        sleeper = self.directory/"sleeper"
        sleeper.write_text("#!"+sys.executable+"\nimport time\ntime.sleep(10)\n")
        sleeper.chmod(0o700)
        started = time.monotonic()
        result = subprocess.run([sys.executable, F.__file__, "--native-binary", str(sleeper), "--optimize-binary", str(sleeper),
                                 "--budget-seconds", "1", "--case-seconds", "1"], capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic()-started, 1.5)
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        self.assertEqual(len(report["cases"]), len(F.REQUIRED))
        self.assertTrue(any(case["correctness"] == "not_run" for case in report["cases"]))
        target = self.directory/"old.json"
        target.write_text("untouched")
        result = subprocess.run([sys.executable, F.__file__, "--native-binary", "/usr/bin/true", "--optimize-binary", "/usr/bin/true",
                                 "--output", str(target)], capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "untouched")


@unittest.skipUnless(os.name == "nt", "requires real Windows runner containment")
class WindowsRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="windows-fast-runner-")
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, source, seconds=2):
        return F.run_command([sys.executable, "-c", source], F.Budget(3), seconds, self.directory)

    def test_deadline_stderr_exit_and_output_limit(self):
        started = time.monotonic()
        result = self.command("import time; time.sleep(10)", .15)
        self.assertIn("deadline", result["error"])
        self.assertLess(time.monotonic()-started, 1.5)
        result = self.command("import sys; print('diagnostic',file=sys.stderr); sys.exit(7)")
        self.assertEqual(result["returncode"], 7)
        self.assertIn("diagnostic", result["stderr"])
        result = self.command("import os; os.write(1,b'x'*200000)")
        self.assertIn("output limit", result["error"])
        self.assertLessEqual(len(result["stdout"]), F.MAX_OUTPUT)

    def test_missing_binary_and_expired_budget_fail(self):
        result = F.run_command([str(self.directory/"missing.exe")], F.Budget(2), 1, self.directory)
        self.assertIn("error", result)
        with self.assertRaisesRegex(F.Failure, "budget exhausted"):
            F.run_command([sys.executable], F.Budget(1, time.monotonic()-2), 1, self.directory)

    def test_production_command_fails_closed_without_launch_or_overwrite(self):
        target = self.directory/"report.json"
        target.write_text("untouched")
        result = subprocess.run([sys.executable, F.__file__, "--native-binary", sys.executable,
                                 "--optimize-binary", sys.executable, "--output", str(target)],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        self.assertIn("Unsupported", report["error"])
        self.assertEqual([case["case"] for case in report["cases"]], F.REQUIRED)
        self.assertTrue(all(case["correctness"] == "not_run" for case in report["cases"]))
        self.assertEqual(target.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
