"""Identical native evaluator; candidate G freezes fixed evidence rule and lineage."""
import argparse
import json
from pathlib import Path
import time
import murmur_phase_evaluate as evaluation
from murmur_data import ROOT,digest,save

evaluation.OUTPUT=ROOT/'generated/murmur-phase-g'
evaluation.RESULTS=ROOT/'results/murmur-phase-g'
evaluation.FREEZE=ROOT/'murmur-phase-g-freeze.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','selection','calibration','test']);a=p.parse_args()
    if a.action=='freeze':
        evaluation.freeze();data=json.loads(evaluation.FREEZE.read_text())
        for name in ['murmur-freeze.json','murmur-phase-c-freeze.json']:
            path=ROOT/name
            for source,expected in json.loads(path.read_text())['sha256'].items():
                assert digest(ROOT.parent.parent/source)==expected;data['sha256'][source]=expected
            data['sha256'][str(path.relative_to(ROOT.parent.parent))]=digest(path)
        for path in [Path(__file__),ROOT/'murmur_evidence_model.py',ROOT/'test_murmur_evidence.py']:
            data['sha256'][str(path.resolve().relative_to(ROOT.parent.parent.resolve()))]=digest(path)
        data.update(time=time.time(),candidate='G: C with fixed.4murmur-evidence gate from training-only quantiles. No Gdev or oldtest outcomes used for knot.')
        save(evaluation.FREEZE,data);print('Completed G freeze with C/original lineage.')
    else:evaluation.evaluate(a.action)
