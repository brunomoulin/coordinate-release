"""No owner is named in the skill: an older `NEEDS <name>` verdict still parses, and a disposition
handed to the owner counts by the word "owner" or the adapter's `owner_name` (2.30.0).
Run: python3 -m unittest discover tests"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import checks as ck
import findings as fd


class OwnerName(unittest.TestCase):
    def test_any_needs_verdict_waits_on_the_owner(self):
        fh = tempfile.NamedTemporaryFile('w', suffix='.md', delete=False)
        fh.write('## #1 NEEDS OWNER\nhow it looks\n\n## #2 NEEDS ALEX\nlogin needed\n\n## #3 PASS\nok\n')
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        v = ck.verdicts(fh.name)
        self.assertEqual({i: s for i, (s, _) in v.items()}, {1: 'needs-human', 2: 'needs-human', 3: 'agent-pass'})

    def test_a_disposition_to_the_owner(self):
        self.assertEqual(fd.classify('Asked the owner: scope call'), 'to owner')
        self.assertEqual(fd.classify('Asked Alex: scope call'), 'fixed')
        self.assertEqual(fd.classify('Asked Alex: scope call', 'Alex'), 'to owner')
        self.assertEqual(fd.classify('Owner said fix it; fixed in r2', 'Alex'), 'fixed')

    def test_owner_name_defaults_to_none(self):
        self.assertIsNone(ad.DEFAULTS['owner_name'])


if __name__ == '__main__':
    unittest.main()
