#!/usr/bin/env python3
"""Focused driver integration checks, not a timed performance comparison.

Build first with build_configured_benchmark.py. Tiny cover/rank fixtures mirror
the existing native_lp/native_branching tests; the independent exhaustive
oracle below also checks every returned original witness and global optimum.
"""
import itertools
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BINARY = Path(os.environ.get('CONFIGURED_BENCHMARK_BINARY',
                            ROOT/'build/configured-bench/optimize-configured-benchmark'))
ROUTES = ('native', 'lp-root', 'lp-cuts', 'lp-updated', 'dfs-reliability',
          'lp-reliability', 'lp-reliability-neighborhood')


class ConfiguredBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BINARY.is_file():
            raise RuntimeError('Build the configured benchmark driver first')

    def invoke(self, text, route, kind='binary', seconds='1', success=True):
        with tempfile.TemporaryDirectory(prefix='configured-benchmark-test-') as tmp:
            source = Path(tmp)/'input.txt'
            source.write_text(text)
            run = subprocess.run([str(BINARY), '--input', str(source), '--kind', kind,
                                  '--route', route, '--seconds', seconds],
                                 capture_output=True, text=True, timeout=3)
        if not success:
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertEqual(run.stdout, '')
            return
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['route'], route)
        self.assertEqual(result['kind'], kind)
        self.assertEqual(result['status'], 'optimal', result['message'])
        self.assertTrue(result['has_solution'])
        self.assertTrue(result['solution_validated'])
        self.assertFalse(result['start_submitted'])
        self.assertEqual(result['guarantee'], 'exact')
        self.assertEqual(result['objective'], result['best_bound'])
        self.assertEqual(result['absolute_gap'], 0)
        self.assertEqual(result['relative_gap'], 0)
        self.assertGreaterEqual(result['solve_seconds'], result['backend_solve_seconds'])
        self.assertGreaterEqual(result['driver_seconds'], result['solve_seconds'])
        config = result['algorithm_configuration']
        lp = route.startswith('lp-')
        reliability = 'reliability' in route
        covers = lp and route != 'lp-root'
        neighborhood = route.endswith('-neighborhood')
        self.assertEqual(config['checked_lp'], lp)
        self.assertEqual(config['root_cover_cuts'], covers)
        self.assertEqual(config['binary_reliability'], reliability)
        self.assertEqual(config['neighborhoods'], neighborhood)
        self.assertEqual(config['knapsack_dp_eligible_route'], not lp)
        self.assertFalse(config['presolve'])
        self.assertEqual(result['relaxation']['root_cover']['requested'], covers)
        self.assertEqual(result['branching']['requested'], reliability)
        self.assertEqual(result['neighborhood']['requested'], neighborhood)
        expected_backend = 'Gecode native'
        if reliability:
            expected_backend += ' frontier'
        if lp:
            expected_backend += ' + checked LP'
            self.assertEqual(config['bound_change_interval'],
                             1 if route in ('lp-root', 'lp-cuts') else 4)
        if neighborhood:
            expected_backend += ' + BinaryHamming'
        self.assertEqual(result['backend'], expected_backend)
        if reliability:
            self.assertEqual(result['budget_nodes'], result['nodes'] +
                             result['branching']['probe_status_calls'] +
                             result['neighborhood']['status_attempts'])
            self.assertLessEqual(result['peak_open_nodes'], config['max_open_nodes'])
        else:
            self.assertIsNone(result['nodes'])
        if neighborhood:
            self.assertEqual(config['neighborhood_settings']['radius'], 4)
            self.assertEqual(config['neighborhood_settings']['time_limit_seconds'], 0.05)
            self.assertLessEqual(result['neighborhood']['attempts'], 1)
        if not lp:
            self.assertEqual(result['relaxation']['lp_calls'], 0)
        self.assertLessEqual(result['branching']['probe_lp_calls'], result['relaxation']['lp_calls'])
        self.assertLessEqual(result['relaxation']['root_cover']['lp_calls'], result['relaxation']['lp_calls'])
        self.assertEqual(len(result['full_values']), result['model_columns'])
        return result

    def test_cover_and_reliability_routes(self):
        # Existing root-cover fixture: min -2x-2y subject to 3x+3y <= 5.
        # Stored all-ones legacy start is deliberately infeasible and discarded.
        cover = '2 1\n-2 -2\n-5 2 0 -3 1 -3\nincumbent 1\n1 1\n'
        feasible = [p for p in itertools.product((0, 1), repeat=2) if 3*sum(p) <= 5]
        optimum = min(-2*sum(p) for p in feasible)
        # Existing unconstrained rank fixture provokes real reliability probes.
        rank = '3 0\n1 4 2\nincumbent 1\n1 1 1\n'
        for route in ROUTES:
            with self.subTest(route=route, model='cover'):
                result = self.invoke(cover, route)
                self.assertIn(tuple(result['assignment']), feasible)
                self.assertEqual(result['objective'], optimum)
                self.assertEqual(result['objective'], -2*sum(result['assignment']))
                if route.startswith('lp-'):
                    self.assertGreater(result['relaxation']['lp_calls'], 0)
                if route.startswith('lp-') and route != 'lp-root':
                    self.assertGreater(result['relaxation']['root_cover']['cuts'], 0)
            with self.subTest(route=route, model='rank'):
                result = self.invoke(rank, route)
                self.assertEqual(result['assignment'], [0, 0, 0])
                self.assertEqual(result['objective'], 0)
                if route == 'dfs-reliability':
                    self.assertGreater(result['branching']['probe_status_calls'], 0)
                    self.assertGreater(result['branching']['manual_splits'], 0)

    def test_global_witnesses(self):
        for kind, n in (('native_tsp', 3), ('weighted_queens', 4)):
            costs = [[(i*7+j*3+i*j) % 13 + 1 for j in range(n)] for i in range(n)]
            text = f'{kind} {n} 0 {n}\n' + ' '.join(map(str, sum(costs, [])))
            text += '\n' + ' '.join(['0']*n) + '\n'
            feasible = []
            for p in itertools.permutations(range(n)):
                if kind == 'native_tsp':
                    seen, node = set(), 0
                    for _ in range(n):
                        seen.add(node)
                        node = p[node]
                    valid = len(seen) == n and node == 0
                else:
                    valid = len({p[i]+i for i in range(n)}) == n and len({p[i]-i for i in range(n)}) == n
                if valid:
                    feasible.append(p)
            cost = lambda p: sum(costs[i][int(p[i])] for i in range(n))
            optimum = min(map(cost, feasible))
            for route in ROUTES:
                with self.subTest(kind=kind, route=route):
                    result = self.invoke(text, route, kind)
                    self.assertIn(tuple(result['assignment']), feasible)
                    self.assertEqual(result['objective'], optimum)
                    self.assertEqual(result['objective'], cost(result['assignment']))

    def test_reject_invalid_options_and_inputs(self):
        valid = '2 1\n-2 -2\n-5 2 0 -3 1 -3\nincumbent 0\n'
        for seconds in ('0', '-1', '10.01', 'nan', 'inf', '1junk'):
            with self.subTest(seconds=seconds):
                self.invoke(valid, 'native', seconds=seconds, success=False)
        self.invoke(valid, 'everything', success=False)
        self.invoke(valid, 'native', kind='unsupported', success=False)
        self.invoke(valid + 'trailing\n', 'native', success=False)
        self.invoke(valid.replace('0 -3 1 -3', '1 -3 0 -3'), 'native', success=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
