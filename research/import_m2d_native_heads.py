"""Independently verify a completed V12 head run without reading clinical audio."""
import argparse
import json
from pathlib import Path
import zipfile

import torch

from m2d_murmur import HERE,sha
from train_m2d_murmur import tensor_sha

FILES={'protocol.json','data-audit.json','native-heads.pt','selection-predictions.json','history.json','complete.json'}


def main(a):
    torch.set_num_threads(2)
    if a.output.exists():raise ValueError('Preserve imported runs')
    with zipfile.ZipFile(a.archive) as z:
        assert len(z.infolist())==len(FILES)
        assert set(z.namelist())=={'artifacts/'+n for n in FILES}
        assert all(i.file_size<15*1024**2 and (i.external_attr>>16)&0o170000!=0o120000 for i in z.infolist())
        assert z.testzip() is None
        a.output.mkdir(parents=True);z.extractall(a.output)
    source=a.output/'artifacts';read=lambda name:json.loads((source/name).read_text())
    complete=read('complete.json');protocol=read('protocol.json');data=read('data-audit.json')
    assert complete['status']=='native_head_training_complete' and complete['encoder_unchanged'] is True
    assert sha(source/'protocol.json')==complete['protocol_sha256']
    assert sha(source/'native-heads.pt')==complete['heads_sha256']
    audit=json.loads(a.audit.read_text())
    for name,h in protocol['source_sha256'].items():
        assert h==audit['files_sha256'][name] and sha(HERE/name)==h,name
    assert protocol['bundle_sha256']==audit['public_native_zip_sha256']
    assert protocol['config_sha256']==audit['public_config_sha256']
    assert all(protocol[k] is False for k in ['private_audio_included','private_profile_included','calibration_or_test_loaded'])
    assert data['training_records']==2356 and data['selection_records']==180 and data['training_only_normalization']
    assert len(data['records'])==2536 and sum(data['training_class_counts'])==data['training_windows']
    history=read('history.json')
    assert len(history)==64
    for cost in [2.,4.,8.,12.]:assert [r['epoch'] for r in history if r['positive_cost']==cost]==list(range(1,17))
    assert sha(a.encoder)==protocol['encoder_checkpoint_sha256']
    state=torch.load(a.encoder,map_location='cpu',weights_only=True)
    original={k[len('runtime.'):]:tensor_sha(v) for k,v in state.items() if k.startswith('runtime.')}
    assert original==complete['encoder_fingerprints']
    heads=torch.load(source/'native-heads.pt',map_location='cpu',weights_only=True)
    expected={'normalization_only'}|{f'positive_cost_{c}_epoch_{e}' for c in [2,4,8,12] for e in [4,8,16]}
    assert set(heads)==expected and len(heads)==13
    for name,head in heads.items():
        w=head['classifier']['weight'];b=head['classifier']['bias']
        mu=head['norm']['running_mean'];var=head['norm']['running_var']
        assert w.shape==(3,3840) and b.shape==(3,) and mu.shape==var.shape==(3840,)
        assert all(torch.isfinite(v).all() for group in head.values() for v in group.values())
        assert (var>0).all()
        if name=='normalization_only':
            assert torch.equal(w,state['classifier.weight']) and torch.equal(b,state['classifier.bias'])
        else:
            old_std=(state['norm.running_var']+1e-5).sqrt()
            initial_w=state['classifier.weight']*((var+1e-5).sqrt()/old_std)
            initial_b=state['classifier.bias']+state['classifier.weight']@((mu-state['norm.running_mean'])/old_std)
            assert not torch.equal(w,initial_w) and not torch.equal(b,initial_b)
    report=dict(status='verified',archive_sha256=sha(a.archive),heads_sha256=sha(source/'native-heads.pt'),
        source_fingerprints_matched=True,encoder_fingerprints_independently_matched=True,
        candidate_heads=13,trained_checkpoints=12,normalization_control_verified=True,
        all_saved_tensors_finite=True,calibration_audio_loaded=False,app_updated=False)
    (a.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['archive','output','audit','encoder']:p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
