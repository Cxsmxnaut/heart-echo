"""Freeze, export and check the two-stage candidate with the actual app reader."""
import argparse
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf
import torch

from two_stage_models import make_clinical, PhoneAdapter, AdaptedClinical, WaveClassifier, sha
from train_phone_adapter import read_records, views_for
from murmur_focus_metrics import aggregate, promotion_checks

HERE = Path(__file__).resolve().parent


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def files(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def main(args):
    import coremltools as ct
    os.umask(0o077); torch.set_num_threads(2); torch.manual_seed(20261119)
    run = args.run.resolve(); source = args.clinical_dir.resolve()
    if (run / 'native-comparison.json').exists():
        raise ValueError('Preserve completed native results')
    complete = json.loads((run / 'complete.json').read_text())
    assert complete['status'] == 'adapter_training_complete'
    protocol = json.loads((run / 'protocol.json').read_text())
    name = protocol['clinical_model']
    weights = source / name / 'Clinical.pt'
    assert sha(weights) == protocol['clinical_weights_sha256']
    assert sha(run / 'PhoneAdapter.pt') == complete['proof']['adapter_sha256']
    assert sha(run / 'final-predictions.json') == complete['predictions_sha256']
    feature_predictions = json.loads((run / 'final-predictions.json').read_text())
    assert sha(args.profile) == protocol['profile_sha256']
    baseline_directory = HERE.parent / 'HeartEcho/Models'
    expected = json.loads((HERE / 'results/murmur-focus-baseline-freeze.json').read_text())
    assert files(baseline_directory / 'Murmur.mlpackage') == expected['model_files']
    rows = [r for r in read_records() if r['role'] in ['selection', 'calibration']]
    views = views_for(rows, json.loads(args.profile.read_text()))
    examples = [torch.randn(1, 1, 8000) * scale for scale in [0., .0001, .03, .3]]
    for domain in views:
        for target in [0, 1, 2]:
            item = next(item for item in views[domain] if item['record']['target'] == target)
            examples.append(torch.from_numpy(item['wave'][:8000].copy())[None, None])
    model_locations = {'app-M': baseline_directory}
    conversions = {}
    for mode in ['clinical-only', 'adapted']:
        clinical = make_clinical(name)
        clinical.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
        if mode == 'adapted':
            adapter = PhoneAdapter(); adapter.load_state_dict(torch.load(run / 'PhoneAdapter.pt', map_location='cpu', weights_only=True))
            clinical = AdaptedClinical(clinical, adapter)
        model = WaveClassifier(clinical).eval()
        folder = run / mode; folder.mkdir(exist_ok=True)
        package = folder / 'Murmur.mlpackage'
        if not package.exists():
            converted = ct.convert(torch.jit.trace(model, examples[2]),
                inputs=[ct.TensorType(name='waveform', shape=(1, 1, 8000))],
                outputs=[ct.TensorType(name='probabilities')],
                minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
            converted.author = 'Heart Echo research; PANNs/TorchVision public model initialization'
            converted.short_description = 'Two-stage research candidate; phone accuracy unestablished.'
            converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1', labels='Absent,Present,Unknown',
                dataset='https://doi.org/10.13026/tshs-mw03', model_revision='Two-stage V10 ' + mode + ' · 2026-11-15',
                clinical_weights_sha256=sha(weights))
            converted.save(str(package))
        converted = ct.models.MLModel(str(package)); errors = []
        for wave in examples:
            with torch.inference_mode():
                expected_p = model(wave).numpy()
            actual = converted.predict({'waveform': wave.numpy()})['probabilities']
            errors.append(float(np.max(np.abs(expected_p - actual))))
        assert max(errors) < .001, (mode, max(errors))
        conversions[mode] = dict(examples=len(examples), maximum_probability_difference=max(errors), passed=True)
        model_locations[mode] = folder
        print(json.dumps({'converted': mode, **conversions[mode]}), flush=True)
    requests = {'clean': [], 'styled': []}
    evaluation_audio = run / 'native-evaluation-audio'; evaluation_audio.mkdir(exist_ok=True)
    for domain, items in views.items():
        for item in items:
            r = item['record']
            if domain == 'clean':
                path = HERE.parent / 'ChestBPM/ML/cache/circor' / r['file']
            else:
                path = evaluation_audio / (r['record'] + '.wav')
                sf.write(path, item['wave'], 2000, subtype='PCM_32')
            requests[domain].append({'id': r['record'], 'path': str(path)})
    probe = run / 'native-probe'
    subprocess.run(['swiftc', '-O', '-module-cache-path', '/tmp/heartecho-two-stage-modules',
                    str(HERE.parent / 'HeartEcho/Engine/MurmurAnalysis.swift'),
                    str(HERE.parent / 'ChestBPM/Tools/MurmurProbe.swift'), '-o', str(probe)], check=True)
    freeze = dict(packages={mode: files(folder / 'Murmur.mlpackage') for mode, folder in model_locations.items()},
                  sources={p.name: sha(p) for p in [Path(__file__), HERE / 'two_stage_models.py',
                           HERE.parent / 'HeartEcho/Engine/MurmurAnalysis.swift', HERE / 'murmur_focus_metrics.py']},
                  probe_sha256=sha(probe), threshold=.60,
                  input_sha256={domain: {r['id']: sha(r['path']) for r in items} for domain, items in requests.items()})
    save(run / 'native-freeze.json', freeze)
    predictions = {}
    for domain, items in requests.items():
        request_file = run / ('native-' + domain + '-requests.json'); save(request_file, items)
        predictions[domain] = {}
        for mode, folder in model_locations.items():
            result = subprocess.run([str(probe), str(request_file), str(folder)], capture_output=True, text=True, check=True)
            values = {r['id']: r for r in map(json.loads, result.stdout.splitlines())}
            assert set(values) == {r['record'] for r in rows}
            for r in rows:
                assert abs(values[r['record']]['reading']['seconds'] - r['samples'] / 2000) < .0005
            predictions[domain][mode] = values
            print(json.dumps({'native_complete': mode, 'domain': domain, 'records': len(values)}), flush=True)
    save(run / 'native-predictions.json', predictions)
    report = dict(roles={}, conversions=conversions, clinical_model=name,
                  evidence='Reused public development and simulated phone input; not independent clinical phone validation.',
                  app_updated=False, regression_scored=False, clinical_weights_frozen_during_adaptation=True)
    aligned_errors = {}
    for domain, values in predictions.items():
        aligned_errors[domain] = {}
        for mode, guesses in values.items():
            key = name if mode == 'clinical-only' else mode
            maximum = max(float(np.max(np.abs(
                np.asarray(guesses[r['record']]['reading']['probabilities']) -
                np.asarray(feature_predictions[r['role']][domain][key][r['record']]['reading']['probabilities']))))
                for r in rows)
            assert maximum < .001, (domain, mode, maximum)
            aligned_errors[domain][mode] = maximum
    report['maximum_aligned_mean_probability_differences'] = aligned_errors
    passed, added = True, 0
    for role in ['selection', 'calibration']:
        cohort = [r for r in rows if r['role'] == role]
        report['roles'][role] = {}
        for domain, values in predictions.items():
            results = {mode: aggregate(cohort, p) for mode, p in values.items()}
            checks = promotion_checks(results['app-M'], results['adapted'])
            passed &= all(checks.values())
            added += results['adapted']['recordings']['detected_positive'] - results['app-M']['recordings']['detected_positive']
            report['roles'][role][domain] = dict(results=results, strict_checks=checks)
    assert files(baseline_directory / 'Murmur.mlpackage') == expected['model_files']
    report.update(development_gate_passed=bool(passed and added > 0), app_model_unchanged=True,
                  decision='eligible_for_frozen_regression_only' if passed and added > 0
                  else 'retain_app_M; two-stage candidate fails strict native development checks')
    save(run / 'native-comparison.json', report)
    print(json.dumps({'decision': report['decision']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--clinical-dir', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    main(parser.parse_args())
