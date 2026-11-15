"""Use the identical frozen evaluator with candidate B's isolated paths."""
import argparse
import json
from pathlib import Path
import time

import murmur_phase_evaluate as evaluation
from murmur_data import ROOT, digest, save

evaluation.OUTPUT = ROOT / 'generated/murmur-phase-b'
evaluation.RESULTS = ROOT / 'results/murmur-phase-b'
evaluation.FREEZE = ROOT / 'murmur-phase-b-freeze.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['freeze', 'selection', 'calibration', 'test']); a = p.parse_args()
    if a.action == 'freeze':
        evaluation.freeze()
        # Complete this new freeze with the ensemble exporter/wrapper and all lineage inputs.
        # No evaluation or new annotation access occurs until this action completes.
        data = json.loads(evaluation.FREEZE.read_text())
        for name in ['murmur-freeze.json', 'murmur-phase-a-freeze.json']:
            path = ROOT / name; prior = json.loads(path.read_text())
            for source, expected in prior['sha256'].items():
                assert digest(ROOT.parent.parent / source) == expected; data['sha256'][source] = expected
            data['sha256'][str(path.relative_to(ROOT.parent.parent))] = digest(path)
        for path in [Path(__file__), ROOT / 'murmur_phase_ensemble.py']:
            data['sha256'][str(path.resolve().relative_to(ROOT.parent.parent.resolve()))] = digest(path)
        data.update(time=time.time(), candidate='B: onefixed50/50probabilityensemble, selectedusingdevelopmentonly. No new independentvalidation claim.')
        save(evaluation.FREEZE, data)
        print('Completed candidate B freeze and verified all baseline/phase lineage inputs.')
    else: evaluation.evaluate(a.action)
