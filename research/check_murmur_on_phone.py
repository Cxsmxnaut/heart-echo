"""Run frozen baseline parity in an isolated app build, then restore the app.

Uses the existing app identifier: no extra test-runner app or app deletion.
Only public bundled samples are read. Product source/model files stay unchanged.
"""
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
STAGE=ROOT/'generated/murmur-phone-validation'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def call(args,log,**kwargs):
    result=subprocess.run(list(map(str,args)),stdout=log,stderr=subprocess.STDOUT,**kwargs)
    if result.returncode:raise RuntimeError('Command failed: '+str(args[0])+'; see validation log')
    return result

def main():
    assert not STAGE.exists(),'Preserve prior validation artifacts; use a separate stage for a new run'
    frozen=json.loads((ROOT/'results/murmur-focus-baseline-freeze.json').read_text())
    model=WORK/'HeartEcho/Models/Murmur.mlpackage'
    assert frozen['model_files']=={str(p.relative_to(model)):sha(p) for p in sorted(model.rglob('*')) if p.is_file()}
    assert frozen['native_reader_sha256']==sha(WORK/'HeartEcho/Engine/MurmurAnalysis.swift')
    STAGE.mkdir(parents=True)
    inventory=STAGE/'device-state.json'
    subprocess.run(['xcrun','devicectl','list','devices','--json-output',str(inventory)],stdout=subprocess.DEVNULL,check=True)
    devices=json.loads(inventory.read_text())['result']['devices']
    devices=[d for d in devices if d.get('hardwareProperties',{}).get('deviceType')=='iPhone' and d.get('connectionProperties',{}).get('tunnelState')=='connected' and d.get('deviceProperties',{}).get('developerModeStatus')=='enabled']
    assert len(devices)==1,'Expected one reachable developer-enabled iPhone'
    device=devices[0]['identifier']
    source=WORK/'HeartEcho';stage=STAGE/'HeartEcho'
    shutil.copytree(source,stage,ignore=shutil.ignore_patterns('build*','Docs','Tests','Tools','UITests','.DS_Store'))
    entry=stage/'HeartEchoApp/HeartEchoApp.swift'
    original=entry.read_text();remaining=original[original.index('enum AppTab:'):]
    entry.write_text('import SwiftUI\n@main struct HeartEchoApp: App { var body: some Scene { WindowGroup { Text("Checking the frozen murmur model…").task { MurmurPhoneCheck.run() } } } }\n'+remaining+'\n'+(ROOT/'MurmurPhoneCheck.swift').read_text())
    samples=source/'Resources/MurmurSamples'
    requests=[{'id':name,'path':str(samples/(name+'.wav'))} for name in ['absent','present','unknown']]
    save(STAGE/'requests.json',requests)
    result=subprocess.run([str(ROOT/'generated/murmur-probe'),str(STAGE/'requests.json'),str(source/'Models')],capture_output=True,text=True,check=True)
    cases=list(map(json.loads,result.stdout.splitlines()))
    assert {r['id'] for r in cases}=={r['id'] for r in requests}
    fixture={'cases':cases,'input_sha256':{r['id']:sha(r['path']) for r in requests},'baseline_model_files':frozen['model_files'],'native_reader_sha256':frozen['native_reader_sha256']}
    save(stage/'Resources/MurmurSamples/phone-check-expected.json',fixture)
    restore=source/'build-phone/Build/Products/Debug-iphoneos/HeartEchoApp.app'
    assert restore.exists(),'A signed normal app must exist for restoration'
    report={'source_sha256':sha(__file__),'harness_sha256':sha(ROOT/'MurmurPhoneCheck.swift'),'baseline_freeze_sha256':sha(ROOT/'results/murmur-focus-baseline-freeze.json'),'fixture':fixture,'app_source_changed':False,'app_model_changed':False,'normal_app_restored':False}
    logpath=STAGE/'validation.log'
    with logpath.open('w') as log:
        call(['xcodebuild','build','-project',stage/'HeartEchoApp.xcodeproj','-scheme','HeartEchoApp','-configuration','Debug','-destination','id='+device,'-derivedDataPath',STAGE/'build','-allowProvisioningUpdates'],log)
        app=STAGE/'build/Build/Products/Debug-iphoneos/HeartEchoApp.app'
        try:
            call(['xcrun','devicectl','device','install','app','--device',device,app],log)
            launch=subprocess.run(['xcrun','devicectl','device','process','launch','--device',device,'--terminate-existing','--console','--timeout','45','app.veritas.heartecho'],capture_output=True,text=True)
            (STAGE/'phone-console.log').write_text(launch.stdout+launch.stderr)
            outputs=[line.split('MURMUR_PHONE_CHECK=',1)[1] for line in launch.stdout.splitlines() if 'MURMUR_PHONE_CHECK=' in line]
            assert len(outputs)==1,'Missing report; inspect phone-console.log'
            report['phone']=json.loads(outputs[0])
            assert report['phone']['passed'],'Phone parity check failed'
        finally:
            call(['xcrun','devicectl','device','install','app','--device',device,restore],log)
            call(['xcrun','devicectl','device','process','launch','--device',device,'--terminate-existing','app.veritas.heartecho'],log)
            report['normal_app_restored']=True
            save(ROOT/'results/murmur-baseline-phone.json',report)
    assert frozen['model_files']=={str(p.relative_to(model)):sha(p) for p in sorted(model.rglob('*')) if p.is_file()}
    print(json.dumps({'passed':report['phone']['passed'],'physical_device':report['phone']['physical_device'],'public_cases':len(report['phone']['cases']),'controls':len(report['phone']['controls']),'normal_app_restored':report['normal_app_restored']},indent=2))

if __name__=='__main__':main()
