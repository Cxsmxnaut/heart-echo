"""Patient-disjoint 5-fold selection on original BMD training patients only.
A regularized small-data classifier uses the frozen phase/timing audio encoder.
"""
from pathlib import Path
import hashlib,json
import joblib,numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.model_selection import KFold
from sklearn.metrics import f1_score,balanced_accuracy_score
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'generated/valves-v3-phase'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def train():
 protocol={'source_sha256':sha(__file__),'feature_protocol_sha256':sha(OUT/'feature-protocol.json'),'data_sha256':sha(OUT/'training.npz'),'grid_C':[.0001,.001,.01,.1,1.],'split':'5-fold KFold on patient rows, shuffled with seed20261119; all eight recordings stay together','model':'StandardScaler fit inside each fold; 4 independent L2 logistic models, no class weights; max_iter2000; fixed .5 threshold','selection':'Max mean per-condition balanced accuracy of out-of-fold training-patient predictions, then macro F1. Refit once on all86 original training patients after selecting C. Original22 test patients remain consumed regression, never used in selection.','inputs':'Frozen public acoustic/phase features only. No labels, diagnosis filename tokens or demographic data in inputs.'}
 if (OUT/'classifier-freeze.json').exists():raise ValueError('Frozen classifier exists; do not overwrite')
 save(OUT/'classifier-protocol.json',protocol);data=np.load(OUT/'training.npz');X=data['x'];Y=data['y'];folds=list(KFold(5,shuffle=True,random_state=20261119).split(X));history=[];best=(-1.,-1.);best_c=None
 def build(c):return make_pipeline(StandardScaler(),OneVsRestClassifier(LogisticRegression(C=c,max_iter=2000,solver='lbfgs')))
 for c in protocol['grid_C']:
  predictions=np.zeros_like(Y)
  for train,validation in folds:
   m=build(c).fit(X[train],Y[train]);predictions[validation]=m.predict(X[validation])
  balanced=float(np.mean([balanced_accuracy_score(Y[:,j],predictions[:,j]) for j in range(4)]));f1=float(f1_score(Y,predictions,average='macro',zero_division=0));row={'C':c,'patient_out_of_fold_macro_balanced_accuracy':balanced,'patient_out_of_fold_macro_f1':f1};history.append(row);print(json.dumps(row),flush=True)
  if (balanced,f1)>best:best=(balanced,f1);best_c=c
 model=build(best_c).fit(X,Y);path=OUT/'classifier.joblib';joblib.dump(model,path);save(OUT/'classifier-freeze.json',{'protocol':protocol,'selected_C':best_c,'cross_validation':history,'classifier_sha256':sha(path),'patients':data['patients'].tolist(),'training_patient_count':len(X),'feature_dimension':X.shape[1]});print('FROZEN',best_c,best,flush=True)
if __name__=='__main__':train()
