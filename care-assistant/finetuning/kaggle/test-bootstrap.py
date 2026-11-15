import hashlib, importlib.util, io, json, subprocess, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('bootstrap_env',Path(__file__).with_name('bootstrap_env.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class BootstrapTests(unittest.TestCase):
 def exercise(self,healthy=False,bad_hash=False):
  with tempfile.TemporaryDirectory() as d:
   scratch=Path(d)/'scratch';art=Path(d)/'art';old=scratch/'venv/bin';old.mkdir(parents=True);(old/'python').write_text('partial');art.mkdir()
   installed=healthy;commands=[];downloads=[]
   archive=io.BytesIO()
   with zipfile.ZipFile(archive,'w') as z:z.writestr('uv/uv',b'not-executed-test-double')
   data={'https://files.pythonhosted.org/uv.whl':archive.getvalue(),'https://files.pythonhosted.org/pip.whl':b'pinned-pip-double'}
   pins={k:{'version':v,'filename':k+'.whl','url':'https://files.pythonhosted.org/'+k+'.whl','sha256':hashlib.sha256(data['https://files.pythonhosted.org/'+k+'.whl']).hexdigest()} for k,v in [('uv','0.13.8'),('pip','26.3')]}
   if bad_hash:pins['uv']['sha256']='0'*64
   def run(argv,**kw):
    nonlocal installed
    commands.append(argv)
    if '-m' in argv and 'pip' in argv:return subprocess.CompletedProcess(argv,0 if installed else 1,'pip 26.3 from isolated-venv' if installed else '', '' if installed else 'missing pip marker')
    if 'ensurepip' in argv:return subprocess.CompletedProcess(argv,1,'ensurepip stdout marker','ensurepip stderr marker')
    if '--version' in argv:return subprocess.CompletedProcess(argv,0,'uv 0.13.8 (test)','')
    if 'venv' in argv:
     p=Path(argv[-1])/'bin';p.mkdir(parents=True);(p/'python').write_text('repaired')
    if 'install' in argv:installed=True
    return subprocess.CompletedProcess(argv,0,'','')
   def urlopen(url,**kw):downloads.append(url);return io.BytesIO(data[url])
   with patch.object(m.subprocess,'run',run),patch.object(m.urllib.request,'urlopen',urlopen):
    if bad_hash:
     with self.assertRaisesRegex(AssertionError,'checksum mismatch'):m.ensure_environment(scratch,art,pins)
     self.assertTrue((old/'python').exists());self.assertFalse(any(Path(c[0]).name=='uv' for c in commands));return
    py=m.ensure_environment(scratch,art,pins)
   self.assertTrue(py.exists())
   if healthy:self.assertEqual(len(commands),1);self.assertEqual(downloads,[])
   else:
    diag=json.loads((art/'ensurepip-repair-diagnostic.json').read_text());self.assertEqual(diag['ensurepip_retry']['stderr'],'ensurepip stderr marker')
    backups=list(scratch.glob('venv.before-uv-*'));self.assertEqual(len(backups),1);self.assertEqual((backups[0]/'bin/python').read_text(),'partial')
    self.assertEqual(len(downloads),2);self.assertTrue(installed)
 def test_healthy_pip_needs_no_repair(self):self.exercise(healthy=True)
 def test_existing_python_without_pip_is_repaired_and_preserved(self):self.exercise()
 def test_wrong_wheel_hash_stops_before_execution(self):self.exercise(bad_hash=True)
if __name__=='__main__':unittest.main()
