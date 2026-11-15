"""Three-outcome murmur metrics; retain abstentions and linked-person grouping."""
from collections import defaultdict
import math
import numpy as np
LABELS={'absent':0,'present':1,'unsure':2}
def counts(truth,pred):
    truth=list(truth);pred=list(pred)
    if len(truth)!=len(pred):raise ValueError('Every label must have one prediction')
    if any(x not in (0,1,2) for x in truth+pred):raise ValueError('Labels must be Absent, Present or Unknown')
    matrix=np.zeros((3,3),dtype=int)
    for a,b in zip(truth,pred):matrix[int(a),int(b)]+=1
    tp=int(matrix[1,1]);fn=int(matrix[1,0]);pu=int(matrix[1,2]);fp=int(matrix[0,1]);tn=int(matrix[0,0]);nu=int(matrix[0,2]);unknown=matrix[2].tolist();n=int(matrix.sum());known=int(matrix[:2].sum())
    ratio=lambda a,b:a/b if b else None
    return {'matrix':matrix.tolist(),'detected_positive':tp,'positive_called_absent':fn,'positive_unsure':pu,'positive_count':tp+fn+pu,'false_alarms':fp,'correct_absent':tn,'negative_unsure':nu,'negative_count':fp+tn+nu,'expert_unknown_outputs':unknown,'total_unsure':int(matrix[:,2].sum()),'total':n,'positive_detection_all':ratio(tp,tp+fn+pu),'negative_clearance_all':ratio(tn,fp+tn+nu),'false_alarm_fraction':ratio(fp,fp+tn+nu),'known_coverage':ratio(known-pu-nu,known),'positive_detection_answered_only':ratio(tp,tp+fn),'specificity_answered_only':ratio(tn,tn+fp)}
def aggregate(rows,predictions):
    truth=[r['target'] for r in rows];pred=[LABELS[predictions[r['record']]['reading']['finding']] for r in rows]
    groups=defaultdict(list)
    for r,p in zip(rows,pred):groups[r['group']].append((r,p))
    gt=[];gp=[];people=[]
    for group,values in sorted(groups.items()):
        labels={r['patient_target'] for r,p in values};t=1 if 1 in labels else 2 if 2 in labels else 0
        guesses={p for r,p in values};p=1 if 1 in guesses else 2 if 2 in guesses else 0
        gt.append(t);gp.append(p);people.append({'group':group,'target':t,'prediction':p,'recordings':len(values)})
    return {'recordings':counts(truth,pred),'linked_people':counts(gt,gp),'people':people}
def wilson(success,total,z=1.959963984540054):
    if not total:return None
    p=success/total;d=1+z*z/total;c=(p+z*z/(2*total))/d;m=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [max(0.,c-m),min(1.,c+m)]
def promotion_checks(base,candidate):
    result={}
    for level in ['recordings','linked_people']:
        a,b=base[level],candidate[level]
        if any(a[k]!=b[k] for k in ['positive_count','negative_count','total']):raise ValueError('Compare the same cohort')
        for key in ['detected_positive','correct_absent']:result[level+'_'+key+'_not_lower']=b[key]>=a[key]
        for key in ['positive_called_absent','false_alarms','total_unsure']:result[level+'_'+key+'_not_higher']=b[key]<=a[key]
        result[level+'_expert_unknown_retained']=b['expert_unknown_outputs'][2]>=a['expert_unknown_outputs'][2]
    return result
