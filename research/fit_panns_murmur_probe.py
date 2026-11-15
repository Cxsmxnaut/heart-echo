"""Fit the two predeclared frozen-feature classifiers; development only."""
import hashlib,json,warnings
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
from murmur_focus_metrics import aggregate,promotion_checks

ROOT=Path(__file__).resolve().parent;ML=ROOT.parent/'ChestBPM/ML';OUT=ROOT/'generated/murmur-v6-pretrained-probe'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def main():
    assert not (OUT/'classifier-freeze.json').exists(),'Never refit after evaluation'
    complete=json.loads((OUT/'features-complete.json').read_text())
    for path,value in complete['files_sha256'].items():assert sha(OUT/path)==value
    protocol=json.loads((OUT/'protocol.json').read_text());assert protocol['classifier_source_sha256']==sha(__file__)
    assert protocol['cohort_manifest_sha256']==sha(ML/'murmur-phase-manifest.json')
    assert protocol['metrics_source_sha256']==sha(ROOT/'murmur_focus_metrics.py')
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role']!='test']
    positions={r['record']:r for r in json.loads((OUT/'records.json').read_text())}
    assert set(positions)=={r['record'] for r in rows}
    training=[r for r in rows if r['role']=='training' and positions[r['record']]['windows']]
    groups={role:{r['group'] for r in rows if r['role']==role} for role in ['training','selection','calibration']}
    assert not groups['training']&(groups['selection']|groups['calibration'])
    class_counts={c:sum(r['target']==c for r in training) for c in range(3)}
    indices=[];targets=[];weights=[];scale_weights=[]
    for r in training:
        pos=positions[r['record']];n=pos['windows']
        indices.extend(range(pos['offset'],pos['offset']+n));targets.extend([r['target']]*n)
        weights.extend([len(training)/(3*class_counts[r['target']]*n)]*n);scale_weights.extend([1/n]*n)
    baseline=json.loads((ROOT/'generated/murmur-focus-diagnosis/baseline-native-development.json').read_text())
    fitted={};predictions={}
    # Fit both models and freeze coefficients before inspecting either development outcome.
    for name in ['pretrained','random']:
        x=np.load(OUT/(name+'-features.npy'));scaler=StandardScaler().fit(x[indices],sample_weight=scale_weights)
        with warnings.catch_warnings():
            warnings.simplefilter('error',ConvergenceWarning)
            classifier=LogisticRegression(C=1.,max_iter=2000,random_state=protocol['seed']).fit(scaler.transform(x[indices]),targets,sample_weight=weights)
        assert classifier.classes_.tolist()==[0,1,2]
        np.savez(OUT/(name+'-classifier.npz'),mean=scaler.mean_,scale=scaler.scale_,coef=classifier.coef_,intercept=classifier.intercept_,classes=classifier.classes_)
        fitted[name]=(x,scaler,classifier)
    frozen={'source_sha256':sha(__file__),'protocol_sha256':sha(OUT/'protocol.json'),'metrics_sha256':sha(ROOT/'murmur_focus_metrics.py'),'classifiers':{name:sha(OUT/(name+'-classifier.npz')) for name in fitted},'regression_scored':False,'threshold':.60}
    save(OUT/'classifier-freeze.json',frozen)
    result={'protocol_sha256':sha(OUT/'protocol.json'),'classifier_freeze_sha256':sha(OUT/'classifier-freeze.json'),'roles':{},'regression_scored':False,'evidence':'Reused development only. A frozen-encoder linear-probe comparison; no independent or phone accuracy claim.'}
    for name,(x,scaler,classifier) in fitted.items():
        values={}
        for r in rows:
            if r['role']=='training':continue
            pos=positions[r['record']];a=pos['offset'];n=pos['windows']
            p=classifier.predict_proba(scaler.transform(x[a:a+n])).mean(0) if n else np.array([0.,0.,1.])
            top=int(p.argmax());label=top if p[top]>=.60 else 2
            values[r['record']]={'reading':{'finding':['absent','present','unsure'][label],'probabilities':p.tolist(),'windows':n}}
        predictions[name]=values;save(OUT/(name+'-development.json'),values)
    passes={name:True for name in fitted};added={name:0 for name in fitted}
    for role in ['selection','calibration']:
        cohort=[r for r in rows if r['role']==role];a=aggregate(cohort,baseline);result['roles'][role]={'baseline':a}
        for name in fitted:
            b=aggregate(cohort,predictions[name]);checks=promotion_checks(a,b);passes[name]&=all(checks.values())
            added[name]+=sum(b[level]['detected_positive']-a[level]['detected_positive'] for level in ['recordings','linked_people'])
            result['roles'][role][name]={'metrics':b,'checks':checks}
    result['development_gate']={name:bool(passes[name] and added[name]>0) for name in fitted}
    result['decision']='native_conversion_required_before_further_evaluation' if result['development_gate']['pretrained'] else 'retain_baseline_reject_frozen_pretrained_probe'
    save(ROOT/'results/murmur-v6-pretrained-probe.json',result)
    print(json.dumps({'development_gate':result['development_gate'],'decision':result['decision']},indent=2))

if __name__=='__main__':main()
