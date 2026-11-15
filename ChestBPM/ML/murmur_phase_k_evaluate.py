"""Identical native evaluator; K freezes selection-only decision temperature and lineage."""
import argparse
import json
from pathlib import Path
import time
import murmur_phase_evaluate as evaluation
from murmur_data import ROOT,digest,save

evaluation.OUTPUT=ROOT/'generated/murmur-phase-k'
evaluation.RESULTS=ROOT/'results/murmur-phase-k'
evaluation.FREEZE=ROOT/'murmur-phase-k-freeze.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','selection','calibration','test']);a=p.parse_args()
    if a.action=='freeze':
        evaluation.freeze();data=json.loads(evaluation.FREEZE.read_text())
        for name in ['murmur-freeze.json','murmur-phase-j-freeze.json']:
            path=ROOT/name
            for source,expected in json.loads(path.read_text())['sha256'].items():
                assert digest(ROOT.parent.parent/source)==expected;data['sha256'][source]=expected
            data['sha256'][str(path.relative_to(ROOT.parent.parent))]=digest(path)
        for path in [Path(__file__),ROOT/'murmur_temperature_model.py']:
            data['sha256'][str(path.resolve().relative_to(ROOT.parent.parent.resolve()))]=digest(path)
        data.update(time=time.time(),candidate='K: J plus decision temperature chosen from selection50only before Kcalibration/test evaluation. Reuseddevelopment,notindependentvalidation.')
        save(evaluation.FREEZE,data);print('Completed K freeze with J/C/original lineage.')
    else:evaluation.evaluate(a.action)
