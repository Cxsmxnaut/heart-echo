"""Report consumed patient regression for the frozen phase-feature classifier."""
from pathlib import Path
import hashlib,json
import joblib,numpy as np
from sklearn.metrics import confusion_matrix,f1_score,balanced_accuracy_score
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'generated/valves-v3-phase'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
frozen=json.loads((OUT/'classifier-freeze.json').read_text());assert sha(OUT/'classifier.joblib')==frozen['classifier_sha256']
data=np.load(OUT/'regression.npz');assert not set(data['patients'])&set(frozen['patients'])
model=joblib.load(OUT/'classifier.joblib');scores=model.predict_proba(data['x']);pred=scores>=.5;y=data['y'];conditions={}
for j,k in enumerate(['AS','AR','MR','MS']):
 tn,fp,fn,tp=map(int,confusion_matrix(y[:,j],pred[:,j],labels=[0,1]).ravel());conditions[k]={'tp':tp,'fn':fn,'fp':fp,'tn':tn,'sensitivity':tp/max(tp+fn,1),'specificity':tn/max(tn+fp,1),'f1':float(f1_score(y[:,j],pred[:,j],zero_division=0)),'balanced_accuracy':float(balanced_accuracy_score(y[:,j],pred[:,j]))}
report={'model':'Frozen phase-aware acoustic encoder + 4 regularized classifiers','classifier_freeze_sha256':sha(OUT/'classifier-freeze.json'),'regression_feature_sha256':sha(OUT/'regression.npz'),'training_patients':len(frozen['patients']),'regression_patients':len(y),'patient_overlap':[],'per_condition':conditions,'macro_balanced_accuracy':float(np.mean([v['balanced_accuracy'] for v in conditions.values()])),'macro_f1':float(f1_score(y,pred,average='macro',zero_division=0)),'exact_label_match':float(np.mean(np.all(pred==y,axis=1))),'records':[{'patient':str(p),'truth':t.tolist(),'scores':s.tolist(),'predictions':g.astype(int).tolist()} for p,t,s,g in zip(data['patients'],y,scores,pred)],'limits':'Consumed22-patient retrospective regression, not fresh independent or phone validation. Eight recordings per patient. BMD-HS license CC BY-NC-ND4.0; local noncommercial research artifacts only, no distribution authorization claimed.'}
(ROOT/'results/valves-v3-phase-results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
