"""Tiny data-integrity tests, without training a policy or launching solvers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import analyze
import train_policy
import validate


def fixture(directory):
    records=[];inputs={};rows=[]
    for fold in range(3):
        identity='fixture_'+str(fold)
        instance={'id':identity,'family':'external_binary','kind':'binary','split':'dev','tier':'tiny','seed':1000+fold,
                  'n':2,'c':[1+fold,2+fold],'rows':[{'a':[[0,1],[1,1]],'b':1}],
                  'incumbent':[1,1],'incumbent_objective':3+2*fold}
        instance['reference']={'status':'optimal','objective':1+fold,'input_sha256':validate.input_hash(instance)}
        record={key:instance[key] for key in ('id','family','kind','split','tier','seed')}
        record.update(json=identity+'.json',txt=identity+'.txt');records.append(record)
        (directory/record['json']).write_text(json.dumps(instance))
        (directory/record['txt']).write_text(f'2 1\n{1+fold} {2+fold}\n1 2 0 1 1 1\nincumbent 1\n1 1\n')
        inputs[identity]={kind:analyze.sha(directory/record[kind]) for kind in ('json','txt')}
        for config,mode in [('stock','native'),('lp','lp')]:
            row={**{key:instance[key] for key in ('id','family','kind','split','tier','seed')},
                 'config':config,'mode':mode,'requested_mode':mode,'branching':'afc','repetition':0,
                 'status':'optimal','elapsed_ms':25,'process_wall_ms':28,'limit_ms':100,'warm':True,
                 'initial_objective':3+2*fold,'objective':1+fold,'assignment':[1,0],'improvements':[[20,1+fold]],
                 'objective_at_limit':1+fold,'completed_within_budget':True,'binary_sha256':'a'*64,
                 'reference_status':'optimal','reference_objective':1+fold,'features':train_policy.algebraic_features(instance)}
            row['validation']=validate.validate_result(instance,row);rows.append(row)
    manifest=directory/'manifest.json';manifest.write_text(json.dumps({'instances':records}))
    protocol={'limit_ms':100,'warm':1,'configs':{'stock':['binary','native','afc','native'],'lp':['binary','lp','afc','native']},
              'binaries':{'binary':'a'*64},'manifests':{str(manifest):analyze.sha(manifest)},'inputs':inputs,
              'split':'dev','repeats':1,'platform':'fixture','machine':'fixture','threads_per_search':1,
              'parallel_solver_runs':False,'highs_mip_used':False,'timing':'fixture'}
    runs=directory/'runs.jsonl';runs.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    metadata={'protocol':protocol,'completed':True,'expected_runs':6,'completed_runs':6}
    runs.with_suffix('.meta.json').write_text(json.dumps(metadata))
    return manifest,runs,rows,metadata


class TrainingIntegrityTests(unittest.TestCase):
    def test_audit_and_duplicate_files_preserve_one_sample_per_instance(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);manifest,runs,rows,metadata=fixture(directory)
            copied=directory/'copied.jsonl';copied.write_text(runs.read_text())
            copied.with_suffix('.meta.json').write_text(json.dumps(metadata))
            samples,provenance=train_policy.load_training_data([runs,copied],manifest,['stock','lp'])
            self.assertEqual(len(samples),3)
            self.assertEqual(provenance['duplicate_observations_dropped'],6)
            self.assertTrue(all(counts=={'stock':1,'lp':1} for counts in provenance['action_observation_counts'].values()))

    def test_repeated_action_trials_change_only_its_instance_median(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);manifest,runs,rows,metadata=fixture(directory)
            repeated=directory/'repeated.jsonl'
            for row in rows:row.update(elapsed_ms=40,process_wall_ms=45)
            repeated.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            repeated.with_suffix('.meta.json').write_text(json.dumps(metadata))
            samples,provenance=train_policy.load_training_data([runs,repeated],manifest,['stock','lp'])
            self.assertEqual(len(samples),3)
            self.assertTrue(all(counts=={'stock':2,'lp':2} for counts in provenance['action_observation_counts'].values()))

    def test_short_nan_and_mismatched_features_rejected(self):
        for features in ([],[0]*11,[float('nan')]*12,[0]*12):
            with self.subTest(features=features), tempfile.TemporaryDirectory() as name:
                directory=Path(name);manifest,runs,rows,_=fixture(directory)
                rows[0]['features']=features;runs.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaisesRegex(ValueError,'feature'):
                    train_policy.load_training_data([runs],manifest,['stock','lp'])

    def test_binary_hash_and_deadline_label_rejected(self):
        for change in ({'binary_sha256':'b'*64},{'completed_within_budget':False},{'mode':'lp','requested_mode':'lp'}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as name:
                directory=Path(name);manifest,runs,rows,_=fixture(directory)
                rows[0].update(change);runs.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaises(ValueError):train_policy.load_training_data([runs],manifest,['stock','lp'])

    def test_wrong_source_input_and_non_development_protocol_rejected(self):
        for scenario in ('input','split','budget'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as name:
                directory=Path(name);manifest,runs,rows,metadata=fixture(directory)
                if scenario=='input':metadata['protocol']['inputs']['fixture_0']['json']='b'*64
                elif scenario=='split':metadata['protocol']['split']='dev,test'
                else:metadata['protocol']['limit_ms']=200
                runs.with_suffix('.meta.json').write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):train_policy.load_training_data([runs],manifest,['stock','lp'])

    def test_fold_residues_and_coverage(self):
        records={str(i):{'family':'family','tier':'small','seed':1000+i} for i in range(3)}
        train_policy.check_folds(records)
        records['3']={'family':'family','tier':'small','seed':1003}
        with self.assertRaisesRegex(ValueError,'fold residue'):train_policy.check_folds(records)
        del records['3'];del records['2']
        with self.assertRaisesRegex(ValueError,'exactly three'):train_policy.check_folds(records)


if __name__=='__main__':unittest.main()
