"""Machine eyeball: the verify brief, an agent report's verdicts as check states, the owner's bulk
confirm, the eyeball routes. Run: python3 -m unittest discover tests"""
import io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import budget
import checks as ck
import eyeball
import ledger as lg

# The shape of a real 2.11.0 Devin report (checks #7-#18), cut down.
REPORT = """# 2.11.0 eyeball - Devin report

## #7 PASS
Live event "Eyeball Live A". Search "Doe": row shows Jane Doe (07-1).

## #14 NEEDS OWNER
No DECLINED rows exist in dev; cannot exercise it without a fixture.
> OWNER: accept the behaviour as is.

## #15 PASS (incident-link door unexercised)
Dirty form: "Discard this edit?" (15-1).

## #16 PARTIAL
No discard prompt where nothing had changed (16-1).

## Records created or changed on dev
- Events Eyeball Live A and B.
"""


def quiet(fn, *args, **kw):
    with redirect_stdout(io.StringIO()) as out:
        r = fn(*args, **kw)
    return r, out.getvalue()


class MachineEyeball(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, 'app')
        os.makedirs(os.path.join(self.root, '.claude'))
        subprocess.run(['git', 'init', '-q', '-b', 'main', self.root], check=True)
        json.dump({'eyeball_verify': {'url': 'http://localhost:5174/app', 'accounts_file': '~/dev-logins.txt',
                                      'rules': ['Never run `./dev-restart.sh`.']}},
                  open(os.path.join(self.root, '.claude', 'coordinate.json'), 'w'))
        quiet(lg.init, os.path.join(self.root, '.coordinate/releases/2.12.0'), '2.12.0')
        for i, what in ((7, 'preferred name everywhere'), (14, 'declined row'), (15, 'discard prompt'),
                        (16, 'no prompt when unchanged'), (17, 'held SA tag')):
            quiet(ck.run, ['add', self.root, '--release', '2.12.0', '--task', str(400 + i), '--where', '5174', what])
        self.f = os.path.join(self.root, '.coordinate/releases/2.12.0/eyeball.md')
        # ids 1-5 in the file; the report numbers them as app did, so map 7,14,15,16 -> 1,2,3,4.
        self.report = os.path.join(self.tmp.name, 'report.md')
        text = REPORT
        for old, new in (('#7 ', '#1 '), ('#14 ', '#2 '), ('#15 ', '#3 '), ('#16 ', '#4 ')):
            text = text.replace('## ' + old, '## ' + new)
        open(self.report, 'w').write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_headings_are_states(self):
        v = ck.verdicts(self.report)
        self.assertEqual({i: s for i, (s, _) in v.items()},
                         {1: 'agent-pass', 2: 'needs-human', 3: 'agent-pass', 4: 'agent-flag'})
        self.assertEqual(v[3][1], 'incident-link door unexercised')  # the heading's caveat is the note
        self.assertTrue(v[2][1].startswith('No DECLINED rows'))  # not the owner's > OWNER: line

    def test_import_never_closes_a_check(self):
        _, out = quiet(ck.run, ['import', self.root, '--release', '2.12.0', self.report])
        self.assertIn('no verdict in the report for: #5', out)
        cs = ck.load(self.f)
        self.assertEqual([c['state'] for c in cs.values()], ['agent-pass', 'needs-human', 'agent-pass', 'agent-flag', 'open'])
        self.assertEqual(ck.waiting_line(self.f, cs),
                         f'waiting on you: 1 open, 2 agent-pass, 1 agent-flag, 1 needs-human · {self.f}')
        # The owner read the report: one bulk confirm closes the agent-pass checks, nothing else.
        quiet(ck.run, ['ok', self.root, '--release', '2.12.0', '--agent-pass'])
        cs = ck.load(self.f)
        self.assertEqual(sorted(cs), [2, 4, 5])
        self.assertIn('agent-pass confirmed', open(os.path.join(os.path.dirname(self.f), 'history.md')).read())

    def test_waiting_splits_owner_from_the_fix_round(self):
        # Every waiting state lands in "waiting on you"; feedback is the coordinator's fix round.
        cs = ck.load(self.f)
        self.assertEqual(ck.waiting_line(self.f, cs), f'waiting on you: 5 open · {self.f}')
        quiet(ck.run, ['feedback', self.root, '--release', '2.12.0', '4', 'the prompt shows on a clean form'])
        self.assertEqual(ck.waiting_line(self.f, ck.load(self.f)),
                         f'waiting on you: 4 open · in a fix round: 1 (416) · {self.f}')
        # The fix landed: `checks fixed` moves it to recheck, waiting on the owner again.
        quiet(ck.run, ['fixed', self.root, '--release', '2.12.0', '4', 'prompt added on blur'])
        cs = ck.load(self.f)
        self.assertEqual(cs[4]['state'], 'recheck')
        self.assertEqual(ck.waiting_line(self.f, cs), f'waiting on you: 4 open, 1 recheck · {self.f}')
        # `checks ok` accepts a recheck, and the file goes quiet.
        quiet(ck.run, ['ok', self.root, '--release', '2.12.0', '4'])
        self.assertNotIn(4, ck.load(self.f))
        self.assertEqual(ck.waiting_line(self.f, ck.load(self.f)), f'waiting on you: 4 open · {self.f}')

    def test_waiting_takes_answers_written_in_the_file(self):
        # The owner answered in eyeball.md, not the chat: the next report sees it and tidies the OK.
        with open(self.f, 'a') as fh:
            fh.write('- OK 1 | 11-10 19:12 | looks right\n- FEEDBACK 2 | 11-10 19:13 | wrong colour\n')
        out = io.StringIO()
        with redirect_stdout(out):
            ck.run(['waiting', self.root, '--release', '2.12.0'])
        self.assertIn('#1 ok in the file, moved to history', out.getvalue())
        self.assertIn('in a fix round: 1', out.getvalue())
        self.assertNotIn(1, ck.load(self.f))
        self.assertIn('looks right', open(os.path.join(os.path.dirname(self.f), 'history.md')).read())

    def test_verify_brief(self):
        quiet(ck.run, ['import', self.root, '--release', '2.12.0', self.report])
        quiet(ck.run, ['feedback', self.root, '--release', '2.12.0', '4', 'the prompt shows on a clean form'])
        brief, out = quiet(eyeball.verify, [self.root, '--release', '2.12.0'])
        text = open(brief).read()
        self.assertNotIn('{{', text)
        self.assertNotIn('<!--', text)
        self.assertIn('**#5** (417, at 5174): held SA tag', text)  # the only open check without a verdict
        self.assertNotIn('**#1**', text)
        self.assertIn('9. Never run `./dev-restart.sh`.', text)
        self.assertIn('`~/dev-logins.txt`', text)
        self.assertIn('eyeball-report-1.md', text)
        self.assertIn('devin_eyeball', out)
        brief2, _ = quiet(eyeball.verify, [self.root, '--release', '2.12.0', '4'])  # re-verify a fix round
        self.assertTrue(brief2.endswith('eyeball-verify-2.md'))
        self.assertIn('the prompt shows on a clean form', open(brief2).read())


class Routes(unittest.TestCase):
    def test_eyeball_routes(self):
        self.assertEqual(budget.infer_route('devin-swe2', 'eyeball-verify-1'), 'devin_eyeball')
        self.assertEqual(budget.infer_route('sonnet', 'eyeball-verify-2'), 'sonnet_eyeball')
        self.assertIn('sonnet_eyeball', budget.ROUTES['SURPLUS']['eyeball'])
        for p in ('ON PACE', 'TIGHT', 'CRITICAL'):
            self.assertEqual(budget.ROUTES[p]['eyeball'], ['devin_eyeball'], p)


if __name__ == '__main__':
    unittest.main()
