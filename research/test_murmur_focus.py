"""Protect comparisons from hiding uncertainty or counting visits as people."""
import json,unittest
from pathlib import Path
from murmur_focus_metrics import aggregate,counts,wilson

class MurmurMetricsTests(unittest.TestCase):
    def test_answered_accuracy_cannot_hide_abstentions(self):
        m=counts([1]*10+[0]*10,[1]+[2]*9+[0]+[2]*9)
        self.assertEqual(m['positive_detection_answered_only'],1)
        self.assertEqual(m['specificity_answered_only'],1)
        self.assertEqual(m['known_coverage'],.1)
        self.assertEqual(m['positive_detection_all'],.1)
        self.assertEqual(m['negative_clearance_all'],.1)

    def test_repeat_visits_are_one_person(self):
        rows=[dict(record='a',group='one',target=0,patient_target=1),dict(record='b',group='one',target=1,patient_target=1),dict(record='c',group='two',target=0,patient_target=0)]
        predictions={k:{'reading':{'finding':v}} for k,v in [('a','absent'),('b','present'),('c','unsure')]}
        m=aggregate(rows,predictions)
        self.assertEqual(m['recordings']['total'],3)
        self.assertEqual(m['linked_people']['total'],2)
        self.assertEqual(m['linked_people']['detected_positive'],1)
        self.assertEqual(m['linked_people']['negative_unsure'],1)

    def test_invalid_comparison_fails(self):
        with self.assertRaises(ValueError):counts([0,1],[0])
        with self.assertRaises(ValueError):counts([3],[0])

    def test_small_perfect_sample_has_wide_interval(self):
        lo,hi=wilson(10,10)
        self.assertAlmostEqual(lo,.7224672,places=6)
        self.assertAlmostEqual(hi,1)

    def test_linked_groups_never_cross_partitions(self):
        path=Path(__file__).resolve().parents[1]/'ChestBPM/ML/murmur-phase-manifest.json'
        groups={}
        for row in json.loads(path.read_text())['records']:
            group=row['group'];role=row['role']
            self.assertEqual(groups.setdefault(group,role),role)

if __name__=='__main__':unittest.main()
