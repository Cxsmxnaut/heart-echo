"""Fixed, reproducible public-data experiments. Read protocol.json before running."""
import argparse, csv, hashlib, json, math, platform
from collections import Counter
from pathlib import Path
import joblib, numpy as np, scipy, scipy.signal as sig
from scipy.io import wavfile
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, accuracy_score, roc_auc_score
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'cache'; OUT=ROOT/'results'; GEN=ROOT/'generated'
GEN.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value): Path(p).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def features(path):
    rate,x=wavfile.read(path)
    if x.ndim>1: x=x.astype(float).mean(axis=1)
    else: x=x.astype(float)
    x=x[:rate*60]; assert len(x)>=rate, path
    x-=x.mean(); x/=max(np.sqrt(np.mean(x*x)),1e-12)
    x=sig.resample_poly(x,2000//math.gcd(rate,2000),rate//math.gcd(rate,2000))
    f,t,z=sig.stft(x,2000,nperseg=2000,noverlap=1000,boundary=None)
    power=np.abs(z)**2
    bands=np.geomspace(20,950,25)
    log=np.stack([np.log10(np.maximum(power[(f>=a)&(f<b)].mean(axis=0),1e-12)) for a,b in zip(bands[:-1],bands[1:])])
    out=np.r_[log.mean(axis=1),log.std(axis=1),np.mean(np.abs(np.diff(x))),np.mean(x[:-1]*x[1:]),np.quantile(np.abs(x),.95),np.mean(np.abs(x)>3)]
    assert np.isfinite(out).all()
    return out

def measures(y,p,prob=None):
    tn,fp,fn,tp=map(int,confusion_matrix(y,p,labels=[0,1]).ravel())
    ratio=lambda a,b: a/b if b else None
    result=dict(tp=tp,fn=fn,fp=fp,tn=tn,sensitivity=ratio(tp,tp+fn),specificity=ratio(tn,tn+fp),precision=ratio(tp,tp+fp),f1=float(f1_score(y,p,zero_division=0)),accuracy=float(accuracy_score(y,p)))
    if prob is not None and len(set(y))==2: result['roc_auc']=float(roc_auc_score(y,prob))
    return result

def model(): return RandomForestClassifier(n_estimators=240,max_depth=10,min_samples_leaf=3,class_weight='balanced_subsample',random_state=20261115,n_jobs=2)
def positive(m,x):
    p=m.predict_proba(x)
    return p[:,list(m.classes_).index(1)] if 1 in m.classes_ else np.zeros(len(x))
def freeze(kind):
    p=OUT/(kind+'-experiment-freeze.json')
    value={'experiment_source_sha256':sha(__file__),'protocol_sha256':sha(ROOT/'protocol.json'),'acquisition_source_sha256':sha(ROOT/'acquire.py'),'numpy':np.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__,'python':platform.python_version()}
    if p.exists(): assert json.loads(p.read_text())==value,'Frozen experiment changed; do not overwrite evidence'
    else: save(p,value)
    return value

def bmd():
    frozen=freeze('bmd'); root=CACHE/'bmd'; rows=list(csv.DictReader((root/'train.csv').open())); labels=['AS','AR','MR','MS']
    valid=[r for r in rows if all(r[k] in ['0','1'] for k in labels)]
    ordered=sorted(valid,key=lambda r:hashlib.sha256(('heart-echo-valves-20261115:'+r['patient_id']).encode()).hexdigest())
    cut=int(.8*len(ordered)); train={r['patient_id'] for r in ordered[:cut]}; test={r['patient_id'] for r in ordered[cut:]}; assert not train&test
    audit={'release_patient_ids':len(rows),'labeled_patients':len(valid),'excluded':[r['patient_id'] for r in rows if r not in valid],'release_wav_files':len(list((root/'train').glob('*.wav'))),'license':(root/'LICENSE').read_text(),'train_patients':sorted(train),'test_patients':sorted(test),'source_commit':json.loads((root/'commit.json').read_text())['sha']}
    X=[];Y=[];ids=[]; hashes={};wave_hashes={}
    for row in ordered:
        vectors=[]
        for n in range(1,9):
            file=root/'train'/(row[f'recording_{n}']+'.wav'); vectors.append(features(file)); hashes[file.name]=sha(file)
            rate,wave=wavfile.read(file); key=hashlib.sha256(wave.tobytes()).hexdigest(); wave_hashes.setdefault(key,[]).append(row['patient_id'])
        vectors=np.stack(vectors); X.append(np.r_[vectors.mean(axis=0),vectors.std(axis=0)]);Y.append([int(row[k]) for k in labels]);ids.append(row['patient_id'])
    crossings=[v for v in wave_hashes.values() if any(p in train for p in v) and any(p in test for p in v)]
    assert not crossings,'Duplicate waveforms cross patient split'
    X=np.stack(X);Y=np.array(Y); istrain=np.array([p in train for p in ids]); report={'audit':audit,'freeze':frozen,'per_condition':{},'waveform_cross_split_duplicates':crossings,'input_feature_sha256':hashlib.sha256(X.tobytes()).hexdigest(),'errors':[],'limits':json.loads((ROOT/'protocol.json').read_text())['valves']['limit']}
    predictions=[]
    for j,label in enumerate(labels):
        m=model().fit(X[istrain],Y[istrain,j]); path=GEN/('bmd-'+label+'.joblib');joblib.dump(m,path)
        prob=positive(m,X[~istrain]);pred=(prob>=.5).astype(int);predictions.append(pred)
        baseline=int(Y[istrain,j].mean()>.5)
        report['per_condition'][label]={'training_positives':int(Y[istrain,j].sum()),'test_positives':int(Y[~istrain,j].sum()),'model':measures(Y[~istrain,j],pred,prob),'baseline':measures(Y[~istrain,j],np.full(len(pred),baseline)),'model_sha256':sha(path)}
        for patient,truth,guess,p in zip(np.array(ids)[~istrain],Y[~istrain,j],pred,prob):
            if truth!=guess: report['errors'].append({'public_patient_id':str(patient),'condition':label,'truth':int(truth),'prediction':int(guess),'score':float(p)})
    report['exact_patient_label_match']=float(np.mean(np.all(np.stack(predictions,axis=1)==Y[~istrain],axis=1)))
    report['audio_sha256']=hashes;save(OUT/'bmd-results.json',report);print(json.dumps(report['per_condition'],indent=2),flush=True)

def physio():
    frozen=freeze('physionet2016');root=CACHE/'physionet2016'; rows=[]
    for reference in sorted(root.glob('training-*/REFERENCE.csv')):
        for name,label in csv.reader(reference.open()): rows.append((reference.parent/(name+'.wav'),int(label=='1'),reference.parent.name[-1]))
    X=[]; hashes={}; wave_hashes={}
    for i,(p,y,source) in enumerate(rows):
        X.append(features(p)); hashes[str(p.relative_to(root))]=sha(p)
        rate,w=wavfile.read(p); key=hashlib.sha256(w.tobytes()).hexdigest(); wave_hashes.setdefault(key,[]).append(str(p.relative_to(root)))
        if i%300==0:print('PhysioNet features',i,'/',len(rows),flush=True)
    X=np.stack(X);Y=np.array([r[1] for r in rows]);train=np.array([r[2]!='f' for r in rows]);
    duplicates=[v for v in wave_hashes.values() if any(p.startswith('training-f/') for p in v) and any(not p.startswith('training-f/') for p in v)]
    assert not duplicates,'Exact waveform duplicate crosses source split'
    m=model().fit(X[train],Y[train]);path=GEN/'physionet2016.joblib';joblib.dump(m,path);p=positive(m,X[~train]);pred=(p>=.5).astype(int)
    baseline=int(Y[train].mean()>.5); report={'freeze':frozen,'train_recordings':int(train.sum()),'test_recordings':int((~train).sum()),'source_counts':dict(Counter(r[2] for r in rows)),'model':measures(Y[~train],pred,p),'baseline':measures(Y[~train],np.full(len(pred),baseline)),'model_sha256':sha(path),'input_feature_sha256':hashlib.sha256(X.tobytes()).hexdigest(),'waveform_cross_split_duplicates':duplicates,'audio_sha256':hashes,'errors':[],'limits':json.loads((ROOT/'protocol.json').read_text())['normal_abnormal']['split_limit']}
    for row,truth,guess,score in zip([r for r in rows if r[2]=='f'],Y[~train],pred,p):
        if truth!=guess:report['errors'].append({'recording':row[0].stem,'truth':int(truth),'prediction':int(guess),'score':float(score)})
    save(OUT/'physionet2016-results.json',report);print(json.dumps({k:report[k] for k in ['train_recordings','test_recordings','model','baseline']},indent=2),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('experiment',choices=['bmd','physio']);args=parser.parse_args();{'bmd':bmd,'physio':physio}[args.experiment]()
