"""Identical native evaluator; D calibration frozen from selection only."""
import argparse
import json
from pathlib import Path
import time
import murmur_phase_evaluate as evaluation
from murmur_data import ROOT, digest, save

evaluation.OUTPUT = ROOT / 'generated/murmur-phase-d'
evaluation.RESULTS = ROOT / 'results/murmur-phase-d'
evaluation.FREEZE = ROOT / 'murmur-phase-d-freeze.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['freeze', 'selection', 'calibration', 'test']); a = p.parse_args()
    if a.action == 'freeze':
        evaluation.freeze(); data = json.loads(evaluation.FREEZE.read_text())
        for name in ['murmur-freeze.json', 'murmur-phase-a-freeze.json']:
            path = ROOT / name
            for source, expected in json.loads(path.read_text())['sha256'].items():
                assert digest(ROOT.parent.parent / source) == expected; data['sha256'][source] = expected
            data['sha256'][str(path.relative_to(ROOT.parent.parent))] = digest(path)
        for path in [Path(__file__), ROOT / 'murmur_phase_calibrate.py', ROOT / 'results/murmur-phase-a/selection-predictions.json', ROOT / 'results/murmur-phase-a/selection-summary.json']:
            data['sha256'][str(path.resolve().relative_to(ROOT.parent.parent.resolve()))] = digest(path)
        data.update(time=time.time(), candidate='D: alpha.025 conservative unknown prior, chosen solely from original50selection groups. Reused development, not independent validation.')
        save(evaluation.FREEZE, data); print('Completed D freeze with original/A lineage and selection inputs.')
    else: evaluation.evaluate(a.action)
