"""Identical native evaluator; M freezes positive-evidence fusion and all lineage."""
import argparse
import json
from pathlib import Path
import time
import murmur_phase_evaluate as evaluation
from murmur_data import ROOT,digest,save

evaluation.OUTPUT=ROOT/'generated/murmur-phase-m'
evaluation.RESULTS=ROOT/'results/murmur-phase-m'
evaluation.FREEZE=ROOT/'murmur-phase-m-freeze.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','selection','calibration','test']);a=p.parse_args()
    if a.action=='freeze':
        evaluation.freeze();data=json.loads(evaluation.FREEZE.read_text())
        for name in ['murmur-freeze.json','murmur-phase-k-freeze.json']:
            path=ROOT/name
            for source,expected in json.loads(path.read_text())['sha256'].items():
                assert digest(ROOT.parent.parent/source)==expected;data['sha256'][source]=expected
            data['sha256'][str(path.relative_to(ROOT.parent.parent))]=digest(path)
        for path in [Path(__file__),ROOT/'murmur_additive_model.py',ROOT/'test_murmur_additive.py',ROOT/'murmur_phase_accept.py']:
            data['sha256'][str(path.resolve().relative_to(ROOT.parent.parent.resolve()))]=digest(path)
        data.update(time=time.time(),candidate='M: fixed phaseC/Kmean positiveevidence addedtooriginalv1, cannotincreaseAbsentconfidence. Reuseddevelopment; noindependentvalidationclaim.')
        save(evaluation.FREEZE,data);print('Completed M freeze with K/J/C/original lineage.')
    else:evaluation.evaluate(a.action)
