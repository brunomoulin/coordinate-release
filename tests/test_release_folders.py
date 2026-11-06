"""Release folders: live state apart from history, the old one-file ledger still read, OUTCOME rows.
Run: python3 -m unittest discover tests"""
import io, os, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import checks as ck
import closeout
import ledger as lg
import status


def quiet(fn, *args, **kw):
    with redirect_stdout(io.StringIO()) as out:
        r = fn(*args, **kw)
    return r, out.getvalue()


def adapter(root):
    a = {'_main': root, 'release_dir': os.path.join(root, '.coordinate/releases'),
         'ledger_dir': os.path.join(root, '.coordinate/ledgers'), 'briefs_dir': os.path.join(root, '.coordinate/briefs'),
         'lessons_file': os.path.join(root, '.coordinate/lessons.md'), 'live_caps': dict(ad.DEFAULTS['live_caps'])}
    return a


def row(f, t, task, ev):
    with open(f, 'a') as fh:
        fh.write(f'| {t} | {task} | coordinator | {ev} |\n')


class Paths(unittest.TestCase):
    def test_new_release_gets_a_folder_old_one_keeps_its_file(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            self.assertEqual(ad.ledger_file(a, '2.12.0'), os.path.join(a['release_dir'], '2.12.0', 'timeline.md'))
            self.assertTrue(ad.in_folder(a, '2.12.0'))
            self.assertEqual(ad.briefs_path(a, '2.12.0'), os.path.join(a['release_dir'], '2.12.0', 'briefs'))
            quiet(lg.init, os.path.join(a['ledger_dir'], '2.11.0.md'), '2.11.0')
            self.assertEqual(ad.ledger_file(a, '2.11.0'), os.path.join(a['ledger_dir'], '2.11.0.md'))
            self.assertFalse(ad.in_folder(a, '2.11.0'))
            self.assertEqual(ad.briefs_path(a, '2.11.0'), os.path.join(a['briefs_dir'], '2.11.0'))
            self.assertEqual(ck.path(a, '2.11.0'), os.path.join(root, '.coordinate/eyeball/2.11.0.md'))

    def test_a_closed_ledger_moved_into_its_folder(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            quiet(lg.init, os.path.join(a['release_dir'], '2.10.0', 'ledger.md'), '2.10.0')
            self.assertEqual(ad.ledger_file(a, '2.10.0'), os.path.join(a['release_dir'], '2.10.0', 'ledger.md'))
            self.assertTrue(ad.in_folder(a, '2.10.0'))

    def test_newest_spans_both_layouts_and_skips_histories(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            old = os.path.join(a['ledger_dir'], '2.11.0.md')
            quiet(lg.init, old, '2.11.0')
            quiet(lg.init, os.path.join(a['release_dir'], '2.12.0'), '2.12.0')
            os.utime(old, (1, 1))
            self.assertEqual(ad.newest_ledger(a), '2.12.0')
            open(os.path.join(a['ledger_dir'], '2.11.0.history.md'), 'w').write('x')
            self.assertEqual(ad.newest_ledger(a), '2.12.0')


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.join(self.tmp.name, '2.12.0')
        quiet(lg.init, self.d, '2.12.0')
        self.f = lg.resolve(self.d)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        return open(os.path.join(self.d, name + '.md')).read()

    def test_init_writes_the_live_files(self):
        for name in ('now', 'decisions', 'timeline'):
            self.assertTrue(os.path.exists(os.path.join(self.d, name + '.md')), name)
        quiet(lg.add, self.f, '501', 'coordinator', 'PLANNED')
        self.assertEqual([r[1].strip() for r in lg.rows(self.f)], ['501'])

    def test_park_replaces_now_and_keeps_the_old_one(self):
        # pilot 2.11.0: 9 parks in one section, 18 KB, every resume read all of them.
        quiet(lg.park, self.f, 'Wave 1 merged.\n- Q: Push now?\n  Options: yes | no\n  Rec: no', 'wave 1')
        self.assertFalse(os.path.exists(os.path.join(self.d, 'history.md')), 'the placeholder is not history')
        quiet(lg.park, self.f, 'Wave 2 merged.', 'wave 2')
        self.assertIn('Wave 2 merged.', self.read('now'))
        self.assertNotIn('Wave 1', self.read('now'))
        self.assertIn('Wave 1 merged.', self.read('history'))
        self.assertEqual([e.strip() for *_, e in lg.rows(self.f)], ['PARKED wave 1', 'PARKED wave 2'])
        self.assertEqual(lg.questions(self.f), [])

    def test_questions_come_from_now(self):
        quiet(lg.park, self.f, '- Q: Ship 377 first?\n  Options: yes | no\n  Rec: yes (why)', 'q')
        self.assertEqual(lg.questions(self.f),
                         [{'question': 'Ship 377 first?', 'options': ['yes', 'no'], 'recommended': 'yes (why)'}])

    def test_a_decision_leaves_when_its_task_merges(self):
        quiet(lg.decide, self.f, 'Merge 494 as is', 'another round', 'one revert commit', task='494', by='owner')
        quiet(lg.decide, self.f, 'Hold the push for the close-out', 'push per wave', 'none')
        self.assertIn('alternatives: another round · revert: one revert commit', self.read('decisions'))
        quiet(lg.add, self.f, '494', 'coordinator', 'MERGED bugfix/494 into main @ abc')
        self.assertNotIn('494', self.read('decisions'))
        self.assertIn('Hold the push', self.read('decisions'))
        self.assertIn('Merge 494 as is', self.read('history'))

    def test_outcome_closes_the_loop(self):
        t = self.f
        row(t, '10-26 10:00', '501', 'ROUTE -> sonnet_implement posture=SURPLUS 7d=40 week=50 5h=20 devin_paid=0')
        row(t, '10-26 10:01', '501', 'LAUNCHED feat/501')
        row(t, '10-26 10:40', '501', 'GATES red lint')
        row(t, '10-26 10:50', 'review-501', 'DONE bugs=2')
        row(t, '10-26 11:00', '501', 'ROUTE -> devin_swe2 posture=TIGHT 5h=60')
        row(t, '10-26 11:01', '501', 'LAUNCHED r2')
        row(t, '10-26 11:31', 'rereview-501-r2', 'DONE bugs=1')
        row(t, '10-26 12:31', '501', 'MERGED feat/501 into main @ abc')
        ev = lg.outcome(t, '501', 72.4, agents_dir=os.path.join(os.path.dirname(t), 'no-mod'))
        self.assertEqual(ev, 'OUTCOME routes=sonnet_implement>devin_swe2 rounds=2 bugs=3 gate_reds=1 '
                             'wall=2h30 5h_at_route=20 5h_now=72 claude_tokens=? claude_usd=?')
        _, out = quiet(lg.outcomes, [t])
        head, line = out.splitlines()
        cols = dict(zip(head.split('\t'), line.split('\t')))
        self.assertEqual((cols['task'], cols['posture'], cols['rounds'], cols['5h_now']), ('501', 'SURPLUS', '2', '?'))


class OneFile(unittest.TestCase):
    def test_park_replaces_the_section_and_keeps_the_blurb(self):
        with tempfile.TemporaryDirectory() as root:
            f = os.path.join(root, '2.11.0.md')
            quiet(lg.init, f, '2.11.0')
            quiet(lg.park, f, 'first park', 'one')
            quiet(lg.park, f, 'second park', 'two')
            s = open(f).read()
            self.assertIn('(Written at each pause', s)
            self.assertIn('second park', s)
            self.assertNotIn('first park', s)
            self.assertIn('first park', open(os.path.join(root, '2.11.0.history.md')).read())
            self.assertEqual(len(lg.rows(f)), 2)
            quiet(lg.decide, f, 'Use SWE-2', 'Fusion', 'none')
            self.assertIn('Use SWE-2', lg.section(open(f).read(), 'Decisions'))


class Eyeball(unittest.TestCase):
    def test_a_passed_check_moves_out_and_ids_stay_unique(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            quiet(lg.init, os.path.join(a['release_dir'], '2.12.0'), '2.12.0')
            f = ck.path(a, '2.12.0')
            self.assertEqual(f, os.path.join(a['release_dir'], '2.12.0', 'eyeball.md'))
            ck.append(f, '- ADD 1 | 10-26 10:00 | 501 | vite 5176 | the login page')
            ck.append(f, '- ADD 2 | 10-26 10:01 | 502 | vite 5176 | the panel')
            ck.append(f, '- OK 1 | 10-26 10:30')
            ck.passed(f, {1})
            self.assertEqual(list(ck.load(f)), [2])
            self.assertIn('the login page', open(os.path.join(a['release_dir'], '2.12.0', 'history.md')).read())
            self.assertEqual(ck.next_id(f, ck.load(f)), 3)
            ck.passed(f, {2})
            self.assertEqual(ck.next_id(f, ck.load(f)), 3)


class Caps(unittest.TestCase):
    def test_live_files_past_their_cap(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            d = os.path.join(a['release_dir'], '2.12.0')
            quiet(lg.init, d, '2.12.0')
            self.assertEqual(status.over_caps(a, '2.12.0'), [])
            quiet(lg.park, lg.resolve(d), '\n'.join(f'line {i}' for i in range(80)), 'long')
            open(a['lessons_file'], 'w').write('x\n' * 100)
            out = status.over_caps(a, '2.12.0')
            self.assertEqual(len(out), 2)
            self.assertTrue(out[0].startswith('.coordinate/releases/2.12.0/now.md: 82 lines, cap 60'))

    def test_an_old_ledger_parked_section(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            f = os.path.join(a['ledger_dir'], '2.11.0.md')
            quiet(lg.init, f, '2.11.0')
            quiet(lg.park, f, '\n'.join(f'park {i}' for i in range(70)), 'long')
            self.assertIn('ledger.py park', status.over_caps(a, '2.11.0')[0])


class Closeout(unittest.TestCase):
    def test_report_goes_to_history_and_the_archive_holds_the_folder(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter(root)
            d = os.path.join(a['release_dir'], '2.12.0')
            quiet(lg.init, d, '2.12.0')
            f = lg.resolve(d)
            quiet(lg.decide, f, 'Keep SWE-2', 'Fusion', 'none')
            closeout.write_report(f, ['- first'])
            closeout.write_report(f, ['- second'])
            h = open(os.path.join(d, 'history.md')).read()
            self.assertEqual(h.count('## Close-out report'), 1)
            self.assertIn('- second', h)
            self.assertNotIn('Close-out', open(f).read())
            dst = os.path.join(root, 'docs', '2.12.0-ledger.md')
            closeout.archive(f, dst)
            s = open(dst).read()
            for part in ('Keep SWE-2', '- second', '## Timeline'):
                self.assertIn(part, s)
            row(f, '10-26 12:00', '501', 'MERGED x')
            p = closeout.index_line(a, f, '2.12.0')
            closeout.index_line(a, f, '2.12.0')
            self.assertEqual(open(p).read().count('- 2.12.0 ('), 1)
            self.assertIn('1 tasks merged', open(p).read())


if __name__ == '__main__':
    unittest.main()
