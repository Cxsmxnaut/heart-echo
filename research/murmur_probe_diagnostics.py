"""Diagnose frozen V6/V7 probes without fitting or choosing any thresholds."""
import json,hashlib
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score,log_loss

ROOT=Path(__file__).resolve().parent;ML=ROOT.parent/'ChestBPM/ML'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role']!='test']
    results={'purpose':'Post-fit diagnostics only: no parameter fitting, threshold search or regression scoring. Training metrics are in-sample. Development was reused. No clinical probability-calibration claim.','source_sha256':sha(__file__),'models':{}}
    for experiment in ['murmur-v6-pretrained-probe','murmur-v7-heartband-probe']:
        folder=ROOT/'generated'/experiment;complete=json.loads((folder/'features-complete.json').read_text());freeze=json.loads((folder/'classifier-freeze.json').read_text())
        for file,value in complete['files_sha256'].items():assert sha(folder/file)==value
        positions={r['record']:r for r in json.loads((folder/'records.json').read_text())}
        for arm in ['pretrained','random']:
            assert sha(folder/(arm+'-classifier.npz'))==freeze['classifiers'][arm]
            x=np.load(folder/(arm+'-features.npy'));weights=np.load(folder/(arm+'-classifier.npz'))
            scaled=x.astype(np.float32).copy();scaled-=weights['mean'];scaled/=weights['scale']
            logits=scaled@weights['coef'].T+weights['intercept'];logits-=logits.max(1,keepdims=True);p=np.exp(logits);p/=p.sum(1,keepdims=True)
            probabilities={}
            for r in rows:
                pos=positions[r['record']];start=pos['offset'];n=pos['windows']
                probabilities[r['record']]=p[start:start+n].mean(0) if n else np.array([0.,0.,1.])
            saved=json.loads((folder/(arm+'-development.json')).read_text())
            difference=max(float(np.max(np.abs(probabilities[k]-v['reading']['probabilities']))) for k,v in saved.items())
            assert difference<1e-5,difference
            name=experiment+'/'+arm;results['models'][name]={'coefficient_replay_maximum_probability_difference':difference}
            for role in ['training','selection','calibration']:
                cohort=[r for r in rows if r['role']==role];known=[r for r in cohort if r['target']!=2]
                target=[r['target'] for r in cohort];probs=np.stack([probabilities[r['record']] for r in cohort])
                sums=probs.astype(np.float64).sum(1,keepdims=True)
                assert np.max(np.abs(sums-1))<1e-5
                probs=probs.astype(np.float64)/sums  # Only remove float32 averaging roundoff for log loss.
                results['models'][name][role]={'records':len(cohort),'known_records':len(known),'known_label_present_probability_auc':float(roc_auc_score([r['target'] for r in known],[probabilities[r['record']][1] for r in known])),'three_class_log_loss':float(log_loss(target,probs,labels=[0,1,2]))}
    (ROOT/'results/murmur-frozen-probe-diagnostics.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
