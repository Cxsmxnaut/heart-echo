"""Audit the full murmur objective against current files and native outputs.

Never infer clinical reliability from engineering checks or reused data.
"""
import json
from train_audio_models import ROOT,ML,digest,save
from murmur_focus_metrics import aggregate,wilson

def main():
    read=lambda p:json.loads(p.read_text())
    decision=read(ROOT/'results/murmur-focus-decision.json')
    freeze=read(ROOT/'results/murmur-focus-baseline-freeze.json')
    package=ROOT.parent/'HeartEcho/Models/Murmur.mlpackage'
    assert freeze['model_files']=={str(p.relative_to(package)):digest(p) for p in sorted(package.rglob('*')) if p.is_file()}
    assert freeze['native_reader_sha256']==digest(ROOT.parent/'HeartEcho/Engine/MurmurAnalysis.swift')
    assert decision['baseline_weights_sha256']==digest(ML/'generated/murmur-phase-m/Murmur.pt')
    v5=read(ROOT/'generated/murmur-v5-sampler/complete.json')
    assert v5['weights_sha256']==digest(ROOT/'generated/murmur-v5-sampler/best.pt')
    assert v5['protocol']['source_sha256']==digest(ROOT/'train_murmur_v5_sampler.py')
    assert v5['protocol']['architecture_source_sha256']==digest(ROOT/'train_phase_texture.py')
    comparison=read(ROOT/'results/murmur-v5-native-development.json')
    rows=[r for r in read(ML/'murmur-phase-manifest.json')['records'] if r['role'] in ['selection','calibration']]
    baseline=read(ROOT/'generated/murmur-focus-diagnosis/baseline-native-development.json')
    candidate=read(ROOT/'generated/murmur-v5-sampler/native-development.json')
    for role in ['selection','calibration']:
        cohort=[r for r in rows if r['role']==role]
        for name,predictions in [('baseline',baseline),('candidate',candidate)]:
            actual=aggregate(cohort,predictions)
            for level in ['recordings','linked_people']:
                assert actual[level]['matrix']==comparison['roles'][role][name][level]['matrix']
    summary=aggregate(rows,baseline)
    ambitions=read(ROOT/'murmur_focus_acceptance.json')['reliability']['ambition_only_not_clinical_standard']
    keymap={'answered_sensitivity':'positive_detection_answered_only','answered_specificity':'specificity_answered_only','coverage_of_independently_assessed_usable_recordings':'known_coverage','all_positive_detection_including_unsure_denominator':'positive_detection_all','all_negative_clearance_including_unsure_denominator':'negative_clearance_all'}
    checks={}
    for level in ['recordings','linked_people']:
        m=summary[level]
        checks[level]={key:{'observed_on_reused_development':m[keymap[key]],'ambition_not_clinical_standard':target,'point_estimate_meets_ambition':m[keymap[key]] is not None and m[keymap[key]]>=target} for key,target in ambitions.items()}
        m['positive_detection_wilson95_descriptive']=wilson(m['detected_positive'],m['positive_count'])
        m['negative_clearance_wilson95_descriptive']=wilson(m['correct_absent'],m['negative_count'])
    phonepath=ROOT/'results/murmur-baseline-phone.json';phone=read(phonepath) if phonepath.exists() else {}
    phonepassed=phone.get('phone',{}).get('passed',False) and phone.get('phone',{}).get('physical_device',False) and phone.get('normal_app_restored',False)
    report={'requirements':{'baseline_preserved':True,'v4_false_alarms_investigated':(ROOT/'results/murmur-v4-diagnosis.json').exists(),'controlled_v5_training_completed_and_frozen':True,'recording_and_person_comparisons_recomputed':True,'unsupported_replacement_rejected':comparison['decision']=='retain_baseline_reject_v5' and not comparison['development_gate_passed'],'documented_model_choice':(ROOT/'murmur-model-decision.md').exists(),'coreml_conversion_parity_on_mac':all(v['passed'] for v in decision['conversion'].values()),'physical_phone_public_sample_parity':bool(phonepassed),'representative_independent_clinician_labeled_phone_validation':False,'high_reliability_goal_proven':False},'baseline_reused_development':summary,'ambition_comparisons':checks,'independent_phone_validation_records_verified':0,'limitations':['All measured accuracy here is reused development evidence, not a generalization estimate.','Known coverage is shown for all known-label development cases; independently assessed usable-audio coverage is unavailable. Do not treat the two denominators as equivalent.','Recording confidence intervals ignore within-person correlation. Person intervals treat linked groups as independent; neither corrects development-selection bias.','Phone parity uses bundled public stethoscope audio. It proves execution agreement on those inputs, not phone-microphone capture accuracy.'],'evidence_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'results/murmur-focus-decision.json',ROOT/'results/murmur-v4-diagnosis.json',ROOT/'results/murmur-v5-native-development.json',ROOT/'phone-evidence-review.md',ROOT/'murmur_focus_acceptance.json',*([phonepath] if phonepath.exists() else [])]},'completion':'NOT ACHIEVED: model choice and engineering checks do not establish the requested high reliability.'}
    for version,label in [('v6','pretrained'),('v7','heartband')]:
        v6path=ROOT/'results'/('murmur-'+version+'-'+label+'-probe.json')
        if not v6path.exists():continue
        v6dir=ROOT/'generated'/('murmur-'+version+'-'+label+'-probe');probe=read(v6path)
        frozen=read(v6dir/'classifier-freeze.json')
        fitter=ROOT/('fit_panns_murmur_probe.py' if version=='v6' else 'fit_panns_heartband_probe.py')
        assert frozen['source_sha256']==digest(fitter)
        assert frozen['metrics_sha256']==digest(ROOT/'murmur_focus_metrics.py')
        assert frozen['protocol_sha256']==digest(v6dir/'protocol.json')
        for name,value in frozen['classifiers'].items():
            assert digest(v6dir/(name+'-classifier.npz'))==value
            predictions=read(v6dir/(name+'-development.json'))
            for role in ['selection','calibration']:
                actual=aggregate([r for r in rows if r['role']==role],predictions)
                for level in ['recordings','linked_people']:
                    assert actual[level]['matrix']==probe['roles'][role][name]['metrics'][level]['matrix']
        report['requirements'][version+'_controlled_probe_frozen_and_rejected']=not any(probe['development_gate'].values()) and probe['decision']=='retain_baseline_reject_frozen_pretrained_probe'
        report['evidence_sha256'][str(v6path.relative_to(ROOT))]=digest(v6path)
        report['evidence_sha256'][str((v6dir/'classifier-freeze.json').relative_to(ROOT))]=digest(v6dir/'classifier-freeze.json')
    v8path=ROOT/'results/murmur-v8-native-development.json'
    if v8path.exists():
        v8dir=ROOT/'generated/murmur-v8-distillation';v8=read(v8path)
        frozen=read(v8dir/'evaluation-freeze.json');complete=read(v8dir/'complete.json')
        assert frozen['candidate_weights_sha256']==digest(v8dir/'best.pt')==complete['weights_sha256']
        assert complete['protocol']['source_sha256']==digest(ROOT/'train_murmur_v8_distillation.py')
        assert complete['protocol']['teacher_weights_sha256']==digest(ML/'generated/murmur-phase-m/Murmur.pt')
        assert frozen['evaluator_sha256']==digest(ROOT/'evaluate_murmur_v8.py')
        assert frozen['metrics_sha256']==digest(ROOT/'murmur_focus_metrics.py')
        predictions=read(v8dir/'native-development.json')
        for role in ['selection','calibration']:
            actual=aggregate([r for r in rows if r['role']==role],predictions)
            for level in ['recordings','linked_people']:assert actual[level]['matrix']==v8['roles'][role]['candidate'][level]['matrix']
        report['requirements']['v8_controlled_run_frozen_converted_and_rejected']=v8['decision']=='retain_baseline_reject_v8' and not v8['development_gate_passed'] and v8['conversion']['candidate']['passed'] and not v8['regression_scored']
        report['evidence_sha256'][str(v8path.relative_to(ROOT))]=digest(v8path)
    save(ROOT/'results/murmur-reliability-audit.json',report)
    print(json.dumps(report['requirements'],indent=2))

if __name__=='__main__':main()
