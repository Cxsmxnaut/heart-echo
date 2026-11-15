"""Supplement the frozen original-label experiment; never retrain or retune."""
from pathlib import Path
import csv,hashlib,json
from experiments import measures
ROOT=Path(__file__).resolve().parent;cache=ROOT/'cache/physionet2016';result=json.loads((ROOT/'results/physionet2016-results.json').read_text())
# Recover the model's predictions from its saved test errors and original references.
errors={r['recording']:r['prediction'] for r in result['errors']}; y=[];p=[];sources={}
for c in 'abcdef':
 updated=cache/f'training-{c}/REFERENCE_withSQI.csv';rows=list(csv.reader(updated.open()));old=dict(csv.reader((cache/f'training-{c}/REFERENCE.csv').open()))
 sources[c]={'rows':len(rows),'sha256':hashlib.sha256(updated.read_bytes()).hexdigest(),'classification_changes':sum(old.get(r[0])!=r[1] for r in rows),'unavailable_in_updated':len(set(old)-{r[0] for r in rows}),'unsure_quality':sum(r[2]=='0' for r in rows)}
 if c=='f':
  for name,label,quality in rows:
   if quality!='1':continue
   truth=int(label=='1');y.append(truth);p.append(errors.get(name,truth))
report={'note':'Post-run reporting audit only. Class labels agree where present; no retraining or tuning. Original protocol/results remain unchanged. Updated source E omits 87 archive records. Five source-F recordings are marked quality unsure.','source':'https://physionet.org/files/challenge-2016/1.0.0/annotations/updated/','sources':sources,'test_quality_usable_count':len(y),'unchanged_model_on_quality_usable_test':measures(y,p),'baseline_on_quality_usable_test':measures(y,[0]*len(y))}
(ROOT/'results/physionet2016-quality-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
