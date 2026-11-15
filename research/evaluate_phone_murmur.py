"""Export the fixed phone-style experiment and compare the actual native reader.

No old final-test/PASCAL scoring or automatic app promotion. Private recordings
provided training style, so these results never establish real-phone accuracy.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
import torch

HERE = Path(__file__).resolve().parent
ML = HERE.parent / 'ChestBPM/ML'
sys.path.insert(0, str(ML))
from murmur_additive_model import AdditiveModel
from murmur_model import spectrum, HOP, FRAMES, windows
from murmur_native_data import CACHE
from murmur_data import digest, save
from native_murmur_gate import native
from murmur_focus_metrics import aggregate, promotion_checks
from phone_style import transform, stable_seed
from train_phone_murmur import shipping_hashes, feature_outputs

NAMES = ['probabilities', 'phase_probabilities', 'murmur_timing']


def package_hashes(directory):
    return {str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def main(run):
    import coremltools as ct
    os.umask(0o077)
    run = run.resolve()
    if (run / 'native-comparison.json').exists():
        raise ValueError('Native comparison already exists; preserve its first result')
    complete = json.loads((run / 'complete.json').read_text())
    freeze = json.loads((run / 'evaluation-freeze.json').read_text())
    assert digest(run / 'protocol.json') == freeze['protocol_sha256']
    assert digest(run / 'data.json') == freeze['data_sha256']
    original = shipping_hashes()
    baseline_freeze = json.loads((HERE / 'results/murmur-focus-baseline-freeze.json').read_text())
    assert package_hashes(HERE.parent / 'HeartEcho/Models/Murmur.mlpackage') == baseline_freeze['model_files']
    torch.manual_seed(2026111502); torch.set_num_threads(2)
    profile = json.loads((run / 'phone-profile.json').read_text())
    rows = [r for r in json.loads((run / 'data.json').read_text()) if r['role'] in ['selection', 'calibration']]
    audio = run / 'evaluation-audio'; audio.mkdir(exist_ok=True)
    requests = {'clean': [], 'styled': []}
    examples = [torch.randn(1, 1, 8000) * scale for scale in [0., .0001, .03, .3]]
    examples_taken = set()
    for r in rows:
        raw = CACHE / 'audio' / (r['record'] + '.f32')
        x = np.fromfile(raw, dtype='<f4')
        y = transform(x, profile, np.random.default_rng(stable_seed('phone-style:' + r['record'])))
        expected = np.load(run / 'features' / (r['record'] + '.npy'))
        assert np.array_equal(spectrum(y), expected), r['record']
        path = audio / (r['record'] + '.wav')
        # AVAudioFile on this Mac reads some IEEE-float WAVs short. Signed PCM32
        # preserves these Float32 waveforms to <1e-9 and retains every frame.
        sf.write(path, y, 2000, subtype='PCM_32')
        requests['clean'].append({'id': r['record'], 'path': str(ML / 'cache/circor' / r['file'])})
        requests['styled'].append({'id': r['record'], 'path': str(path)})
        key = (r['role'], r['target'])
        if key not in examples_taken:
            examples_taken.add(key)
            examples.extend([torch.from_numpy(wave[:8000].copy())[None, None] for wave in [x, y]])
    locations = {'baseline': HERE.parent / 'HeartEcho/Models'}
    conversions = {}
    for arm in ['clean-control', 'phone-style']:
        location = run / arm; weights = location / 'Murmur.pt'
        assert digest(weights) == complete['models'][arm]['weights_sha256'] == freeze['models'][arm]['weights_sha256']
        model = AdditiveModel(); model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True)); model.eval()
        package = location / 'Murmur.mlpackage'
        if not package.exists():
            converted = ct.convert(torch.jit.trace(model, examples[2]),
                inputs=[ct.TensorType(name='waveform', shape=(1, 1, 8000))],
                outputs=[ct.TensorType(name=n) for n in NAMES],
                minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
            converted.author = 'Heart Echo local public-data research'
            converted.short_description = 'Phone-style adaptation experiment; clinical phone accuracy unestablished.'
            converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',
                labels='Absent,Present,Unknown', phase_labels='noise,S1,systole,S2,diastole',
                model_revision='Phone-style V9 ' + arm + ' · 2026-11-15', weights_sha256=digest(weights))
            converted.save(str(package))
        converted = ct.models.MLModel(str(package))
        errors = []
        for x in examples:
            with torch.inference_mode():
                expected = model(x)
            actual = converted.predict({'waveform': x.numpy()})
            errors.append([float(np.max(np.abs(value.numpy() - actual[name])))
                           for value, name in zip(expected, NAMES)])
        maximum = np.max(errors, axis=0).tolist()
        assert max(maximum) < .001, (arm, maximum)
        conversions[arm] = dict(examples=len(examples), maximum_differences=maximum, passed=True)
        locations[arm] = location
        print(json.dumps({'converted': arm, **conversions[arm]}), flush=True)
    save(run / 'native-conversion.json', conversions)
    save(run / 'native-evaluation-freeze.json', dict(
        packages={arm: package_hashes(path / 'Murmur.mlpackage') for arm, path in locations.items()},
        evaluator_sha256=digest(Path(__file__)), reader_sha256=digest(HERE.parent / 'HeartEcho/Engine/MurmurAnalysis.swift'),
        probe_sha256=digest(HERE / 'generated/murmur-probe'),
        metrics_sha256=digest(HERE / 'murmur_focus_metrics.py'), threshold=.60,
        comparison_data_sha256=digest(run / 'data.json'),
        input_file_sha256={domain: {r['id']: digest(Path(r['path'])) for r in items}
                           for domain, items in requests.items()}))
    outputs = {}
    for domain in ['clean', 'styled']:
        outputs[domain] = {}
        for arm, location in locations.items():
            outputs[domain][arm] = native(location, requests[domain], 'phone-v9-' + domain + '-' + arm)
            assert set(outputs[domain][arm]) == {r['record'] for r in rows}
            for r in rows:
                actual = outputs[domain][arm][r['record']]['reading']['seconds']
                assert abs(actual - r['samples'] / 2000) < .0005, (domain, r['record'], actual)
            print(json.dumps({'native_complete': arm, 'domain': domain, 'records': len(rows)}), flush=True)
    save(run / 'native-predictions.json', outputs)
    report = dict(roles={}, conversion=conversions, regression_scored=False, app_changed=False,
                  private_phone_accuracy='Unavailable: no independent clinician reference labels',
                  limitations=json.loads((run / 'protocol.json').read_text())['limitations'])
    aligned_errors = {}
    for arm in locations:
        weights = (ML / 'generated/murmur-phase-m/Murmur.pt' if arm == 'baseline'
                   else run / arm / 'Murmur.pt')
        model = AdditiveModel(); model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True)); model.eval()
        aligned_errors[arm] = {}
        for domain in ['clean', 'styled']:
            maximum = 0.
            for r in rows:
                path = ((CACHE / 'features') if domain == 'clean' else (run / 'features')) / (r['record'] + '.npy')
                features = np.load(path)
                usable = set(r['clean_usable' if domain == 'clean' else 'styled_usable'])
                starts = [s // HOP for s in windows(r['samples']) if s // HOP in usable]
                if starts:
                    x = torch.from_numpy(np.stack([features[:, s:s + FRAMES] for s in starts]))
                    with torch.inference_mode():
                        p = feature_outputs(model, x)[0].numpy().mean(0)
                else:
                    p = np.array([0., 0., 1.])
                q = outputs[domain][arm][r['record']]['reading']['probabilities']
                maximum = max(maximum, float(np.max(np.abs(p - q))))
            assert maximum < .001, (arm, domain, maximum)
            aligned_errors[arm][domain] = maximum
    report['maximum_aligned_mean_probability_differences'] = aligned_errors
    report['all_native_read_lengths_matched'] = True
    passed, added = True, 0
    for role in ['selection', 'calibration']:
        cohort = [r for r in rows if r['role'] == role]
        report['roles'][role] = {}
        for domain in ['clean', 'styled']:
            results = {arm: aggregate(cohort, predictions) for arm, predictions in outputs[domain].items()}
            checks = promotion_checks(results['baseline'], results['phone-style'])
            passed &= all(checks.values())
            added += results['phone-style']['recordings']['detected_positive'] - results['baseline']['recordings']['detected_positive']
            report['roles'][role][domain] = dict(results=results, strict_candidate_checks=checks)
    assert shipping_hashes() == original
    report.update(development_gate_passed=bool(passed and added > 0), shipping_packages_unchanged=True,
                  decision='eligible_for_frozen_regression_only' if passed and added > 0
                  else 'retain_shipping_model; phone-style V9 fails native development checks')
    save(run / 'native-comparison.json', report)
    print(json.dumps({'decision': report['decision'], 'shipping_packages_unchanged': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    main(parser.parse_args().run)
