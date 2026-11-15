"""Fetch only the two named public datasets into ignored cache; preserve provenance."""
from pathlib import Path
import concurrent.futures, csv, hashlib, io, json, time, urllib.request, zipfile
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'cache'
CACHE.mkdir(exist_ok=True)
def fetch(url, target):
    target = Path(target)
    if target.exists(): return target.read_bytes()
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'HeartEcho-public-research/1.0'})
            data = urllib.request.urlopen(request, timeout=90).read()
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            return data
        except Exception:
            if attempt == 3: raise
            time.sleep(attempt + 1)
def gitsha(data): return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
def bmd():
    root = CACHE / 'bmd'; root.mkdir(exist_ok=True)
    commit = json.loads(fetch('https://api.github.com/repos/sani002/BMD-HS-Dataset/commits/main',root/'commit.json'))['sha']
    tree = json.loads(fetch(f'https://api.github.com/repos/sani002/BMD-HS-Dataset/git/trees/{commit}?recursive=1',root/'tree.json'))
    assert not tree.get('truncated')
    files = [x for x in tree['tree'] if x['type'] == 'blob' and (x['path'].startswith('train/') and x['path'].endswith('.wav') or x['path'] in ['train.csv','additional_metadata.csv','README.md','LICENSE'])]
    def download(entry):
        data = fetch(f"https://raw.githubusercontent.com/sani002/BMD-HS-Dataset/{commit}/{entry['path']}", root/entry['path'])
        assert gitsha(data) == entry['sha'], entry['path']
        return {'path':entry['path'], 'git_blob':entry['sha'], 'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data)}
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        results=[]
        for i, result in enumerate(pool.map(download,files)):
            results.append(result)
            if i % 100 == 0: print('BMD verified',i+1,'/',len(files),flush=True)
    (ROOT/'results/bmd-source.json').write_text(json.dumps({'repository':'https://github.com/sani002/BMD-HS-Dataset','commit':commit,'files':results},indent=2)+'\n')
def physio():
    root=CACHE/'physionet2016'; root.mkdir(exist_ok=True)
    url='https://physionet.org/files/challenge-2016/1.0.0/'
    archive=fetch(url+'training.zip', root/'training.zip')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for item in z.infolist():
            destination=(root/item.filename).resolve()
            assert destination.is_relative_to(root.resolve())
        z.extractall(root)
    records=[]
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.suffix.lower() in ['.wav','.csv','.hea']:
            records.append({'path':str(p.relative_to(root)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (ROOT/'results/physionet2016-source.json').write_text(json.dumps({'source':url+'training.zip','archive_sha256':hashlib.sha256(archive).hexdigest(),'files':records},indent=2)+'\n')
    print('PhysioNet verified local hashes:',len(records),flush=True)
if __name__=='__main__':
    import sys
    {'bmd':bmd,'physio':physio}[sys.argv[1]]()
