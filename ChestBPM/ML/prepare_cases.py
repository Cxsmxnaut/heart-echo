"""Controlled waveform/noise cases. Synthetic mixtures are not real movement validation."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import signal
import soundfile as sf

from denoiser import KerasGraph, enhance

ROOT = Path(__file__).resolve().parent


def bandpass(x):
    return signal.sosfilt(signal.butter(2, [25, 400], btype='bandpass', fs=1000, output='sos'), x)


def stretch_noise(x, n):
    # Repeating the public short example is disclosed; short fades suppress loop clicks.
    x = np.asarray(x, float).copy(); fade = min(30, len(x) // 10)
    x[:fade] *= np.linspace(0, 1, fade); x[-fade:] *= np.linspace(1, 0, fade)
    return np.resize(x, n)


def spectral_baseline(x):
    _, _, z = signal.stft(x, 1000, nperseg=256, noverlap=128)
    power = np.abs(z) ** 2; clean = np.empty_like(z)
    for i in range(z.shape[1]):
        noise = np.quantile(power[:, max(0, i - 20):i + 1], .15, axis=1)
        gain = np.maximum(.1, 1 - noise / np.maximum(power[:, i], 1e-12))
        clean[:, i] = z[:, i] * gain
    return signal.istft(clean, 1000, nperseg=256, noverlap=128)[1][:len(x)]


def si_sdr(reference, value):
    a = reference - np.mean(reference); b = value - np.mean(value)
    projection = a * np.dot(a, b) / max(np.dot(a, a), 1e-20)
    return float(10 * np.log10(max(np.dot(projection, projection), 1e-20) / max(np.sum((b - projection) ** 2), 1e-20)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['development', 'test', 'final_test', 'validation_v17'], required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'manifest.json')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--native', action='store_true', help='Keep the original signal for the complete native pipeline')
    args = parser.parse_args()
    manifest = json.load(args.manifest.open()); records = [r for r in manifest['records'] if r['split'] == args.split]
    if args.limit:
        records = records[:args.limit]
    model = None if args.native else KerasGraph(ROOT / 'cache/LU-Net.h5')
    noises = {}
    for name in ['speech', 'babble']:
        x, rate = sf.read(ROOT / ('cache/noise/' + name + '.wav'))
        if x.ndim > 1:
            x = x[:, 0]
        resampled = signal.resample_poly(x, 1000, rate)
        noises[name] = resampled if args.native else bandpass(resampled)
    root = ROOT / 'cache/cases' / (args.split + ('-native' if args.native else '')); root.mkdir(parents=True, exist_ok=True)
    cases, metrics = [], []
    for record in records:
        prefix = ROOT / 'cache/circor/training_data' / record['record']
        audio, rate = sf.read(str(prefix) + '.wav'); labels = np.loadtxt(str(prefix) + '.tsv', ndmin=2)
        resampled = signal.resample_poly(audio, 1000, rate)
        x = (resampled if args.native else bandpass(resampled))[2000:14000]
        x = x / max(np.max(np.abs(x)), 1e-8) * .3
        s1 = (labels[labels[:, 2] == 1, 0] - 2).tolist()
        rng = np.random.default_rng(int(hashlib.sha256(record['record'].encode()).hexdigest()[:8], 16))
        n = len(x); t = np.arange(n) / 1000
        variants = {'clean': x.copy()}
        for name, noise in [('white', bandpass(rng.normal(0, 1, n))), ('hum', np.sin(2 * np.pi * 50 * t)),
                            *[(name, stretch_noise(noise, n)) for name, noise in noises.items()]]:
            for db in [6, 0]:
                scaled = noise * np.sqrt(np.mean(x * x) / max(np.mean(noise * noise), 1e-12)) * 10 ** (-db / 20)
                variants[name + '_' + str(db) + 'dB'] = x + scaled
        clicks = np.zeros(n)
        for at in [3.13, 6.41, 9.29]:
            offset = int(at * 1000); width = min(40, n - offset)
            if width > 0:
                clicks[offset:offset + width] = .6 * np.hanning(width) * np.sin(np.arange(width) * .41)
        variants['short_taps_simulated'] = x + clicks
        rub = bandpass(rng.normal(0, 1, n)); rub *= .22 / max(np.sqrt(np.mean(rub * rub)), 1e-8)
        rub *= ((t > 5.8) & (t < 6.2))
        variants['brief_rub_simulated'] = x + rub
        variants['contact_gain_simulated'] = x * np.where((t > 4) & (t < 5.2), .15, 1)
        variants['lost_contact_simulated'] = x * np.where((t > 6) & (t < 6.5), 0, 1)
        for condition, mixture in variants.items():
            scale = min(1.0, .9 / max(np.max(np.abs(mixture)), 1e-8)); mixture = mixture * scale
            reference = x * scale
            outputs = {'raw': mixture} if args.native else {'bandpass': mixture, 'spectral': spectral_baseline(mixture), 'lunet': enhance(model, mixture)}
            for method, output in outputs.items():
                identity = record['record'] + '__' + condition + '__' + method
                path = root / (identity + '.wav'); sf.write(path, output.astype(np.float32), 1000, subtype='FLOAT')
                cases.append(dict(id=identity, path=str(path), split=args.split, group=record['group'], record=record['record'],
                                  condition=condition, method=method, s1=s1))
                metrics.append(dict(record=record['record'], condition=condition, method=method,
                                    si_sdr=si_sdr(reference, output), rms=float(np.sqrt(np.mean(output * output)))))
            print(record['record'], condition, flush=True)
    # Negative controls: no hidden heart sound. Any returned BPM is a false detection.
    rng = np.random.default_rng(917); n = 12000; t = np.arange(n) / 1000
    controls = dict(silence=np.zeros(n), white_only=bandpass(rng.normal(0, .05, n)),
                    speech_only=stretch_noise(noises['speech'], n), babble_only=stretch_noise(noises['babble'], n),
                    hum_only=.05 * np.sin(2 * np.pi * 50 * t))
    for name, x in controls.items():
        x = x * min(1, .5 / max(np.max(np.abs(x)), 1e-8))
        outputs = [('raw', x)] if args.native else [('bandpass', x), ('spectral', spectral_baseline(x)), ('lunet', enhance(model, x))]
        for method, y in outputs:
            path = root / (name + '__' + method + '.wav'); sf.write(path, y.astype(np.float32), 1000, subtype='FLOAT')
            cases.append(dict(id=name + '__' + method, path=str(path), split=args.split, group='negative', record='negative',
                              condition=name, method=method, s1=[]))
    (root / 'cases.json').write_text(json.dumps(cases))
    (ROOT / 'results' / (args.split + '-waveform.json')).write_text(json.dumps(metrics, indent=2))
    print('Prepared', len(cases), 'cases:', root / 'cases.json', flush=True)


if __name__ == '__main__':
    main()
