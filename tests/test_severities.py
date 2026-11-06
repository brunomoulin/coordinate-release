"""Review severities: Bug / Risk / Improvement / Suggestion / Nit rows all count (the second pilot's v2-perf
finding 4). Run: python3 -m unittest discover tests"""
import os, re, subprocess, sys, tempfile, unittest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'coordinate', 'skills', 'coordinate')
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
import findings as fd

# The shape of v2-perf-T87-code-review.md: the project's brief asked for Bug / Risk / Nit, and
# dispose.py printed "no findings rows" and filled nothing.
V2_PERF = ('| # | Severity | File:line | Finding | Fix | Disposition |\n|---|---|---|---|---|---|\n'
           '| 1 | Risk | providers.ts:479 | none is a request | say so | |\n'
           '| 2 | nit | providers.ts:12 | comment | reword | |\n'
           '| 3 | Bug | a.ts:1 | x | z | Fixed in r2 |\n'
           '| 4 | Note | a.ts:2 | not a severity | - | |\n')


class Severities(unittest.TestCase):
    def setUp(self):
        fh = tempfile.NamedTemporaryFile('w', suffix='-code-review.md', delete=False)
        fh.write(V2_PERF)
        fh.close()
        self.path = fh.name
        self.addCleanup(os.unlink, self.path)

    def test_risk_and_nit_are_rows(self):
        self.assertEqual([(r[1], r[2]) for r in fd.rows(self.path)], [('1', 'Risk'), ('2', 'Nit'), ('3', 'Bug')])

    def test_dispose_fills_them(self):
        r = subprocess.run([sys.executable, os.path.join(SKILL, 'scripts', 'dispose.py'), self.path,
                            'To fix in round 2', '2=Not doing: wording only, final'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('filled 2', r.stdout)
        got = {r[1]: r[3][-1] for r in fd.rows(self.path)}
        self.assertEqual(got, {'1': 'To fix in round 2', '2': 'Not doing: wording only, final', '3': 'Fixed in r2'})

    def test_template_names_what_findings_reads(self):
        # One list: the brief's severities are the ones findings.py matches.
        t = open(os.path.join(SKILL, 'references', 'review-brief-template.md')).read()
        named = re.search(r'Severity\s+is\s+one\s+of\s+(.+?)\.\s+Leave', t, re.S)
        self.assertTrue(named, 'review-brief-template.md names no severities')
        self.assertEqual(set(re.findall(r'`(\w+)`', named.group(1))), set(fd.SEVERITIES))


if __name__ == '__main__':
    unittest.main()
