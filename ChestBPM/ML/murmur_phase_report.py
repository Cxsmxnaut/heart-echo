"""Publish aggregate phase-aware murmur evidence without private or per-person audio."""
import collections
import json
from pathlib import Path
from murmur_data import ROOT,digest,save
from murmur_model import metrics
from murmur_phase_data import PHASE_MANIFEST


def main():
    folder=ROOT/'results/murmur-phase-m'
    accepted=json.loads((folder/'acceptance-with-regression.json').read_text());assert accepted['eligible']
    generated=ROOT/'generated/murmur-phase-m/Murmur.mlpackage';bundled=ROOT/'PhaseModels/Murmur.mlpackage'
    package_hashes={str(p.relative_to(generated)):digest(p) for p in generated.rglob('*') if p.is_file()}
    assert package_hashes=={str(p.relative_to(bundled)):digest(p) for p in bundled.rglob('*') if p.is_file()},'Bundled model differs from evaluated package'
    roles={}
    for role in ['selection','calibration','test']:
        summary=json.loads((folder/(role+'-summary.json')).read_text());rows=json.loads((folder/(role+'-predictions.json')).read_text());groups=collections.defaultdict(list)
        for r in rows:groups[r['group']].append(r)
        truth=[1 if any(r['patient_target']==1 for r in v) else 2 if any(r['patient_target']==2 for r in v) else 0 for v in groups.values()]
        grouped={}
        for name in ['baseline','candidate']:
            predictions=[1 if any(r[name]=='present' for r in v) else 2 if any(r[name]=='unsure' for r in v) else 0 for v in groups.values()]
            grouped[name]=metrics(truth,predictions)
        assert len(groups)==(120 if role=='test' else 50)
        roles[role]=dict(**accepted['results'][role],linked_people_any_visit=grouped,
            linked_people_count=len(groups),patient_visit_entries=summary['patients'],
            patient_unit_note='baseline_patient/candidate_patient count source patient/visit IDs, which can include linked repeat visits. linked_people_any_visit collapses AdditionalID links: any Present truth/prediction wins, else Unknown/Unsure, else Absent. This across-visit analysis is descriptive, not prospective clinical diagnosis.',
            paired_record_difference_intervals=json.loads((folder/(role+'-paired-comparison.json')).read_text())['differences'],known_noise_controls=summary['known_negative_controls'])
    manifest=json.loads(PHASE_MANIFEST.read_text());split={}
    for role in ['training','selection','calibration','test']:
        rows=[r for r in manifest['records'] if r['role']==role];split[role]=dict(linked_people=len({r['group'] for r in rows}),patient_visit_entries=len({r['patient'] for r in rows}),recordings=len(rows))
    samples=[dict(sample=r['id'],finding=r['reading']['finding'],probabilities=r['reading']['probabilities']) for r in map(json.loads,(folder/'public-samples.ndjson').open())]
    report=dict(model='M: phase-aware positive-evidence addition',schema='chestbpm-murmur-wave-2k-v1',labels=['Absent','Present','Unknown/Unsure'],
        source='CirCor1.0.3,ODCAttribution1.0,https://doi.org/10.13026/tshs-mw03',split=split,
        weights_sha256=digest(ROOT/'generated/murmur-phase-m/Murmur.pt'),package_manifest_sha256=digest(ROOT/'PhaseModels/Murmur.mlpackage/Manifest.json'),
        model_freeze_sha256=digest(ROOT/'murmur-phase-m-freeze.json'),package_files_sha256=package_hashes,preserved_v1_report_sha256=digest(ROOT/'murmur-report.json'),report_generator_sha256=digest(Path(__file__)),
        accepted=accepted['eligible'],roles=roles,conversion=json.loads((ROOT/'generated/murmur-phase-m/conversion.json').read_text()),public_samples=samples,
        limitations=['All100development groups were reused during research, including architecture/calibration choices.','Original120test groups were inspected in v1; v2test is retrospective regression, not fresh independent validation.','Public stethoscope results do not establish bare-phone or clinical accuracy. No new personal recordings, private audio or Watch inputs were used.','ExpertUnknown labels are uncertain, not known healthy/noise. All uncertain/invalid inputs remain in evaluation denominators.','Phase accuracy concerns only annotated frames in one first4secondwindow per recording; unannotated spans are excluded and coverage is reported. Phase labels are semi-supervised.','Weak murmur timing supervision approximates early/mid/late/holo timing; it is not dense clinical murmur truth.','Paired linked-group bootstrap3000percentile intervals are exploratory and do not correct for research/model selection.','Twenty nonheart controls reuse known synthetic/speech sources; they are not unseen-noise validation.','Bundled NoMurmurAnnotated demo now returnsUnsure; fixed samples were not replaced to improve the demonstration.','No AFib, valve-disease or disease-probability output is implemented.'])
    save(ROOT/'murmur-phase-report.json',report)
    for role,v in roles.items():print(role,'unique linked-person analysis',v['linked_people_any_visit'])
    print('Published ML/murmur-phase-report.json aggregate evidence.')


if __name__=='__main__':main()
