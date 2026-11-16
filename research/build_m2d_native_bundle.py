"""Bundle only allowlisted PUBLIC native training/selection audio for V12."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

import numpy as np

HERE=Path(__file__).resolve().parent


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1024*1024):h.update(block)
    return h.hexdigest()


def validate_rows(rows):
    groups={};names=set()
    for r in rows:
        if r['role'] not in ['training','selection']:
            raise ValueError('Calibration, test and private records are forbidden')
        if groups.setdefault(r['group'],r['role'])!=r['role']:
            raise ValueError('One linked person crosses partitions')
        if not re.fullmatch(r'[A-Za-z0-9_]+',r['record']) or r['record'] in names:
            raise ValueError('Invalid or duplicate public identifier')
        names.add(r['record'])
        p=Path(r['file'])
        if p.parts[0]!='training_data' or '..' in p.parts or p.suffix!='.wav':
            raise ValueError('Only public CirCor WAV provenance is allowed')


def build(output):
    os.umask(0o077)
    if output.exists():raise ValueError('Preserve existing bundles')
    ml=HERE.parent/'ChestBPM/ML';manifest=ml/'murmur-phase-manifest.json'
    rows=[r for r in json.loads(manifest.read_text())['records'] if r['role'] in ['training','selection']]
    validate_rows(rows)
    assert len(rows)==2536 and sum(r['role']=='training' for r in rows)==2356
    cache=ml/'generated/murmur-native-development'
    native=json.loads((cache/'manifest.json').read_text())
    assert native['phase_manifest_sha256']==sha(manifest)
    reader=HERE.parent/'HeartEcho/Engine/MurmurAnalysis.swift'
    assert native['native_reader_sha256']==sha(reader)
    by_id={r['record']:r for r in native['records']}
    output.mkdir(parents=True)
    records=[]
    temporary=output/'public-native.pending'
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        for i,r in enumerate(rows,1):
            item=by_id[r['record']]
            assert item['source_sha256']==r['sha256']
            audio=cache/'audio'/(r['record']+'.f32')
            assert sha(audio)==item['native_audio_sha256']
            wave=np.fromfile(audio,dtype='<f4')
            assert len(wave)==item['samples'] and np.isfinite(wave).all()
            name='audio/'+r['record']+'.f32'
            archive.write(audio,name)
            records.append(dict({k:r[k] for k in ['record','group','patient_target','target','role','file','sha256']},
                native_file=name,native_sha256=sha(audio),samples=len(wave)))
            if i%500==0:print(json.dumps(dict(public_records_bundled=i,total=len(rows))),flush=True)
        config=dict(public_only=True,private_audio_included=False,phone_profile_included=False,
            calibration_or_test_included=False,rate=2000,format='little-endian float32',records=records,
            phase_manifest_sha256=sha(manifest),native_manifest_sha256=sha(cache/'manifest.json'),
            native_reader_sha256=sha(reader),dataset='CirCor DigiScope1.0.3; ODC Attribution1.0')
        archive.writestr('public-config.json',json.dumps(config,separators=(',',':')))
    final=output/'public-native.zip';temporary.replace(final)
    with zipfile.ZipFile(final) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())=={'public-config.json'}|{r['native_file'] for r in records}
    shutil.copyfile(ml/'cache/circor/LICENSE.txt',output/'LICENSE.txt')
    (output/'README.md').write_text(
        '# Public CirCor audio through the unchanged Heart Echo reader\n\n'
        'Private research input. Only2,356training and180selection recordings. '
        'No personal recordings, private phone profile, calibration or test audio. '
        'Audio was converted to2kHz using the unchanged shipping AVAudioConverter reader.\n\n'
        'Source: Oliveira et al. (2022), The CirCor DigiScope Phonocardiogram Dataset1.0.3, '
        'PhysioNet, DOI10.13026/tshs-mw03. https://physionet.org/content/circor-heart-sound/1.0.3/\n\n'
        'License: Open Data Commons Attribution License v1.0. Original LICENSE.txt included. '
        'The other license category preserves that license; this is not a license change.\n')
    metadata=dict(title='Heart Echo Native Public V12',id='bhavithlolakapuri/heart-echo-native-public-v12',
        licenses=[{'name':'other'}],description=(output/'README.md').read_text())
    (output/'dataset-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    audit=dict(status='bundle_verified',records=len(records),training=2356,selection=180,
        private_audio_included=False,private_profile_included=False,calibration_or_test_included=False,
        zip_sha256=sha(final),zip_bytes=final.stat().st_size,
        public_config_sha256=hashlib.sha256(json.dumps(config,separators=(',',':')).encode()).hexdigest(),
        native_reader_sha256=sha(reader),source_sha256=sha(Path(__file__)))
    (output/'bundle-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    build(p.parse_args().output)
