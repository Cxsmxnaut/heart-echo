"""Weak murmur timing targets; public timing labels are approximate, not dense truth."""
import numpy as np
from murmur_phase_data import targets
from murmur_data import ROOT


def timing_targets(record, frames):
    phases = targets(record, frames)
    result = np.full(frames, -100., dtype=np.float32)
    if record['target'] == 2: return phases, result
    if record['target'] == 0:
        result[phases != -100] = 0
        return phases, result
    timing = {2: record['systolic_timing'].lower(), 4: record['diastolic_timing'].lower()}
    timing = {k: '' if v in ['', 'nan'] else v for k, v in timing.items()}
    if not any(timing.values()): return phases, result
    centers = (np.arange(frames) * 40 + 128) / 2000
    for a, b, state in np.loadtxt(ROOT / 'cache/circor' / record['annotation'], ndmin=2):
        if a >= b or state not in [2, 4]: continue
        inside = (centers >= a) & (centers < b)
        label = timing[int(state)]
        if not label:
            result[inside] = 0
            continue
        if label.startswith('holo'): low, high = 0., 1.
        elif label.startswith('early'): low, high = 0., .5
        elif label.startswith('mid'): low, high = .25, .75
        elif label.startswith('late'): low, high = .5, 1.
        else: raise ValueError('Unsupported timing label: ' + label)
        result[inside] = 0
        result[inside & (centers >= a + low * (b - a)) & (centers < a + high * (b - a))] = 1
    return phases, result
