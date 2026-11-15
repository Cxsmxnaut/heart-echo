"""Independent seeded synthetic false-positive controls. No heart recordings."""
import json
from pathlib import Path
import numpy as np
from scipy import signal
import soundfile as sf

root = Path(__file__).resolve().parent / 'cache/cases/negative-extra'
root.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(992831)
n = 16000; t = np.arange(n) / 1000
cases = {}
for i in range(6):
    x = rng.normal(size=n)
    x = signal.sosfilt(signal.butter(2, [25, 100 + i * 50], fs=1000, btype='bandpass', output='sos'), x)
    cases[f'colored_noise_{i}'] = x
cases['tone_sweep'] = signal.chirp(t, 40, t[-1], 350)
cases['hum_harmonics'] = np.sin(2 * np.pi * 50 * t) + .4 * np.sin(2 * np.pi * 100 * t)
for bpm in [48, 72, 120, 160]:
    phase = t % (60 / bpm)
    cases[f'regular_beep_{bpm}'] = np.sin(2 * np.pi * 220 * t) * (phase < .08)
cases['random_taps'] = signal.lfilter([1], [1, -.85], (rng.random(n) < .003) * rng.normal(size=n))
cases['clipped_speechlike'] = np.clip(np.sin(2*np.pi*140*t) * (.5+.5*np.sin(2*np.pi*3.1*t)) + rng.normal(0,.2,n), -.3, .3)
rows = []
for name, x in cases.items():
    path = root / (name + '.wav')
    sf.write(path, x / max(abs(x).max(), 1e-8) * .2, 1000, subtype='FLOAT')
    rows.append(dict(id=name, path=str(path), split='independent_negative', group='negative', record='negative', condition=name, method='raw', s1=[]))
(root / 'cases.json').write_text(json.dumps(rows, indent=2))
print(len(rows), 'new synthetic controls')
