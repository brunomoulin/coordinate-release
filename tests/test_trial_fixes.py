"""pilot 2.11.0 trial findings: Devin quota wording, the pace floor on sight, SWE-2 reviews. Run: python3 -m unittest discover tests"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import budget
import closeout


class DevinQuota(unittest.TestCase):
    def test_weekly_quota_exhausted_counts(self):
        # pilot 2.11.0: this line slipped past DEVIN_OUT and Fusion stayed allowed.
        self.assertTrue(budget.DEVIN_OUT.search('Error: your weekly usage quota has been exhausted.'))
        self.assertFalse(budget.DEVIN_OUT.search('quota: 40% used this week'))


class PaceFloor(unittest.TestCase):
    T = {'pace_floor_pct': 25}

    def test_floor_shown_when_it_applies(self):
        # "7d 11% at 7% of week (pace 0.44)" did not add up on sight.
        self.assertEqual(budget.week_text({'week_elapsed_pct': 7}, self.T), 'at 7% of week (floor 25%)')

    def test_no_floor_past_it(self):
        self.assertEqual(budget.week_text({'week_elapsed_pct': 40}, self.T), 'at 40% of week')
        self.assertEqual(budget.week_text({'week_elapsed_pct': None}, self.T), 'at unknown of week')


class Swe2Review(unittest.TestCase):
    def test_route_exists_and_is_inferred(self):
        self.assertIn('swe2_review', budget.ALL_ROUTES)
        self.assertEqual(budget.infer_route('devin-swe2', 'rereview-466'), 'swe2_review')
        self.assertEqual(budget.infer_route('devin', 'critique-470'), 'swe2_review')
        self.assertEqual(budget.infer_route('devin', '466'), 'devin_swe2')
        # closeout's overrule count per route: a SWE-2 review would read 'unmatched'.
        self.assertEqual(closeout.REVIEW_WHO['devin-swe2'], 'swe2_review')

    def test_free_so_every_posture(self):
        for p in budget.ROUTES:
            self.assertIn('swe2_review', budget.ROUTES[p]['review'], p)
            self.assertIn('swe2_review', budget.ROUTES[p]['critique'], p)


if __name__ == '__main__':
    unittest.main()
