"""v1 lessons: review routes that read 'unmatched', and overrules inflated by confirmations and repeats.
Run: python3 -m unittest discover tests"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import closeout
import findings as fd
import ledger as lg


class Classify(unittest.TestCase):
    def test_confirmations_are_not_overrules(self):
        for d in ('No change: checked, holds', 'No change: verification note (cap change clean)',
                  'No change: the row confirms parity and copy; wording is T18\'s',
                  'No change: result correct'):
            self.assertEqual(fd.classify(d), 'noted', d)

    def test_real_declines_stay_overrules(self):
        for d in ('No change: by design', 'Not doing: harmless second guard',
                  'No change: a collab card that lists the channel is one the user asked to see'):
            self.assertEqual(fd.classify(d), 'overruled', d)


TABLE = ('| # | Severity | File:line | Finding | Fix | Disposition |\n|---|---|---|---|---|---|\n'
         '| 1 | Bug | a.ts:1 | x | z | No change: row 6 goes in r3 |\n'
         '| 2 | Bug | a.ts:2 | y | z | No change: row 6 goes in r3 |\n'
         '| 3 | Bug | a.ts:3 | w | z | No change: checked, holds |\n'
         '| 4 | Bug | a.ts:4 | v | z | Fixed |\n')


class Overrules(unittest.TestCase):
    def test_repeats_and_confirmations_leave_the_count(self):
        with tempfile.TemporaryDirectory() as d:
            brief = os.path.join(d, 'briefs')
            os.makedirs(brief)
            open(os.path.join(brief, 'v1-T1-rereview.md'), 'w').write(TABLE)
            lf = os.path.join(d, 'timeline.md')
            a = {'_briefs': brief}
            from unittest import mock
            with mock.patch.object(closeout.ad, 'briefs_path', return_value=brief), \
                    mock.patch.object(closeout, 'review_route', return_value='sonnet_review'):
                s = closeout.overrules(a, lf, 'v1')['sonnet_review']
            self.assertEqual((s['overruled'], s['noted'], s['repeat'], s['fixed']), (1, 1, 1, 1))

    def test_line_leaves_noted_and_repeats_out_of_the_percentage(self):
        import collections
        s = collections.Counter(overruled=1, noted=1, repeat=1, fixed=1)
        line = closeout.overrule_lines({'sonnet_review': s})[0]
        self.assertIn('1 of 2 disposed (50%)', line)
        self.assertIn('noted 1', line)
        self.assertIn('repeat 1', line)


class RouteNames(unittest.TestCase):
    def ledger(self, d, rows):
        lf = os.path.join(d, 'timeline.md')
        open(lf, 'w').write('| When | Task | Who | Event |\n|---|---|---|---|\n' + ''.join(
            f'| 11-02 20:0{i} | {t} | {w} | {e} |\n' for i, (t, w, e) in enumerate(rows)))
        return lf

    def test_ledger_task_without_a_hyphen_before_the_round(self):
        # v1: rows say review-T64r3, the file is v1-T64-r3-rereview.md
        with tempfile.TemporaryDirectory() as d:
            lf = self.ledger(d, [('review-T64r3', 'sonnet', 'DONE bugs=1')])
            self.assertEqual(closeout.review_route(lf, 'v1', os.path.join(d, 'v1-T64-r3-rereview.md')),
                             'sonnet_review')

    def test_hyphenated_task_still_matches(self):
        with tempfile.TemporaryDirectory() as d:
            lf = self.ledger(d, [('review-T64-r3', 'sonnet', 'DONE bugs=1')])
            self.assertEqual(closeout.review_route(lf, 'v1', os.path.join(d, 'v1-T64-r3-rereview.md')),
                             'sonnet_review')

    def test_unmatched_files_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            lf = self.ledger(d, [])
            p = os.path.join(d, 'v1-T9-code-review.md')
            open(p, 'w').write(TABLE)
            from unittest import mock
            with mock.patch.object(closeout, 'review_files', return_value=[p]):
                self.assertEqual(closeout.unmatched_files({}, lf, 'v1'), ['v1-T9-code-review.md'])


if __name__ == '__main__':
    unittest.main()
