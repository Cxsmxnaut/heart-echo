"""Repair only the task's isolated venv. No model/training dependency changes.
Pinned uv/pip wheels come from official PyPI URLs with checked SHA-256.
"""
import datetime, hashlib, io, json, os, shutil, subprocess, sys, urllib.request, venv, zipfile
from pathlib import Path

def ensure_environment(scratch, artifacts, pins, env=None, force_diagnostics=False):
    scratch, artifacts = Path(scratch), Path(artifacts)
    scratch.mkdir(parents=True, exist_ok=True); artifacts.mkdir(parents=True, exist_ok=True)
    target=scratch/'venv'; py=target/'bin/python'
    env={**(os.environ if env is None else env),'UV_PYTHON_DOWNLOADS':'never','UV_CACHE_DIR':str(scratch/'bootstrap/cache'),'UV_NO_PROGRESS':'1'}
    def probe(argv):
        try:
            r=subprocess.run([str(x) for x in argv],capture_output=True,text=True,env=env,timeout=180)
            return {'command':[str(x) for x in argv],'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        except (OSError, subprocess.SubprocessError) as e:
            return {'command':[str(x) for x in argv],'returncode':None,'stdout':'','stderr':repr(e)}
    def write_once(name, data):
        p=artifacts/name
        if not p.exists():p.write_text(json.dumps(data,indent=2)+'\n')
    def ok(row):return row['returncode']==0
    def checked(argv):
        row=probe(argv)
        write_once('bootstrap-command-'+hashlib.sha256(' '.join(row['command']).encode()).hexdigest()[:10]+'.json',row)
        if not ok(row):raise RuntimeError('Bootstrap command failed: '+row['stderr'][-4000:])
        return row
    # Preserve the currently available snapshot; an earlier overwritten archive cannot be recovered.
    for name in ['kaggle-failure.json','kaggle-status.json']:
        src=artifacts/name; dst=artifacts/('pre-repair-'+name)
        if src.exists() and not dst.exists():shutil.copy2(src,dst)
    source=Path('/kaggle/working/care-e4b-pilot-artifacts.zip')
    first=source.with_name('care-e4b-pre-repair-failure.zip')
    if source.exists() and not first.exists():shutil.copy2(source,first)
    if not py.exists():venv.EnvBuilder(with_pip=False).create(target)
    before=probe([py,'-m','pip','--version'])
    if ok(before) and not force_diagnostics:return py
    # This is a diagnostic retry; original CalledProcessError/archive stays preserved.
    ensurepip=probe([py,'-m','ensurepip','--upgrade','--default-pip'])
    after=probe([py,'-m','pip','--version'])
    diagnostic={'kernel_python':sys.version,'kernel_executable':sys.executable,'pip_before':before,'ensurepip_retry':ensurepip,'pip_after':after}
    write_once('ensurepip-repair-diagnostic.json',diagnostic)
    print('ensurepip diagnostic stdout:\n'+ensurepip['stdout'][-12000:],flush=True)
    print('ensurepip diagnostic stderr:\n'+ensurepip['stderr'][-12000:],flush=True)
    if ok(after):
        write_once('venv-bootstrap-result.json',{'method':'stdlib_ensurepip','pip':after,'training_packages_changed':False})
        return py
    assert not (artifacts/'kaggle-seed-001/training-complete.json').exists(),'Do not recreate a completed training environment'
    bootstrap=scratch/'bootstrap';bootstrap.mkdir(exist_ok=True)
    def wheel(key):
        pin=pins[key];url=pin['url']
        assert url.startswith('https://files.pythonhosted.org/')
        path=bootstrap/pin['filename']
        if not path.exists():
            with urllib.request.urlopen(url,timeout=120) as r, path.open('wb') as f:
                count=0
                for chunk in iter(lambda:r.read(2**20),b''):
                    count+=len(chunk);assert count<64*1024**2,'Bootstrap wheel unexpectedly large';f.write(chunk)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==pin['sha256'],key+' wheel checksum mismatch'
        return path
    uv_wheel=wheel('uv');pip_wheel=wheel('pip')
    uv=bootstrap/'uv'
    with zipfile.ZipFile(uv_wheel) as z:
        members=[n for n in z.namelist() if n.endswith('/uv') and not n.endswith('/')]
        assert len(members)==1,'Unexpected official uv wheel layout'
        uv.write_bytes(z.read(members[0]));uv.chmod(0o700)
    version=checked([uv,'--version'])
    assert version['stdout'].split()[:2]==['uv',pins['uv']['version']]
    backup=target.with_name('venv.before-uv-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    target.rename(backup)  # Keep the partial environment; never delete it.
    checked([uv,'--no-config','venv','--python',sys.executable,target])
    checked([uv,'--no-config','pip','install','--python',py,'--no-deps','--no-index',pip_wheel])
    final=checked([py,'-m','pip','--version'])
    assert ('pip '+pins['pip']['version']+' ') in final['stdout']
    write_once('venv-bootstrap-result.json',{'method':'verified_official_uv_and_local_pip_wheel','bootstrap_pins':pins,'partial_venv_preserved':str(backup),'pip':final,'training_packages_changed':False})
    print('Isolated venv repaired; training/model pins unchanged. Partial venv preserved; diagnostic logs saved.',flush=True)
    return py
