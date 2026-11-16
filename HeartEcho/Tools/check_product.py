#!/usr/bin/env python3
"""Run reproducible native product/engine checks without reading personal captures."""
from pathlib import Path
import subprocess,tempfile,json,time
ROOT=Path(__file__).resolve().parents[1]

def main():
    began=time.time();results=[]
    with tempfile.TemporaryDirectory(prefix='heartecho-checks-') as directory:
        out=Path(directory);cache=out/'modules'
        common=['Engine/MurmurAnalysis.swift','HeartEchoApp/AudioAssessment.swift','HeartEchoApp/HeartRecording.swift']
        checks=[
            ('bpm',['Engine/HeartRateEstimator.swift','Engine/NoiseAnalysis.swift','Engine/NeuralSignal.swift','Engine/WatchLink.swift','Engine/TrialProtocol.swift','Engine/DiagnosticLog.swift','Tests/main.swift'],[]),
            ('murmur',['Engine/MurmurAnalysis.swift','Tools/MurmurChecks.swift'],['Models']),
            ('records',common+['Engine/CaptureArtifact.swift','Tests/RecordChecks.swift'],[]),
            ('storage',common+['HeartEchoApp/RecordingFiles.swift','Tests/StorageChecks.swift'],[]),
            ('care',common+['HeartEchoApp/NativeCareDirectory.swift','HeartEchoApp/CareService.swift','Tests/CareChecks.swift'],[]),
            ('guidance',['HeartEchoApp/RecordingGuidance.swift','Tests/RecordingGuidanceChecks.swift'],[]),
            ('care-intent',['HeartEchoApp/CareSearchIntent.swift','Tests/CareSearchIntentChecks.swift'],[]),
        ]
        for name,files,args in checks:
            binary=out/name
            subprocess.run(['swiftc','-O','-module-cache-path',str(cache),*files,'-o',str(binary)],cwd=ROOT,check=True)
            result=subprocess.run([str(binary),*args],cwd=ROOT,capture_output=True,text=True)
            count=sum(line.startswith('PASS:') for line in result.stdout.splitlines())
            results.append({'check':name,'exit_code':result.returncode,'passed_assertions':count,'output':result.stdout})
            print(name,result.returncode,count,flush=True)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        for name,args in [('collector',['python3','-m','unittest','discover','-s','Tools','-p','test_*.py']),('origin',['python3','Tools/verify_port.py'])]:
            result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);results.append({'check':name,'exit_code':result.returncode,'output':result.stdout+result.stderr});print(name,result.returncode,flush=True)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    report={'scope':'Engineering checks; no clinical/phone accuracy validation and no personal captures.','elapsed_seconds':time.time()-began,'results':results}
    (ROOT/'Docs/product-checks-final.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
