#!/usr/bin/env python3
"""Compatibility/prefix checks and independent feasible witnesses; no solves."""
import copy
import unittest
import final_instances as generator


class FinalInstances(unittest.TestCase):
    def test_all_previous_inputs_unchanged(self):
        for family, (low, high) in generator.legacy.BOUNDS.items():
            for variant in (('uncorrelated', 'correlated') if family == 'knapsack' else ('single',)):
                for size in range(low, high + 1):
                    old = generator.legacy.make(family, size, variant)
                    new = generator.make(family, size, variant)
                    self.assertEqual(old, new)
                    self.assertEqual(generator.legacy.encode_txt(old), generator.encode_txt(new))

    def test_extension_prefixes(self):
        for family, (_, high) in generator.legacy.BOUNDS.items():
            for variant in (('uncorrelated', 'correlated') if family == 'knapsack' else ('single',)):
                a, b, c = (generator.make(family, n, variant) for n in (high, high + 1, high + 2))
                for small, large in ((a, b), (b, c)):
                    p, q = small['parameters'], large['parameters']
                    if family == 'knapsack':
                        self.assertEqual(p['weights'][0], q['weights'][0][:small['n']])
                        self.assertEqual(p['profits'], q['profits'][:small['n']])
                    elif family == 'assignment':
                        n = p['size']; self.assertEqual(p['costs'], [r[:n] for r in q['costs'][:n]])
                    elif family == 'facility_location':
                        n = p['facilities']; self.assertEqual(p['opening_costs'], q['opening_costs'][:n])
                        self.assertEqual(p['assignment_costs'], [r[:n] for r in q['assignment_costs'][:2*n]])
                    elif family == 'bin_packing':
                        self.assertEqual(p['weights'], q['weights'][:p['items']])
                    elif family == 'production':
                        n = p['periods']; self.assertEqual(p['demands'], q['demands'][:n])
                        self.assertEqual(p['production_costs'], q['production_costs'][:n])
                        self.assertEqual(p['storage'], q['storage']); self.assertEqual(p['holding_cost'], q['holding_cost'])
                    else:
                        n = p['size']; self.assertEqual(small['data'], [r[:n] for r in large['data'][:n]])
                self.assertEqual(c, generator.make(family, high + 2, variant))

    def test_independent_larger_witnesses(self):
        for family in ('knapsack', 'assignment', 'facility_location', 'bin_packing', 'production'):
            high = generator.legacy.BOUNDS[family][1]
            for variant in (('uncorrelated', 'correlated') if family == 'knapsack' else ('single',)):
                model = generator.make(family, high + 3, variant)
                p = model['parameters']; x = [0] * model['n']
                if family == 'assignment':
                    for i in range(p['size']): x[i*p['size'] + i] = 1
                elif family == 'facility_location':
                    x[:p['facilities']] = [1] * p['facilities']
                    for i in range(p['customers']): x[p['facilities'] + i*p['facilities']] = 1
                elif family == 'bin_packing':
                    loads = []
                    for i in sorted(range(p['items']), key=lambda i: -p['weights'][i]):
                        b = next((b for b, load in enumerate(loads) if load+p['weights'][i] <= p['capacity']), len(loads))
                        if b == len(loads): loads.append(0)
                        loads[b] += p['weights'][i]; x[i*p['bins'] + b] = 1
                    self.assertLessEqual(len(loads), p['bins'])
                    for b in range(len(loads)): x[p['items']*p['bins'] + b] = 1
                elif family == 'production':
                    for t, demand in enumerate(p['demands']): x[t*8 + demand] = 1
                expected = sum(a*b for a, b in zip(model['c'], x))
                self.assertTrue(all(sum(value*x[j] for j, value in row['a']) >= row['b'] for row in model['rows']))
                checked = generator.validate_assignment(model, x)
                self.assertTrue(checked['valid'], checked)
                self.assertEqual(checked['objective'], expected)
                damaged = copy.deepcopy(model); damaged['c'][0] += 1
                self.assertFalse(generator.validate_assignment(damaged, x)['valid'])


if __name__ == '__main__':
    unittest.main()
