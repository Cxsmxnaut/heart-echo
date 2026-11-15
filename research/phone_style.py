"""Bounded, unpaired phone-style augmentation, never a measured transfer function.

Only smooth spectral summaries and noise power are retained. No private heartbeat
waveform, diagnosis, Watch value, or inferred murmur target is mixed into examples.
"""
import hashlib
import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter1d

RATE = 2000
LIMIT_DB = 6.0


def stable_seed(name):
    return int(hashlib.sha256(name.encode()).hexdigest()[:16], 16)


def check_audio(audio):
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim != 1 or len(x) < RATE * 4 or not np.all(np.isfinite(x)):
        raise ValueError('Expected at least four seconds of finite mono audio')
    rms = float(np.sqrt(np.mean(x * x)))
    if rms < 1e-7:
        raise ValueError('Silent audio cannot define a phone spectrum')
    return x, rms


def normalized_spectrum(audio):
    x, rms = check_audio(audio)
    hz, power = signal.welch(x / rms, fs=RATE, nperseg=1024)
    logpower = gaussian_filter1d(np.log(np.maximum(power, 1e-14)), 5)
    band = (hz >= 25) & (hz <= 950)
    return hz, logpower - logpower[band].mean(), rms


def fit_profile(public_audio, phone_audio, noise_audio):
    """Inputs are equally weighted recordings, not overlapping heartbeat crops."""
    if not public_audio or not phone_audio or not noise_audio:
        raise ValueError('Public, phone and off-chest noise examples are required')
    public = [normalized_spectrum(x) for x in public_audio]
    phone = [normalized_spectrum(x) for x in phone_audio]
    noise = [normalized_spectrum(x) for x in noise_audio]
    hz = public[0][0]
    reference = np.median(np.stack([x[1] for x in public]), axis=0)
    curves = [np.clip((x[1] - reference) * 10 / np.log(10), -LIMIT_DB, LIMIT_DB)
              for x in phone]
    noise_logpower = np.median(np.stack([x[1] for x in noise]), axis=0)
    noise_logpower -= noise_logpower.max()
    return dict(rate=RATE, frequency_hz=hz.tolist(), response_db=np.stack(curves).tolist(),
                phone_rms=[x[2] for x in phone], noise_power=np.exp(noise_logpower).tolist(),
                maximum_response_db=LIMIT_DB, snr_db_range=[24., 36.],
                method='Unpaired smoothed spectral differences, bounded to +/-6 dB; '
                       'synthetic Gaussian noise shaped by off-chest power only.',
                limitation='Differences include people, anatomy and placement, not just the microphone. '
                           'No paired transfer-function or real phone accuracy claim.')


def transform(audio, profile, rng):
    """Symmetric filtering and quiet colored noise; no time warp or beat insertion."""
    x, _ = check_audio(audio)
    hz = np.asarray(profile['frequency_hz'])
    curve = np.asarray(profile['response_db'][int(rng.integers(len(profile['response_db'])))])
    curve = np.clip(curve * rng.uniform(.5, 1.), -LIMIT_DB, LIMIT_DB)
    gain = 10 ** (curve / 20)
    fir = signal.firwin2(129, hz, gain, fs=RATE)
    y = signal.fftconvolve(x, fir, mode='same')
    # Noise is synthesized from power statistics; original phone cycles are never copied.
    noise = rng.normal(size=len(y))
    frequencies = np.fft.rfftfreq(len(y), 1 / RATE)
    amplitude = np.sqrt(np.interp(frequencies, hz, profile['noise_power']))
    amplitude[0] = 0
    noise = np.fft.irfft(np.fft.rfft(noise) * amplitude, n=len(y))
    noise /= max(float(np.sqrt(np.mean(noise * noise))), 1e-12)
    rms = float(np.sqrt(np.mean(y * y)))
    snr = rng.uniform(*profile['snr_db_range'])
    y += noise * rms * 10 ** (-snr / 20)
    target_rms = profile['phone_rms'][int(rng.integers(len(profile['phone_rms'])))]
    y *= target_rms / max(float(np.sqrt(np.mean(y * y))), 1e-12)
    y *= 10 ** (rng.uniform(-3, 3) / 20)
    peak = float(np.max(np.abs(y)))
    if peak > .95:
        y *= .95 / peak
    result = y.astype(np.float32)
    if result.shape != x.shape or not np.all(np.isfinite(result)):
        raise ValueError('Augmentation corrupted audio')
    return result


def eligible_today(cohort):
    """Excluded or case-on recordings must never be opened for style fitting."""
    return [r for r in cohort['records'] if not r.get('excluded', True)
            and r.get('case_on') is False]


def assert_person_split(rows):
    groups = {}
    for r in rows:
        if r['role'] not in ('training', 'selection', 'calibration'):
            raise ValueError('Only public development partitions are allowed')
        if groups.setdefault(r['group'], r['role']) != r['role']:
            raise ValueError('A linked person crosses partitions')
