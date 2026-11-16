"""Verify all V13 snapshots against the exact V11 reference before evaluation."""
import argparse
import json
from pathlib import Path
import zipfile

import torch

from m2d_murmur import HERE,sha
from train_m2d_murmur import tensor_sha
from train_m2d_preserving import trainable_name,ENCODER_CHECKPOINT

EXPECTED={'protocol.json','data-audit.json','frozen-initial-sha.json','history.json','complete.json'}|{
    f'{prefix}{epoch}{suffix}' for epoch in [4,8,12] for prefix,suffix in [('M2D-epoch','.pt'),('selection-epoch','.json')]}


def main(a):
    torch.set_num_threads(2)
    if a.output.exists():raise ValueError('Preserve imported runs')
    with zipfile.ZipFile(a.archive) as z:
        assert len(z.infolist())==len(EXPECTED) and set(z.namelist())=={'artifacts/'+n for n in EXPECTED}
        assert all(i.file_size<500*1024**2 and (i.external_attr>>16)&0o170000!=0o120000 for i in z.infolist())
        assert sum(i.file_size for i in z.infolist())<2*1024**3 and z.testzip() is None
        a.output.mkdir(parents=True);z.extractall(a.output)
    source=a.output/'artifacts';read=lambda name:json.loads((source/name).read_text())
    complete=read('complete.json');protocol=read('protocol.json');initial=read('frozen-initial-sha.json')
    audit=json.loads(a.audit.read_text())
    assert complete['status']=='preserving_training_complete' and complete['epochs']==12
    assert sha(source/'protocol.json')==complete['protocol_sha256']
    for name,h in protocol['source_sha256'].items():
        assert h==audit['files_sha256'][name] and sha(HERE/name)==h,name
    assert protocol['config_sha256']==audit['config_sha256'] and protocol['bundle_sha256']==audit['bundle_sha256']
    assert all(protocol[k] is False for k in ['private_audio_included','private_profile_included','calibration_or_test_loaded'])
    assert sha(a.reference)==ENCODER_CHECKPOINT
    reference=torch.load(a.reference,map_location='cpu',weights_only=True)
    expected_frozen={k:tensor_sha(v) for k,v in reference.items() if not trainable_name(k)}
    assert expected_frozen==initial['frozen']
    for name,h in initial['trainable'].items():assert trainable_name(name) and tensor_sha(reference[name])==h
    history=read('history.json');data=read('data-audit.json')
    assert [r['epoch'] for r in history]==list(range(1,13))
    assert data['training_records']==2356 and data['selection_records']==180 and len(data['records'])==2536
    assert sum(data['training_class_counts'])==data['training_windows']
    steps=(data['training_windows']+31)//32
    assert all(r['batch_attempts']==r['epoch']*steps for r in history)
    verified={}
    for epoch in [4,8,12]:
        path=source/f'M2D-epoch{epoch}.pt';proof=complete['snapshots'][str(epoch)]
        assert sha(path)==proof['weights_sha256']
        state=torch.load(path,map_location='cpu',weights_only=True)
        assert set(state)==set(reference) and all(torch.isfinite(v).all() for v in state.values())
        assert all(state[k].shape==v.shape for k,v in reference.items())
        for name,h in expected_frozen.items():assert tensor_sha(state[name])==h,(epoch,name)
        changed=[name for name,h in initial['trainable'].items() if tensor_sha(state[name])!=h]
        blocks=sorted({int(k.split('.')[3]) for k in changed if k.startswith('runtime.backbone.blocks.')})
        assert blocks==[10,11] and 'classifier.weight' in changed
        assert len(changed)==proof['changed_parameter_tensors']
        verified[str(epoch)]=dict(weights_sha256=sha(path),changed_blocks=blocks,
            changed_parameter_tensors=len(changed),first_ten_blocks_and_normalization_exact=True,all_tensors_finite=True)
        del state
    report=dict(status='verified',snapshots=verified,epochs=12,batch_attempts=complete['batch_attempts'],
        archive_sha256=sha(a.archive),source_fingerprints_matched=True,reference_sha256=sha(a.reference),
        private_audio_used=False,calibration_audio_loaded=False,shipping_app_unchanged=True)
    (a.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['archive','output','audit','reference']:p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
