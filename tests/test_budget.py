"""budget.py posture over synthetic signals. Run: python3 -m unittest discover tests"""
import os, sys, time, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import budget

A = {'budget': ad.DEFAULTS['budget']}


def signals(elapsed_pct, seven_pct, five_pct=None):
    return {'five_hour_pct': five_pct, 'five_hour_resets_at': None, 'seven_day_pct': seven_pct,
            'seven_day_resets_at': time.time() + (1 - elapsed_pct / 100) * budget.WEEK,
            'week_elapsed_pct': elapsed_pct, 'devin_paid': None, 'context_tokens': None}


class Posture(unittest.TestCase):
    def check(self, elapsed, seven, want, five=None):
        p, pace, _ = budget.posture(A, signals(elapsed, seven, five))
        self.assertEqual(p, want, f'elapsed {elapsed}%, 7d {seven}%: pace {pace}')

    def test_early_week_spend_is_not_overspending(self):
        # pilot 2.11.0: 7d 10% at 7% elapsed read pace 1.4, TIGHT.
        self.check(5, 10, 'SURPLUS')
        self.check(7, 10, 'SURPLUS')
        self.check(0, 10, 'SURPLUS')

    def test_early_week_burst_is_still_tight(self):
        self.check(5, 30, 'TIGHT')

    def test_past_the_floor_pace_is_unchanged(self):
        self.check(50, 50, 'ON PACE')
        self.check(50, 60, 'TIGHT')
        self.check(80, 30, 'SURPLUS')

    def test_critical_and_five_hour(self):
        self.check(95, 92, 'CRITICAL')

    def test_the_five_hour_window_never_sets_the_posture(self):
        # second pilot v1: 7d 11% at 25% elapsed (pace 0.44) still went TIGHT on a 71% 5h window.
        self.check(25, 11, 'SURPLUS', five=71)
        self.check(50, 50, 'ON PACE', five=75)
        self.check(50, 50, 'ON PACE', five=99)


class BuildFit(unittest.TestCase):
    def builds(self, elapsed, seven, five=None):
        s = signals(elapsed, seven, five)
        p, _, _ = budget.posture(A, s)
        with mock.patch.object(budget, '_load', return_value={}):
            return p, [x for x in budget.allowed(A, p, s)['build'] if x in budget.CLAUDE_BUILDS]

    def test_five_hour_gate_is_by_fit(self):
        # Trial fix 4: at 59% a Sonnet build (-> 69%) launches instead of waiting for the reset.
        self.assertEqual(self.builds(10, 5, five=59),
                         ('SURPLUS', ['haiku_implement', 'sonnet_implement', 'opus_implement']))
        # 66 + Opus 20 >= 85: Opus waits, Sonnet (76) and Haiku (69) go.
        self.assertEqual(self.builds(10, 5, five=66)[1], ['haiku_implement', 'sonnet_implement'])
        # 80% is still SURPLUS (the 5h window never sets the posture); only Haiku (83) fits.
        self.assertEqual(self.builds(10, 5, five=80), ('SURPLUS', ['haiku_implement']))

    def test_tight_allows_a_sonnet_build_that_fits_the_week(self):
        # pilot 2.11.0 wave 4: 7d 36% at 30.5% read TIGHT and refused the Sonnet build the owner judged fine.
        self.assertEqual(self.builds(30.5, 36), ('TIGHT', ['sonnet_implement']))
        self.assertEqual(self.builds(33.5, 45), ('TIGHT', ['sonnet_implement']))

    def test_tight_refuses_a_build_the_week_cannot_carry(self):
        self.assertEqual(self.builds(40, 70), ('TIGHT', []))

    def test_a_build_crossing_85_does_not_fit_whatever_the_posture(self):
        # ON PACE week, hot 5h window: the posture does not move, the fit check does the talking.
        self.assertEqual(self.builds(50, 50, five=72), ('ON PACE', ['sonnet_implement']))
        self.assertEqual(self.builds(50, 50, five=76), ('ON PACE', []))
        s = signals(25, 11, 71)  # the v1 case above, now SURPLUS
        p, _, _ = budget.posture(A, s)
        self.assertEqual(p, 'SURPLUS')
        self.assertIn('>= 85', budget.misfit(A, p, s, 'opus_implement'))  # 71 + 20: DOES NOT FIT
        self.assertIsNone(budget.misfit(A, p, s, 'sonnet_implement'))    # 81: fits

    def test_critical_allows_no_claude_build(self):
        self.assertEqual(self.builds(95, 92), ('CRITICAL', []))


class Spend(unittest.TestCase):
    """budget.spend: the last hour's 5h climb split by session, from the mod's sessions/<id>.json."""
    NOW = 1_700_000_000

    def setUp(self):
        import json, tempfile
        self.dir = tempfile.mkdtemp()
        self.json = json
        p = mock.patch.object(budget, 'SESSIONS', self.dir)
        p.start()
        self.addCleanup(p.stop)

    def write(self, sid, cwd, samples):
        with open(os.path.join(self.dir, f'{sid}.json'), 'w') as f:
            self.json.dump({'session': sid, 'cwd': cwd, 'samples': samples}, f)

    def sig(self, five):
        return {'five_hour_pct': five, 'five_hour_resets_at': self.NOW + 3 * 3600}

    def test_another_session_gets_its_share_of_the_climb(self):
        m = lambda n: self.NOW - n * 60
        # The coordinator spent $2 this hour; another session $6, from a baseline before the hour.
        self.write('me', '/w/app', [[m(50), 10, 40], [m(1), 12, 60]])
        self.write('s2', '/w/coordinate', [[m(70), 1, 38], [m(30), 4, 50], [m(2), 7, 59]])
        r = budget.spend(self.sig(60), me='me', now=self.NOW)
        self.assertEqual(r['climb'], 20)
        self.assertEqual(r['mine_usd'], 2)
        self.assertEqual(r['others'], [('coordinate', 6)])
        self.assertEqual(r['others_pct'], 15)
        self.assertIn('~15% by other sessions (coordinate $6.00)', r['line'])
        self.assertIn('~5% by this one ($2.00)', r['line'])

    def test_quiet_and_stale_sessions_say_nothing(self):
        self.write('me', '/w/app', [[self.NOW - 600, 1, 40], [self.NOW - 60, 3, 45]])
        self.write('old', '/w/x', [[self.NOW - 2 * 3600, 1, 30], [self.NOW - 90 * 60, 5, 35]])
        self.assertIsNone(budget.spend(self.sig(45), me='me', now=self.NOW))

    def test_a_file_a_day_old_is_removed(self):
        self.write('gone', '/w/x', [[self.NOW - 2 * 86400, 1, 30]])
        budget.spend(self.sig(45), me='me', now=self.NOW)
        self.assertEqual(os.listdir(self.dir), [])

    def test_the_climb_starts_at_the_window_reset(self):
        # The window reset 20 min ago: the 80% before it is the old window's.
        self.write('s2', '/w/c', [[self.NOW - 50 * 60, 0, 80], [self.NOW - 15 * 60, 1, 2], [self.NOW - 60, 3, 10]])
        r = budget.spend({'five_hour_pct': 10, 'five_hour_resets_at': self.NOW + 280 * 60}, me='me', now=self.NOW)
        self.assertEqual(r['climb'], 8)

    def test_no_five_hour_reading_gives_dollars_only(self):
        self.write('s2', '/w/c', [[self.NOW - 600, 1, None], [self.NOW - 60, 2.5, None]])
        r = budget.spend({'five_hour_pct': None, 'five_hour_resets_at': None}, me='me', now=self.NOW)
        self.assertIsNone(r['others_pct'])
        self.assertIn('other sessions $1.50 (c $1.50)', r['line'])


if __name__ == '__main__':
    unittest.main()
