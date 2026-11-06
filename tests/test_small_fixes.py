"""findings rows with any id, sonnet_review, DB tests touched by a diff. Run: python3 -m unittest discover tests"""
import os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import budget
import db
import findings as fd


class FindingIds(unittest.TestCase):
    def test_rereview_ids_are_rows(self):
        # pilot 2.11.0: a re-review numbered R2-1..R2-5; dispose.py filled 0 and said nothing.
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False) as f:
            f.write('| # | Severity | File:line | Finding | Fix | Disposition |\n|---|---|---|---|---|---|\n'
                    '| R2-1 | Bug | a.ts:1 | x | z | |\n| 3 | Suggestion | b.ts:2 | y | z | Fixed |\n')
        try:
            self.assertEqual([r[1] for r in fd.rows(f.name)], ['R2-1', '3'])
        finally:
            os.unlink(f.name)


class SonnetReview(unittest.TestCase):
    def test_route_exists_and_is_inferred(self):
        self.assertIn('sonnet_review', budget.ALL_ROUTES)
        self.assertEqual(budget.infer_route('sonnet', 'rereview-466'), 'sonnet_review')
        self.assertEqual(budget.infer_route('sonnet', 'critique-470'), 'sonnet_critique')
        self.assertEqual(budget.infer_route('sonnet', '466'), 'sonnet_implement')

    def test_allowed_until_critical(self):
        for p in ('SURPLUS', 'ON PACE', 'TIGHT'):
            self.assertIn('sonnet_review', budget.ROUTES[p]['review'], p)
        self.assertNotIn('sonnet_review', budget.ROUTES['CRITICAL']['review'])


def git(cwd, *args):
    subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True)


def write(root, path, text):
    p = os.path.join(root, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write(text)


class TouchedDbTests(unittest.TestCase):
    def test_existing_db_tests_importing_a_changed_file(self):
        # pilot 2.11.0 task 497: an upload path changed; a DB test went red unseen.
        with tempfile.TemporaryDirectory() as root:
            git(root, 'init', '-q', '-b', 'main')
            git(root, 'config', 'user.email', 't@t')
            git(root, 'config', 'user.name', 't')
            write(root, 'src/services/upload.ts', 'export const a = 1\n')
            write(root, 'src/services/other.ts', 'export const b = 1\n')
            write(root, 'src/tests/db/linked.dbtest.ts',
                  "import { a } from '../../services/upload';\nvi.mock('../../services/other', () => ({}));\n")
            write(root, 'src/tests/db/mocked.dbtest.ts', "vi.mock('../../services/upload', () => ({}));\n")
            write(root, 'src/tests/db/unrelated.dbtest.ts', "import { b } from '../../services/other.js';\n")
            git(root, 'add', '-A')
            git(root, 'commit', '-qm', 'base')
            git(root, 'switch', '-qc', 'task')
            write(root, 'src/services/upload.ts', 'export const a = 2\n')
            git(root, 'commit', '-qam', 'change the door')
            write(root, 'src/tests/db/new.dbtest.ts', "import { a } from '../../services/upload';\n")
            a = {'main_branch': 'main', 'db_test': {}}
            self.assertEqual(db.touched_db_tests(a, root), ['src/tests/db/linked.dbtest.ts'])


if __name__ == '__main__':
    unittest.main()
