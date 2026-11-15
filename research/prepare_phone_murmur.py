"""Create a private, reproducible phone-style CirCor development cache.

The user explicitly authorized using yesterday/today audio for style fitting.
No private clinical labels are created. Existing public person partitions remain.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
from scipy import signal
import soundfile as sf

HERE = Path(__file__).resolve().parent
ML = HERE.parent / 'ChestBPM/ML'
sys.path.insert(0, str(ML))
from murmur_model import spectrum, FRAMES, HOP, SAMPLES, banks
from murmur_data import digest, save
from murmur_phase_data import PHASE_MANIFEST
from murmur_native_data import CACHE
from phone_style import (RATE, fit_profile, transform, stable_seed, eligible_today,
                         assert_person_split)


def read_phone(path):
    x, rate = sf.read(path, dtype='float32', always_2d=True)
    # The model sees mono; files remain untouched at their original rate.
    x = x.mean(axis=1)
    divisor = math.gcd(rate, RATE)
    return signal.resample_poly(x, RATE // divisor, rate // divisor).astype(np.float32)


def usable_starts(x):
    starts = np.arange(0, len(x) - SAMPLES + 1, HOP)
    energy = np.r_[0., np.cumsum(x.astype(np.float64) ** 2)]
    clips = np.r_[0, np.cumsum(np.abs(x) >= .999)]
    good = ((energy[starts + SAMPLES] - energy[starts]) / SAMPLES >= .00002 ** 2)
    good &= (clips[starts + SAMPLES] - clips[starts]) / SAMPLES <= .01
    return np.flatnonzero(good).tolist()


def prepare(args):
    os.umask(0o077)
    out = args.output.resolve()
    if out.exists():
        raise ValueError('Run directory already exists; preserve it and use a new directory')
    if 'generated' not in out.relative_to(HERE).parts:
        raise ValueError('Private derivatives must stay under ignored research/generated/')
    out.mkdir(parents=True, mode=0o700)
    rows = [r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role'] != 'test']
    assert_person_split(rows)
    cached = json.loads((CACHE / 'manifest.json').read_text())
    assert cached['phase_manifest_sha256'] == digest(PHASE_MANIFEST)
    native = {r['record']: r for r in cached['records']}
    assert set(native) == {r['record'] for r in rows}
    protocol = dict(created_unix=time.time(), seed=20261115, threshold=.60,
                    public_dataset='CirCor DigiScope 1.0.3; existing development partitions only',
                    native_cache_sha256=digest(CACHE / 'manifest.json'),
                    phase_manifest_sha256=digest(PHASE_MANIFEST),
                    today_cohort_sha256=digest(args.today_cohort),
                    original_weights_sha256=digest(ML / 'generated/murmur-phase-m/Murmur.pt'),
                    source_sha256={p.name: digest(p) for p in [Path(__file__), HERE / 'phone_style.py',
                                   HERE / 'train_phone_murmur.py', ML / 'murmur_additive_model.py',
                                   ML / 'murmur_model.py', ML / 'murmur_timing_data.py',
                                   ML / 'murmur_phase_model.py', ML / 'murmur_timing_model.py',
                                   ML / 'murmur_phase_data.py', HERE / 'murmur_focus_metrics.py']},
                    phone_use='Unlabeled spectral/noise statistics only; no private murmur targets, '
                              'Watch labels, private inference-based labels or copied heartbeat noise.',
                    selection='Eight epochs per arm, 80 steps/epoch, identical M initialization, '
                              'AdamW lr2e-5 weight_decay.001, batch24:10Absent/8Present/2expertUnknown/'
                              '4syntheticUnknown. Both arms use paired clean and second-view label, '
                              'phase and timing losses plus .20 clean-teacher KL. Second view is '
                              'clean for control and phone-style for candidate. Select highest '
                              'minimum clean/style 3-class balanced recall on selection, then their '
                              'mean. Only epochs1..8 eligible; epoch0 is reported as baseline.',
                    promotion='Existing strict recording/person promotion checks on clean and '
                              'synthetic-style selection and calibration; require added positives. '
                              'No automatic replacement; all evidence remains reused development.',
                    limitations=['Unpaired single-person phone style is an approximation and can encode anatomy.',
                                 'Today audio already inspected and used for style: not an independent phone test.',
                                 'Synthetic noise may obscure faint murmurs despite 24-36dB SNR; no clinical label guarantee.',
                                 'No fresh clinical phone validation; do not tune thresholds or use old tests for selection.'])
    save(out / 'protocol.json', protocol)
    phone, noise, sources = [], [], []
    for r in eligible_today(json.loads(args.today_cohort.read_text())):
        path = args.today_cohort.parent / r['audio_file']
        assert digest(path) == r['sha256']
        phone.append(read_phone(path))
        sources.append(dict(day='today', purpose='unlabeled_spectrum', id=r['id'], sha256=digest(path)))
    yesterday = args.yesterday.resolve()
    summaries = json.loads((yesterday / 'v17-replay-report.json').read_text())
    requests = {r['id']: r for r in json.loads((yesterday / 'replay/audio-only-requests.json').read_text())}
    for r in summaries:
        if r['condition'] not in ('Quiet', 'Off chest'):
            continue
        path = Path(requests[r['id']]['path'])
        (phone if r['condition'] == 'Quiet' else noise).append(read_phone(path))
        sources.append(dict(day='yesterday', purpose='unlabeled_spectrum' if r['condition'] == 'Quiet'
                            else 'noise_power_only', id=r['id'], completed=r['completed'], sha256=digest(path)))
    # Fit source reference to training people ONLY, at most one recording per person.
    reference_records, used_groups = [], set()
    for target in (0, 1, 2):
        choices = sorted([r for r in rows if r['role'] == 'training' and r['target'] == target
                          and r['patient_target'] == target],
                         key=lambda r: stable_seed('reference:' + r['record']))
        chosen = []
        for r in choices:
            if r['group'] in used_groups:
                continue
            chosen.append(r); used_groups.add(r['group'])
            if len(chosen) == 30:
                break
        assert len(chosen) == 30
        reference_records.extend(chosen)
    public = []
    for r in reference_records:
        path = CACHE / 'audio' / (r['record'] + '.f32')
        assert digest(path) == native[r['record']]['native_audio_sha256']
        public.append(np.fromfile(path, dtype='<f4'))
    profile = fit_profile(public, phone, noise)
    profile.update(private_sources=sources, public_reference_records=[r['record'] for r in reference_records],
                   public_reference_people=len(used_groups), case_on_audio_used=False,
                   private_clinical_labels_created=False)
    save(out / 'phone-profile.json', profile)
    styled = out / 'features'; styled.mkdir()
    examples = out / 'examples'; examples.mkdir()
    prepared, exported = [], set()
    clean_shape, augmented_shape = [], []
    for index, r in enumerate(rows, 1):
        meta = native[r['record']]
        raw = CACHE / 'audio' / (r['record'] + '.f32')
        clean_file = CACHE / 'features' / (r['record'] + '.npy')
        assert digest(raw) == meta['native_audio_sha256']
        assert digest(clean_file) == meta['features_sha256']
        x = np.fromfile(raw, dtype='<f4')
        y = transform(x, profile, np.random.default_rng(stable_seed('phone-style:' + r['record'])))
        feat = spectrum(y)
        original = np.load(clean_file)
        assert feat.shape == original.shape and np.all(np.isfinite(feat))
        target = styled / (r['record'] + '.npy'); np.save(target, feat)
        good = usable_starts(y)
        both = sorted(set(meta['usable_frame_starts']) & set(good))
        prepared.append(dict(**r, samples=meta['samples'], clean_usable=meta['usable_frame_starts'],
                             styled_usable=good, paired_usable=both, styled_features_sha256=digest(target),
                             clean_features_sha256=meta['features_sha256']))
        if r['role'] == 'training':
            clean_shape.append(original.mean(axis=1)); augmented_shape.append(feat.mean(axis=1))
        if r['role'] == 'selection' and r['target'] not in exported:
            exported.add(r['target'])
            for name, audio in [('original', x), ('phone-style', y)]:
                sf.write(examples / (r['record'] + '-' + name + '.wav'), audio, RATE, subtype='PCM_16')
        if index % 200 == 0:
            print(json.dumps({'prepared': index, 'total': len(rows)}), flush=True)
    save(out / 'data.json', prepared)
    rng = np.random.default_rng(2026111501)
    clean_controls, style_controls = [], []
    for _ in range(64):
        x = rng.normal(0, .003, SAMPLES).astype(np.float32)
        clean_controls.append(spectrum(x)); style_controls.append(spectrum(transform(x, profile, rng)))
    np.savez(out / 'noise-controls.npz', clean=np.stack(clean_controls), styled=np.stack(style_controls))
    summary = dict(public_records=len(prepared), private_phone_spectra=len(phone),
                   private_off_chest_noise_spectra=len(noise), excluded_case_on_used=False,
                   source_training_people_for_profile=len(used_groups),
                   roles={role: sum(r['role'] == role for r in prepared)
                          for role in ['training', 'selection', 'calibration']},
                   phone_profile_sha256=digest(out / 'phone-profile.json'),
                   data_sha256=digest(out / 'data.json'), control_sha256=digest(out / 'noise-controls.npz'))
    save(out / 'prepared.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--today-cohort', type=Path, required=True)
    parser.add_argument('--yesterday', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args())
