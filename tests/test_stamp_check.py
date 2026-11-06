"""The stamp check (db.stamp_check) and the close-out's "ships in R" claims. Run: python3 -m unittest discover tests"""
import json, os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import closeout
import db


def git(cwd, *args):
    return subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True, text=True).stdout.strip()


def write(root, path, text):
    p = os.path.join(root, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write(text)


class StampCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, 'repo-task')
        os.makedirs(self.root)
        git(self.root, 'init', '-q', '-b', 'main')
        git(self.root, 'config', 'user.email', 't@t')
        git(self.root, 'config', 'user.name', 't')
        write(self.root, 'src/a.ts', 'export const a = 1\n')
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-qm', 'base')
        git(self.root, 'switch', '-qc', 'task')
        write(self.root, 'src/tests/db/new.dbtest.ts', 'test\n')
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-qm', 'new test')
        self.a = {'main_branch': 'main', 'db_test': {}, 'log_dir': os.path.join(self.tmp.name, 'logs')}

    def tearDown(self):
        self.tmp.cleanup()

    def stamp(self, code, recheck=False, head=None, files=('new.dbtest.ts',)):
        os.makedirs(self.a['log_dir'], exist_ok=True)
        with open(db.stamps_file(self.a), 'a') as f:
            f.write(json.dumps({'ts': '2026-10-26 21:00', 'wt': 'repo-task',
                                'head': head or git(self.root, 'rev-parse', 'HEAD'),
                                'files': list(files), 'code': code, 'recheck': recheck,
                                'reviewed': recheck}) + '\n')

    def whys(self):
        return [why for _, why in db.stamp_check(self.a, self.root)]

    def test_no_run_is_a_miss(self):
        # pilot 2.11.0: 38 implementer runs unstamped against 18 stamped.
        self.assertEqual(self.whys(), ['no db.py run at HEAD'])

    def test_green_at_head_passes(self):
        self.stamp(0, files=('src/tests/db/new.dbtest.ts',))  # matched by basename
        self.assertEqual(self.whys(), [])

    def test_older_commit_is_a_miss(self):
        self.stamp(0, head=git(self.root, 'rev-parse', 'HEAD~1'))
        self.assertEqual(self.whys(), ['no db.py run at HEAD'])

    def test_latest_run_decides(self):
        self.stamp(0)
        self.stamp(1)
        self.assertEqual(self.whys(), ['red at HEAD (exit 1)'])

    def test_guard_then_coordinator_reviewed_run(self):
        self.stamp(7)
        self.assertEqual(self.whys(), ['the guard refused it at HEAD (exit 7)'])
        self.stamp(0, recheck=True)
        self.assertEqual(self.whys(), [])

    def test_dirty_tree_is_named(self):
        write(self.root, 'src/a.ts', 'export const a = 2\n')
        self.assertIn('uncommitted changes: commit, then run db.py again', self.whys())


class ShipsClaims(unittest.TestCase):
    def test_lines_that_say_r_ships(self):
        # pilot 2.11.0: "2.11.0 ships only the optional MFA" had no commit behind it.
        with tempfile.TemporaryDirectory() as root:
            git(root, 'init', '-q', '-b', 'main')
            write(root, 'ROADMAP.md', '- 2.11.0 ships only the optional MFA\n- 2.11.0 fixes the list\n'
                                      '- 2.11.01 ships nothing\n- shipped in 2.11.0: uploads\n')
            write(root, '.coordinate/ledgers/2.11.0.md', '2.11.0 ships everything\n')
            git(root, 'add', '-A')
            claims = closeout.ships_claims(root, '2.11.0')
            self.assertEqual(claims, ['ROADMAP.md:1:- 2.11.0 ships only the optional MFA',
                                      'ROADMAP.md:4:- shipped in 2.11.0: uploads'])


if __name__ == '__main__':
    unittest.main()
