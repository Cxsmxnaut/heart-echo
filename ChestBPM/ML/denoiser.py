"""Numerical import of the authors' LU-Net HDF5 graph, without executing Keras code.

Reference: Ali et al., IEEE Access 2023, document 10173517. The source architecture
is credited in ATTRIBUTION.txt. Original weights remain in the ignored cache.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import h5py
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parent
torch.set_num_threads(1)


class SameConv(nn.Module):
    def __init__(self, kernel, bias, stride, activation):
        super().__init__()
        self.stride, self.activation = stride, activation
        self.register_buffer('kernel', torch.from_numpy(kernel.transpose(2, 1, 0).copy()))
        self.register_buffer('bias', torch.from_numpy(bias.copy()))

    def forward(self, x):
        total = max(0, ((x.shape[-1] + self.stride - 1) // self.stride - 1) * self.stride + self.kernel.shape[-1] - x.shape[-1])
        y = F.conv1d(F.pad(x, (total // 2, total - total // 2)), self.kernel, self.bias, stride=self.stride)
        return torch.relu(y) if self.activation == 'relu' else torch.tanh(y) if self.activation == 'tanh' else F.elu(y) if self.activation == 'elu' else y


class BiLSTM(nn.Module):
    def __init__(self, weights):
        super().__init__()
        forward = weights['forward']
        hidden = forward['recurrent_kernel'].shape[0]
        self.layer = nn.LSTM(forward['kernel'].shape[0], hidden, batch_first=True, bidirectional=True)
        with torch.no_grad():
            for direction, suffix in [('forward', ''), ('backward', '_reverse')]:
                w = weights[direction]
                getattr(self.layer, 'weight_ih_l0' + suffix).copy_(torch.from_numpy(w['kernel'].T))
                getattr(self.layer, 'weight_hh_l0' + suffix).copy_(torch.from_numpy(w['recurrent_kernel'].T))
                bias = w['bias'].reshape(-1)
                getattr(self.layer, 'bias_ih_l0' + suffix).copy_(torch.from_numpy(bias[:hidden * 4]))
                other = bias[hidden * 4:] if len(bias) == hidden * 8 else np.zeros(hidden * 4, np.float32)
                getattr(self.layer, 'bias_hh_l0' + suffix).copy_(torch.from_numpy(other))

    def forward(self, x):
        return self.layer(x.transpose(1, 2))[0].transpose(1, 2)


class KerasGraph(nn.Module):
    def __init__(self, path):
        super().__init__()
        self.operations = nn.ModuleDict()
        self.nodes, self.weights = [], {}
        with h5py.File(path) as file:
            raw = file.attrs['model_config']
            config = json.loads(raw.decode() if isinstance(raw, bytes) else raw)['config']
            self.input_name, self.output_name = config['input_layers'][0][0], config['output_layers'][0][0]
            for layer in config['layers']:
                kind, c = layer['class_name'], layer['config']; name = c['name']
                inputs = [n[0] for n in layer['inbound_nodes'][0]] if layer['inbound_nodes'] else []
                w = {}
                if name in file['model_weights']:
                    def collect(key, value):
                        if isinstance(value, h5py.Dataset):
                            w[key] = np.asarray(value, dtype=np.float32)
                    file['model_weights'][name].visititems(collect)
                if kind == 'Conv1D':
                    kernel = next(v for k, v in w.items() if k.endswith('/kernel:0'))
                    bias = next(v for k, v in w.items() if k.endswith('/bias:0'))
                    assert c['padding'] == 'same' and c['activation'] in ['relu', 'tanh', 'elu', 'linear']
                    w = dict(kernel=kernel, bias=bias)
                    self.operations[name] = SameConv(kernel, bias, c['strides'][0], c['activation'])
                elif kind == 'Bidirectional':
                    lc = c['layer']['config']
                    assert lc['activation'] == 'tanh' and lc['recurrent_activation'] == 'sigmoid' and lc['return_sequences']
                    assert c['merge_mode'] == 'concat'
                    w = {direction: {part: next(v for k, v in w.items() if '/' + direction + '_' in '/' + k and k.endswith('/' + part + ':0'))
                                     for part in ['kernel', 'recurrent_kernel', 'bias']} for direction in ['forward', 'backward']}
                    self.operations[name] = BiLSTM(w)
                elif kind not in ['InputLayer', 'UpSampling1D', 'Concatenate', 'Dropout']:
                    raise ValueError('Unsupported source layer: ' + kind)
                self.nodes.append((name, kind, inputs, c))
                self.weights[name] = w
        self.eval()

    def forward(self, x):
        values = {self.input_name: x}
        for name, kind, inputs, config in self.nodes:
            if kind == 'InputLayer':
                continue
            if kind == 'Concatenate':
                values[name] = torch.cat([values[n] for n in inputs], dim=1 if config['axis'] == 2 else 2)
            elif kind == 'UpSampling1D':
                values[name] = torch.repeat_interleave(values[inputs[0]], config['size'], dim=2)
            elif kind == 'Dropout':
                values[name] = values[inputs[0]]
            else:
                values[name] = self.operations[name](values[inputs[0]])
        return values[self.output_name]

    def numpy_reference(self, x):
        """Independent Conv/LSTM arithmetic checks layout, gates and reverse direction."""
        values = {self.input_name: x.transpose(0, 2, 1)}
        def sigmoid(a):
            return 1 / (1 + np.exp(-np.clip(a, -80, 80)))
        for name, kind, inputs, c in self.nodes:
            if kind == 'InputLayer':
                continue
            a = values[inputs[0]]; w = self.weights[name]
            if kind == 'Conv1D':
                stride = c['strides'][0]; kernel = w['kernel']; n = a.shape[1]
                total = max(0, ((n + stride - 1) // stride - 1) * stride + len(kernel) - n)
                padded = np.pad(a, ((0, 0), (total // 2, total - total // 2), (0, 0)))
                windows = np.lib.stride_tricks.sliding_window_view(padded, len(kernel), axis=1)[:, ::stride]
                y = np.einsum('btck,kco->bto', windows, kernel, optimize=True) + w['bias']
                values[name] = np.maximum(y, 0) if c['activation'] == 'relu' else np.tanh(y) if c['activation'] == 'tanh' else np.where(y > 0, y, np.expm1(y)) if c['activation'] == 'elu' else y
            elif kind == 'Bidirectional':
                outputs = []
                for direction in ['forward', 'backward']:
                    d = w[direction]; hidden = d['recurrent_kernel'].shape[0]
                    h = np.zeros((len(a), hidden), np.float32); cell = h.copy(); y = np.zeros((len(a), a.shape[1], hidden), np.float32)
                    for t in range(a.shape[1]) if direction == 'forward' else reversed(range(a.shape[1])):
                        bias = d['bias'].reshape(-1, hidden * 4).sum(axis=0)
                        i, f, g, o = np.split(a[:, t] @ d['kernel'] + h @ d['recurrent_kernel'] + bias, 4, axis=1)
                        cell = sigmoid(f) * cell + sigmoid(i) * np.tanh(g); h = sigmoid(o) * np.tanh(cell); y[:, t] = h
                    outputs.append(y)
                values[name] = np.concatenate(outputs, axis=2)
            elif kind == 'Concatenate':
                values[name] = np.concatenate([values[n] for n in inputs], axis=c['axis'])
            elif kind == 'UpSampling1D':
                values[name] = np.repeat(a, c['size'], axis=1)
            else:
                values[name] = a
        return values[self.output_name].transpose(0, 2, 1)


def enhance(model, signal, batch=32):
    """50% overlap, causal block availability and preserved source amplitude."""
    x = np.asarray(signal, np.float32); output = np.zeros_like(x); weights = np.zeros_like(x)
    starts = list(range(0, max(1, len(x) - 799), 400))
    if starts[-1] + 800 < len(x):
        starts.append(starts[-1] + 400)
    window = np.maximum(np.hanning(801)[:-1], 1e-4).astype(np.float32)
    for offset in range(0, len(starts), batch):
        positions = starts[offset:offset + batch]
        frames = np.stack([np.pad(x[s:s + 800], (0, max(0, 800 - len(x[s:s + 800])))) for s in positions])
        scales = np.maximum(np.max(np.abs(frames), axis=1), 1e-8)
        with torch.inference_mode():
            result = model(torch.from_numpy((frames / scales[:, None])[:, None, :])).numpy()[:, 0, :] * scales[:, None]
        for start, cleaned in zip(positions, result):
            n = min(800, len(x) - start); output[start:start + n] += cleaned[:n] * window[:n]; weights[start:start + n] += window[:n]
    return output / np.maximum(weights, 1e-8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', type=Path, default=ROOT / 'cache/LU-Net.h5')
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args(); model = KerasGraph(args.weights)
    rng = np.random.default_rng(1701)
    vectors = [np.zeros((1, 1, 800), np.float32), rng.normal(0, .2, (1, 1, 800)).astype(np.float32),
               np.sin(np.arange(800) * 2 * np.pi * 65 / 1000).astype(np.float32)[None, None] * .3]
    differences, durations = [], []
    for x in vectors:
        began = time.perf_counter()
        with torch.inference_mode():
            y = model(torch.from_numpy(x)).numpy()
        durations.append(time.perf_counter() - began)
        ref = model.numpy_reference(x)
        differences.append(float(np.max(np.abs(y - ref))))
    assert max(differences) < 2e-4, differences
    report = dict(weight_sha256=hashlib.sha256(args.weights.read_bytes()).hexdigest(), independent_numpy_max_errors=differences,
                  seconds_per_800_samples=durations, output_finite=bool(np.isfinite(y).all()))
    if args.export:
        import coremltools as ct
        traced = torch.jit.trace(model, torch.from_numpy(vectors[1]))
        converted = ct.convert(traced, inputs=[ct.TensorType(name='noisy', shape=(1, 1, 800))],
                               outputs=[ct.TensorType(name='cleaned')], minimum_deployment_target=ct.target.iOS17,
                               compute_precision=ct.precision.FLOAT32)
        converted.author = 'Original LU-Net: Shams Nafisa Ali et al.; numerical conversion: Chest BPM'
        converted.short_description = 'Experimental heart-sound denoising, 0.8 seconds at 1 kHz; not a diagnostic model.'
        converted.user_defined_metadata['source'] = 'https://github.com/ShamsNafisaAli/LU-Net-Heart-Sound-Denoising-'
        converted.user_defined_metadata['weight_sha256'] = report['weight_sha256']
        path = ROOT / 'generated/HeartDenoiser.mlpackage'; converted.save(str(path))
        errors = []
        for x in vectors:
            with torch.inference_mode():
                expected = model(torch.from_numpy(x)).numpy()
            actual = converted.predict({'noisy': x})['cleaned']
            errors.append(float(np.max(np.abs(actual - expected))))
        assert max(errors) < 3e-4, errors
        report['coreml_max_errors'] = errors
        with torch.inference_mode():
            expected = model(torch.from_numpy(vectors[1])).numpy()
        np.savez(ROOT / 'generated/verification-vectors.npz', input=vectors[1], expected=expected)
    (ROOT / 'results/model-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
