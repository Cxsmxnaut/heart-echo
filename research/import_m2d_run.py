"""Safely import one completed cloud M2D run and independently check its weights."""
import argparse
import json
import os
from pathlib import Path
import zipfile

import torch

from m2d_murmur import sha,HERE,PRETRAINED_SHA,WEIGHT_FOLDER
from train_m2d_murmur import tensor_sha

EXPECTED={'protocol.json','initial-parameter-fingerprints.json','data-audit.json','history.json',
          'M2D.pt','selected.json','selection-predictions.json','training-proof.json','complete.json'}


def main(args):
    os.umask(0o077);torch.set_num_threads(2)
    if args.output.exists():
        raise ValueError('Refuse to overwrite an imported run')
    with zipfile.ZipFile(args.archive) as archive:
        members=archive.infolist()
        names=[p.filename for p in members]
        if len(names)!=len(EXPECTED) or set(names)!={'artifacts/'+name for name in EXPECTED}:
            raise ValueError('Unexpected archive contents')
        if any(p.file_size>500*1024**2 or (p.external_attr>>16)&0o170000==0o120000 for p in members):
            raise ValueError('Unexpected file size or symbolic link')
        if sum(p.file_size for p in members)>600*1024**2 or archive.testzip() is not None:
            raise ValueError('Invalid training archive')
        args.output.mkdir(parents=True)
        archive.extractall(args.output)
    source=args.output/'artifacts'
    read=lambda name:json.loads((source/name).read_text())
    complete=read('complete.json');protocol=read('protocol.json');proof=read('training-proof.json')
    assert complete['status']=='m2d_training_complete' and complete['proof']==proof
    assert sha(source/'protocol.json')==complete['protocol_sha256']
    assert sha(source/'M2D.pt')==proof['weights_sha256']
    audit=json.loads(args.audit.read_text())
    assert protocol['config_sha256']==audit['files_sha256']['public-config.json']
    for name,fingerprint in protocol['source_sha256'].items():
        assert fingerprint==audit['files_sha256'][name] and sha(HERE/name)==fingerprint,name
    assert protocol['private_audio_included'] is False and protocol['calibration_or_test_loaded'] is False
    history=read('history.json');selected=read('selected.json');data=read('data-audit.json')
    assert len(history)==50 and [r['epoch'] for r in history]==list(range(1,51))
    assert data['training_recordings']==2356 and data['selection_recordings']==180
    assert all(r['optimizer_steps']==r['epoch']*data['optimizer_steps_per_epoch'] for r in history)
    assert selected['epoch']==max(history,key=lambda r:r['selection_score'])['epoch']
    initial=read('initial-parameter-fingerprints.json')
    state=torch.load(source/'M2D.pt',map_location='cpu',weights_only=True)
    assert all(torch.isfinite(v).all() for v in state.values())
    changed=[k for k,digest in initial.items() if tensor_sha(state[k])!=digest]
    assert len(changed)==proof['changed_parameter_tensors']
    pretrained=args.cache/WEIGHT_FOLDER/'checkpoint-300.pth'
    assert sha(pretrained)==PRETRAINED_SHA
    original=torch.load(pretrained,map_location='cpu',weights_only=True)
    original=original.get('model',original)
    backbone_changed=[]
    for name,value in original.items():
        current=state['runtime.backbone.'+name]
        assert current.shape==value.shape,name
        same=torch.equal(current,value)
        if name in ['pos_embed','norm_stats'] or name.startswith('patch_embed.'):
            assert same,('Frozen pretrained tensor changed',name)
        elif not same:
            backbone_changed.append(name)
    blocks=sorted({int(k.split('.')[1]) for k in backbone_changed if k.startswith('blocks.')})
    assert blocks==list(range(12)) and proof['changed_transformer_blocks']==blocks
    report=dict(status='verified',archive_sha256=sha(args.archive),weights_sha256=sha(source/'M2D.pt'),
        uploaded_source_matched=True,private_data_uploaded=False,calibration_or_test_loaded=False,
        epochs_run=50,training_batches=history[-1]['optimizer_steps'],selected_epoch=selected['epoch'],
        selection_score=selected['score'],independently_changed_parameter_tensors=len(changed),
        independently_changed_transformer_blocks=blocks,independently_changed_backbone_tensors=len(backbone_changed),
        frozen_pretrained_tensors_exact=True,all_saved_tensors_finite=True,
        note='Training batch count includes AMP step attempts; not an independent accuracy estimate.')
    (args.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=HERE/'cache/m2d-weights')
    main(parser.parse_args())
