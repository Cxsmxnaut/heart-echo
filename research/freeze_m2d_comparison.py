"""Choose between both frozen M2D arms using selection only, before calibration."""
import argparse
import json
from pathlib import Path

from m2d_murmur import sha,HERE


def main(args):
    if args.output.exists():
        raise ValueError('Preserve the pre-evaluation model choice')
    models={}
    for name,path in [('paper',args.paper),('released',args.released)]:
        path=path.resolve()
        complete=json.loads((path/'complete.json').read_text())
        assert complete['status']=='m2d_training_complete'
        assert complete['proof']['epochs_run']==50
        assert complete['proof']['changed_transformer_blocks']==list(range(12))
        assert sha(path/'protocol.json')==complete['protocol_sha256']
        assert sha(path/'M2D.pt')==complete['proof']['weights_sha256']
        protocol=json.loads((path/'protocol.json').read_text())
        for filename,fingerprint in protocol['source_sha256'].items():
            assert sha(HERE/filename)==fingerprint,filename
        assert protocol['calibration_or_test_loaded'] is False
        assert protocol['private_audio_included'] is False
        history=json.loads((path/'history.json').read_text())
        chosen=json.loads((path/'selected.json').read_text())
        assert len(history)==50
        best=max(history,key=lambda row:row['selection_score'])
        assert chosen['epoch']==best['epoch'] and chosen['score']==best['selection_score']
        models[name]=dict(source_directory=str(path),weights_sha256=sha(path/'M2D.pt'),
            protocol_sha256=sha(path/'protocol.json'),data_audit_sha256=sha(path/'data-audit.json'),
            selected_epoch=chosen['epoch'],selection_score=chosen['score'],config_sha256=protocol['config_sha256'])
    assert models['paper']['config_sha256']==models['released']['config_sha256']
    # The first item wins ties; the rule is fixed before reading calibration.
    champion=max(['paper','released'],key=lambda name:models[name]['selection_score'])
    result=dict(models=models,chosen_by_selection_only=champion,
        evaluator_sha256=sha(HERE/'evaluate_m2d_murmur.py'),
        tie_rule='paper first',threshold=.60,frozen_before_this_run_calibration_audio=True,
        evidence='Both selection sets reused. Two arms; released arm added after first paper-arm selection observations.',
        app_update_authorized_by_this_file=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(chosen_by_selection_only=champion,selection_scores={k:v['selection_score'] for k,v in models.items()})))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper',type=Path,required=True)
    parser.add_argument('--released',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
