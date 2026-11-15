"""Evaluate the unchanged shipping Core ML model on original PASCAL A archives.
Public research access is offered by challenge authors. No audio is redistributed.
"""
from pathlib import Path
import hashlib, json, subprocess, io, zipfile
import numpy as np
from scipy.io import wavfile
from acquire import fetch
ROOT=Path(__file__).resolve().parent; WORK=ROOT.parent; CACHE=ROOT/'cache/pascal-a'; OUT=ROOT/'results'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def run():
    model=WORK/'HeartEcho/Models/Murmur.mlpackage'; executable=ROOT/'generated/murmur-probe'
    frozen={'model_files':{str(p.relative_to(model)):sha(p) for p in sorted(model.rglob('*')) if p.is_file()},'inference_source_sha256':sha(WORK/'HeartEcho/Engine/MurmurAnalysis.swift'),'probe_source_sha256':sha(WORK/'ChestBPM/Tools/MurmurProbe.swift'),'evaluator_sha256':sha(__file__),'native_executable_sha256':sha(executable),'archive_note':'The extra-heart-sound archive uses Atraining_extrahls internally. V3 adds those 19 controls; the original normal/murmur/artifact cases and inference are unchanged.', 'initial_attempt':'The initial probe was given the package instead of its containing directory and failed before producing results; corrected invocation only. Original freeze preserved.', 'threshold':.60,'protocol':'Use every normal/murmur file from PASCAL A with original archive category as reference. Count short/rejected audio as unsure; report all artifact/extra-sound predictions separately. Do not tune or train on these files. Exact decoded-waveform overlap with all cached CirCor files is excluded and listed. No person IDs available; no patient-independent or clinical accuracy claim.'}
    path=OUT/'external-murmur-v3-freeze.json'
    if path.exists():assert json.loads(path.read_text())==frozen,'Frozen external experiment changed'
    else:save(path,frozen)
    files=[];archives={}
    for label in ['normal','murmur','artifact','extrahs']:
        name=f'Atraining_{label}.zip';url='https://www.peterjbentley.com/heartchallenge/wav/'+name
        archive=fetch(url,CACHE/name);archives[name]={'source':url,'sha256':hashlib.sha256(archive).hexdigest()}
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for item in z.infolist():
                assert (CACHE/item.filename).resolve().is_relative_to(CACHE.resolve())
            z.extractall(CACHE)
        for file in sorted((CACHE/('Atraining_extrahls' if label == 'extrahs' else f'Atraining_{label}')).rglob('*.wav')):files.append({'id':file.stem,'path':str(file),'reference':label,'sha256':sha(file)})
    def wavehash(path):
        rate,x=wavfile.read(path)
        return hashlib.sha256(str(rate).encode()+x.tobytes()).hexdigest()
    seen={wavehash(p) for p in (WORK/'ChestBPM/ML/cache/circor').rglob('*.wav')}
    overlaps=[r['id'] for r in files if wavehash(r['path']) in seen]
    requests=[{'id':r['id'],'path':r['path']} for r in files if r['id'] not in overlaps]
    request=CACHE/'requests.json';save(request,requests)
    output=subprocess.run([str(executable),str(request),str(model.parent)],check=True,capture_output=True,text=True)
    predictions={r['id']:r for r in map(json.loads,output.stdout.splitlines())}
    matrix={k:{p:0 for p in ['present','absent','unsure']} for k in ['normal','murmur','artifact','extrahs']};errors=[];records=[]
    for r in files:
        if r['id'] in overlaps:continue
        pred=predictions[r['id']]['reading']; matrix[r['reference']][pred['finding']]+=1
        row={'id':r['id'],'reference':r['reference'],'prediction':pred['finding'],'seconds':pred['seconds'],'windows':pred['windows'],'sha256':r['sha256']}
        records.append(row)
        if r['reference']=='murmur' and pred['finding']!='present' or r['reference']=='normal' and pred['finding']=='present':errors.append(row)
    pos=sum(matrix['murmur'].values());neg=sum(matrix['normal'].values())
    report={'freeze':frozen,'archives':archives,'circor_cached_waveforms_checked':len(seen),'exact_waveform_overlaps_excluded':overlaps,'matrix':matrix,'murmur_detection_fraction':matrix['murmur']['present']/pos,'false_alarm_fraction':matrix['normal']['present']/neg,'positive_called_absent':matrix['murmur']['absent'],'positive_unsure':matrix['murmur']['unsure'],'normal_unsure':matrix['normal']['unsure'],'always_absent_baseline':{'murmurs_detected':0,'positive_called_absent':pos,'normal_false_alarms':0,'unsure':0},'records':records,'errors':errors,'limitations':['Original archive categories are challenge reference labels, not verified diagnoses.','Public iStethoscope Pro recordings are different from our capture method. This does not establish current-iPhone murmur accuracy.','Unknown participant identities prevent proving patient independence or patient-level metrics.','Only exact decoded-waveform overlap is checked; transformed or partial duplicates can remain.','Challenge page invites research and specifies citation, but an explicit redistribution license was not found. Audio is not included in the release.'],'citation':'Bentley P, Nordehn G, Coimbra M, Mannor S. PASCAL Classifying Heart Sounds Challenge 2011. https://www.peterjbentley.com/heartchallenge/'}
    save(OUT/'external-murmur-results.json',report);print(json.dumps({k:report[k] for k in ['matrix','murmur_detection_fraction','false_alarm_fraction','positive_called_absent','positive_unsure']},indent=2))
if __name__=='__main__':run()
