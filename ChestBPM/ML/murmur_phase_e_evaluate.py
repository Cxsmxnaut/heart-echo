"""Identical native evaluator; candidate E uses verified native development inputs."""
import argparse
import json
from pathlib import Path
import time
import murmur_phase_evaluate as evaluation
from murmur_data import ROOT, digest, save

evaluation.OUTPUT=ROOT/'generated/murmur-phase-e'
evaluation.RESULTS=ROOT/'results/murmur-phase-e'
evaluation.FREEZE=ROOT/'murmur-phase-e-freeze.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','selection','calibration','test']);a=p.parse_args()
    if a.action=='freeze':
        evaluation.freeze();data=json.loads(evaluation.FREEZE.read_text())
        for name in ['murmur-freeze.json','murmur-phase-a-freeze.json']:
            path=ROOT/name
            for source,expected in json.loads(path.read_text())['sha256'].items():
                assert digest(ROOT.parent.parent/source)==expected;data['sha256'][source]=expected
            data['sha256'][str(path.relative_to(ROOT.parent.parent))]=digest(path)
        for path in [Path(__file__),ROOT/'murmur_native_model.py',ROOT/'murmur_native_data.py',ROOT/'generated/murmur-native-development/manifest.json',ROOT.parent/'Tools/MurmurAudioExport.swift']:
            data['sha256'][str(path.resolve().relative_to(ROOT.parent.parent.resolve()))]=digest(path)
        data.update(time=time.time(),candidate='E: explicit phase model with exact native development resampling/gates and originalv1 parity checked on367records. Reused development, not independent validation.')
        save(evaluation.FREEZE,data);print('Completed E freeze including native data provenance and original/A lineage.')
    else:evaluation.evaluate(a.action)
