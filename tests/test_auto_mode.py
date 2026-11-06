"""Auto mode: picks (A<n>) and holds (W<n>) in decisions.md, listed atop now.md until the owner reviews
them. Run: python3 -m unittest discover tests"""
import io, os, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import ledger as lg


def quiet(fn, *args, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kw)


class AutoMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.join(self.tmp.name, '2.12.0')
        quiet(lg.init, self.d, '2.12.0')
        self.f = lg.resolve(self.d)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        return open(os.path.join(self.d, name + '.md')).read()

    def test_auto_on_survives_a_park(self):
        quiet(lg.set_auto, self.f, True)
        self.assertEqual(lg.auto_on(self.f)[0], True)
        self.assertIn('auto mode on', self.read('decisions'))
        quiet(lg.park, self.f, 'For you: nothing waits.\n', 'night park')
        now = self.read('now')
        self.assertIn('**Auto mode is on**', now)
        self.assertLess(now.index('Auto mode is on'), now.index('For you'))
        quiet(lg.set_auto, self.f, False)
        self.assertEqual(lg.auto_on(self.f)[0], False)
        self.assertNotIn('Auto mode is on', self.read('now'))

    def test_picks_and_holds_top_the_park(self):
        # pilot 2.11.0 night: 6 picks, 4 held; the owner could not find them in a 118 KB ledger.
        quiet(lg.set_auto, self.f, True)
        quiet(lg.decide, self.f, 'keep the r2 reader', 'revert to r1', 'one commit', task='468', auto=True)
        quiet(lg.decide, self.f, 'route 470 to SWE-2', 'Sonnet', 'none: not started', auto=True)
        quiet(lg.wait, self.f, '517 MFA: build now?', 'now | 2.12.1 | drop', '2.12.1 (feature-sized)', 'product', task='517')
        with self.assertRaises(SystemExit):
            quiet(lg.wait, self.f, 'q', 'a | b', 'a', 'whim')
        quiet(lg.park, self.f, 'For you: 2 picks, 1 hold.\n', 'night park')
        now = self.read('now')
        self.assertIn('## Decided for you (2)', now)
        self.assertIn('- A1 [468] keep the r2 reader · revert: one commit', now)
        self.assertIn('- A2 route 470 to SWE-2 · revert: none: not started', now)
        self.assertIn('## Waiting for you (1)', now)
        self.assertLess(now.index('Waiting for you'), now.index('For you'))
        qs = lg.questions(self.f)
        self.assertEqual(qs, [{'question': '[W1] [517] 517 MFA: build now? (held: product direction (a feature-sized choice))',
                               'options': ['now', '2.12.1', 'drop'], 'recommended': '2.12.1 (feature-sized)'}])

    def test_review_ok_override_answer(self):
        quiet(lg.decide, self.f, 'keep the r2 reader', 'revert to r1', 'one commit', task='468', auto=True)
        quiet(lg.decide, self.f, 'route 470 to SWE-2', 'Sonnet', 'none', auto=True)
        quiet(lg.wait, self.f, 'MFA now?', 'now | later', 'later (feature-sized)', 'product')
        # A merged task keeps an unreviewed pick in force until the owner sees it.
        quiet(lg.add, self.f, '468', 'coordinator', 'MERGED feat/468')
        self.assertIn('A1', self.read('decisions'))
        quiet(lg.review, self.f, 'A1', 'ok')
        self.assertNotIn('keep the r2 reader', self.read('decisions'))  # reviewed + merged: retired
        self.assertIn('keep the r2 reader', self.read('history'))
        quiet(lg.review, self.f, 'A2', 'override', 'route 470 to Sonnet', 'one relaunch')
        dec = self.read('decisions')
        self.assertNotIn('auto A2', dec)
        self.assertIn('· owner · route 470 to Sonnet · alternatives: A2: route 470 to SWE-2', dec)
        quiet(lg.review, self.f, 'W1', 'now', revert='a feature branch')
        dec = self.read('decisions')
        self.assertNotIn('waits W1', dec)
        self.assertIn('· owner · MFA now?: now · alternatives: later', dec)
        self.assertEqual(lg.items(self.f, unreviewed=True), [])
        self.assertNotIn('<!-- auto -->', self.read('now'))
        with self.assertRaises(SystemExit):
            quiet(lg.review, self.f, 'A1', 'ok')  # gone from decisions.md
        quiet(lg.decide, self.f, 'next pick', 'x', 'y', auto=True)
        self.assertIn('auto A3', self.read('decisions'))  # ids count history too

    def test_one_file_ledger_refuses_auto(self):
        f = os.path.join(self.tmp.name, '2.11.0.md')
        quiet(lg.init, f, '2.11.0')
        with self.assertRaises(SystemExit):
            quiet(lg.decide, f, 'x', 'y', 'z', auto=True)


if __name__ == '__main__':
    unittest.main()
