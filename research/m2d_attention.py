"""Learned temporal pooling for M2D; the fingerprinted mean baseline is unchanged.

New inference uses M2DAttentionMurmur. The original M2DMurmur remains available
only as a reproducible baseline. Separate recording-window aggregation is
unchanged; attention replaces the time average inside each five-second window.
"""
import copy

import torch
from torch import nn

from m2d_murmur import M2DMurmur

FEATURE_DIM = 3840
ATTENTION_DIM = 64


class TemporalAttentionPool(nn.Module):
    """Content-dependent, normalized weights over the encoder's time frames."""

    def __init__(self, feature_dim=FEATURE_DIM, hidden_dim=ATTENTION_DIM):
        super().__init__()
        self.input_norm = nn.LayerNorm(feature_dim, elementwise_affine=False)
        self.project = nn.Linear(feature_dim, hidden_dim)
        self.score = nn.Linear(hidden_dim, 1, bias=False)
        # A new model starts with the exact uniform-pooling function.
        nn.init.zeros_(self.score.weight)

    def forward(self, frames, mask=None, return_weights=False):
        if frames.ndim != 3 or frames.shape[1] == 0:
            raise ValueError('Expected nonempty batch x time x feature embeddings')
        scores = self.score(torch.tanh(self.project(self.input_norm(frames)))).squeeze(-1)
        if mask is not None:
            if mask.shape != scores.shape or mask.dtype != torch.bool:
                raise ValueError('Attention mask must be boolean batch x time')
            if not mask.any(dim=1).all():
                raise ValueError('Every window needs at least one valid frame')
            scores = scores.masked_fill(~mask, float('-inf'))
        weights = scores.softmax(dim=1)
        pooled = (frames * weights.unsqueeze(-1)).sum(dim=1)
        return (pooled, weights) if return_weights else pooled


class MeanPoolControl(nn.Module):
    """The sole architectural difference in the matched control."""

    def forward(self, frames):
        return frames.mean(dim=1)


class M2DDecisionHead(nn.Module):
    """Trainable decision head with fixed original normalization statistics."""

    def __init__(self, norm, classifier, pooling='attention'):
        super().__init__()
        if pooling not in ('attention', 'mean'):
            raise ValueError('Unknown pooling method')
        self.pooling = pooling
        self.pool = TemporalAttentionPool() if pooling == 'attention' else MeanPoolControl()
        self.norm = copy.deepcopy(norm)
        self.classifier = copy.deepcopy(classifier)
        self.classifier.requires_grad_(True)
        self.norm.requires_grad_(False)
        self.norm.eval()

    def train(self, mode=True):
        super().train(mode)
        self.norm.eval()
        return self

    def forward(self, frames, return_weights=False):
        if return_weights:
            if self.pooling != 'attention':
                raise ValueError('Only the attention head has learned weights')
            pooled, weights = self.pool(frames, return_weights=True)
            return self.classifier(self.norm(pooled)), weights
        return self.classifier(self.norm(self.pool(frames)))


class M2DAttentionMurmur(nn.Module):
    """Full inference model whose final within-window pooling is attention."""

    def __init__(self, baseline):
        super().__init__()
        self.runtime = copy.deepcopy(baseline.runtime)
        self.runtime.requires_grad_(False)
        self.runtime.eval()
        self.head = M2DDecisionHead(baseline.norm, baseline.classifier)

    @classmethod
    def from_checkpoint(cls, cache, encoder_state, attention_state):
        baseline = M2DMurmur(cache).eval()
        baseline.load_state_dict(encoder_state)
        model = cls(baseline)
        model.head.load_state_dict(attention_state, strict=True)
        return model

    def train(self, mode=True):
        super().train(mode)
        self.runtime.eval()
        self.head.norm.eval()
        return self

    def features(self, wave):
        with torch.no_grad():
            return self.runtime.to_log_mel_spec(wave)

    def frame_features(self, log_mel):
        with torch.no_grad():
            return self.runtime.encode_lms(self.runtime.normalize_batch(log_mel))

    def forward(self, log_mel, return_weights=False):
        return self.head(self.frame_features(log_mel), return_weights=return_weights)
