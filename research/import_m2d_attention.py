"""Independently verify trained attention/control artifacts against the source."""
import argparse
import json
from pathlib import Path
import zipfile

import torch
from torch import nn

from m2d_attention import M2DDecisionHead, FEATURE_DIM
from m2d_murmur import HERE, sha
from train_m2d_attention import EPOCHS, SNAPSHOTS, BATCH_SIZE
from train_m2d_murmur import tensor_sha
from train_m2d_native_heads import ENCODER_CHECKPOINT

FILES = {'protocol.json', 'data-audit.json', 'base-fingerprints.json', 'initial-heads.pt',
         'attention-heads.pt', 'selection-predictions.json', 'history.json', 'complete.json'}


def main(a):
    torch.set_num_threads(2)
    if a.output.exists():
        raise ValueError('Preserve completed/partial imports')
    with zipfile.ZipFile(a.archive) as archive:
        assert len(archive.infolist()) == len(FILES)
        assert set(archive.namelist()) == {'artifacts/' + n for n in FILES}
        assert all(i.file_size < 40 * 1024**2 and (i.external_attr >> 16) & 0o170000 != 0o120000
                   for i in archive.infolist())
        assert sum(i.file_size for i in archive.infolist()) < 100 * 1024**2
        assert archive.testzip() is None
        a.output.mkdir(parents=True)
        archive.extractall(a.output)
    source = a.output / 'artifacts'
    read = lambda n: json.loads((source / n).read_text())
    complete, protocol, data = map(read, ['complete.json', 'protocol.json', 'data-audit.json'])
    assert complete['status'] == 'attention_training_complete'
    assert complete['epochs'] == EPOCHS and complete['heads'] == 6 and complete['base_model_unchanged']
    assert sha(source / 'protocol.json') == complete['protocol_sha256']
    assert sha(source / 'attention-heads.pt') == complete['heads_sha256']
    assert sha(source / 'initial-heads.pt') == complete['initial_heads_sha256']
    audit = json.loads(a.audit.read_text())
    assert set(protocol['source_sha256']) == set(audit['files_sha256'])
    for name, fingerprint in protocol['source_sha256'].items():
        assert fingerprint == audit['files_sha256'][name] == sha(HERE / name), name
    assert protocol['bundle_sha256'] == audit['bundle_sha256']
    assert protocol['config_sha256'] == audit['config_sha256']
    assert all(protocol[k] is False for k in ['private_audio_included', 'private_profile_included', 'calibration_or_test_loaded'])
    assert sha(a.encoder) == ENCODER_CHECKPOINT == protocol['base_checkpoint_sha256']
    baseline = torch.load(a.encoder, map_location='cpu', weights_only=True)
    assert {k:tensor_sha(v) for k,v in baseline.items()} == read('base-fingerprints.json')
    assert data['training_records'] == 2356 and data['selection_records'] == 180
    assert len(data['records']) == 2536 and sum(data['training_class_counts']) == data['training_windows']
    assert data['cache_bytes'] == data['training_windows'] * data['frame_count'] * FEATURE_DIM * 2
    assert data['frame_count'] > 1 and data['initial_attention_maximum_logit_error'] < .0001
    history = read('history.json')
    assert [r['epoch'] for r in history] == list(range(1, EPOCHS + 1))
    steps = (data['training_windows'] + BATCH_SIZE - 1) // BATCH_SIZE
    assert all(r['optimizer_steps_per_arm'] == r['epoch'] * steps for r in history)
    assert complete['optimizer_steps_per_arm'] == EPOCHS * steps
    initial = torch.load(source / 'initial-heads.pt', map_location='cpu', weights_only=True)
    heads = torch.load(source / 'attention-heads.pt', map_location='cpu', weights_only=True)
    assert set(initial) == {'attention', 'mean'}
    assert set(heads) == {f'{arm}_epoch_{e}' for arm in ['mean', 'attention'] for e in SNAPSHOTS}
    assert torch.count_nonzero(initial['attention']['pool.score.weight']) == 0
    verified = {}
    for arm, state in initial.items():
        assert all(torch.isfinite(v).all() for v in state.values())
        for k,v in baseline.items():
            if k.startswith(('norm.', 'classifier.')):
                assert torch.equal(state[k], v), (arm, k)
    for name, state in heads.items():
        arm = name.split('_')[0]
        head = M2DDecisionHead(nn.BatchNorm1d(FEATURE_DIM, affine=False), nn.Linear(FEATURE_DIM, 3), arm)
        head.load_state_dict(state, strict=True)
        assert set(state) == set(initial[arm]) and all(torch.isfinite(v).all() for v in state.values())
        for k,v in baseline.items():
            if k.startswith('norm.'):
                assert torch.equal(state[k], v), (name, k)
        changed = [k for k,v in state.items() if not torch.equal(v, initial[arm][k])]
        assert {'classifier.weight', 'classifier.bias'} <= set(changed)
        assert all(k.startswith(('pool.', 'classifier.')) for k in changed)
        if arm == 'attention':
            assert {'pool.score.weight', 'pool.project.weight', 'pool.project.bias'} <= set(changed)
            for domain in ['native2k', 'generic']:
                evidence = complete['attention_audit'][name][domain]
                assert evidence['nonuniform_windows'] > 0
                assert evidence['maximum_deviation_from_uniform'] > 1e-6
        verified[name] = dict(changed_tensors=changed, normalization_exact=True,
                              all_tensors_finite=True, pooling=arm)
    result = dict(status='verified', archive_sha256=sha(a.archive), heads_sha256=sha(source / 'attention-heads.pt'),
        encoder_sha256=sha(a.encoder), source_fingerprints_matched=True, heads=verified,
        epochs=EPOCHS, optimizer_steps_per_arm=complete['optimizer_steps_per_arm'],
        initial_attention_uniform=True, base_fingerprints_matched=True,
        head_artifacts_contain_no_encoder_weights=True, private_audio_used=False,
        calibration_audio_loaded=False, app_updated=False)
    (a.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['archive', 'output', 'audit', 'encoder']:
        p.add_argument('--' + name, type=Path, required=True)
    main(p.parse_args())
