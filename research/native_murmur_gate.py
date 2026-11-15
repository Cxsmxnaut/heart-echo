"""Compare native shipping/candidate models on development before regression use."""
import json,subprocess,sys
from pathlib import Path
from train_audio_models import ROOT,ML,digest,save
from murmur_model import metrics

def native(model,requests,tag):
    p=ROOT/'cache'/('native-'+tag+'.json');save(p,requests)
    r=subprocess.run([str(ROOT/'generated/murmur-probe'),str(p),str(model)],capture_output=True,text=True,check=True)
    return {v['id']:v for v in map(json.loads,r.stdout.splitlines())}
def gate():
    out=ROOT/'results/native-v2-murmur-development.json'
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role'] in ['selection','calibration']]
    requests=[{'id':r['record'],'path':str(ML/'cache/circor'/r['file'])} for r in rows]
    models={'shipping':ROOT.parent/'HeartEcho/Models','candidate':ROOT/'generated/audio-v2-murmur/native'}
    outputs={key:native(path,requests,'v2-'+key) for key,path in models.items()};mapping={'absent':0,'present':1,'unsure':2};report={}
    for role in ['selection','calibration']:
        group=[r for r in rows if r['role']==role];y=[r['target'] for r in group]
        report[role]={key:metrics(y,[mapping[values[r['record']]['reading']['finding']] for r in group]) for key,values in outputs.items()}
    report['native_models_sha256']={key:{str(p.relative_to(path)):digest(p) for p in (path/'Murmur.mlpackage').rglob('*') if p.is_file()} for key,path in models.items()}
    report['note']='Development partitions were reused in prior research. Same native input checks, audio conversion, window positions and threshold. No regression data read by this gate.'
    save(out,report);print(json.dumps({k:report[k] for k in ['selection','calibration']},indent=2))
if __name__=='__main__':gate()
