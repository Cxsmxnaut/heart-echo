#!/usr/bin/env python3
"""Verify origin files remain unchanged and compare every copied engine/model."""
import hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]; workspace=root.parent
manifest=json.loads((root/'PORTING.json').read_text())
adapted={'Engine/HeartRateMonitor.swift','Engine/LegacyDiagnosticsView.swift','Engine/WatchLink.swift','Watch/HeartEchoWatch.swift','Watch/Info.plist','Tools/collect_study.py','Tools/dashboard.py','Tools/dashboard.html','Tools/poll_diagnostics.py','Tools/watch_study.py','Tools/test_collector.py','UITests/HeartEchoDiagnosticsUITests.swift'}
failures=[]; exact=0; sources=0
for path,entry in manifest['origin_files'].items():
    source=workspace/entry['source']; current=root/path
    sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(source)!=entry['source_sha256']: failures.append('Origin changed: '+str(source))
    sources+=1
    if path not in adapted:
        if sha(current)!=entry['source_sha256']: failures.append('Copy changed: '+path)
        else: exact+=1
for name,origin in [('BeatStates','ML/Models'),('Murmur','ML/PhaseModels')]:
    source=workspace/'ChestBPM'/origin/(name+'.mlpackage');target=root/'Models'/(name+'.mlpackage')
    for p in source.rglob('*'):
        if p.is_file() and p.name!='.DS_Store':
            copy=target/p.relative_to(source)
            if not copy.exists() or p.read_bytes()!=copy.read_bytes(): failures.append('Model differs: '+str(copy))
print(f'{sources} origin hashes checked; {exact} exact copies; shipping model packages compared.')
for failure in failures: print('FAIL:',failure)
raise SystemExit(bool(failures))
