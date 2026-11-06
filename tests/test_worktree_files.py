"""Each worktree's changed files in status.py, for the pane's MAP trees. Run: python3 -m unittest discover tests"""
import os, subprocess, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import status


def git(cwd, *args):
    subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


class ChangedFiles(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.main = os.path.join(root, 'repo')
        self.wt = os.path.join(root, 'repo-342')
        os.makedirs(self.main)
        git(self.main, 'init', '-q', '-b', 'main')
        git(self.main, 'config', 'user.email', 't@t')
        git(self.main, 'config', 'user.name', 't')
        write(f'{self.main}/README.md', 'a\nb\n')
        write(f'{self.main}/src/old.ts', 'x\n')
        git(self.main, 'add', '.')
        git(self.main, 'commit', '-qm', 'init')
        git(self.main, 'worktree', 'add', '-q', self.wt, '-b', 'bugfix/342')
        # Committed on the branch: one file added, one edited, one deleted.
        write(f'{self.wt}/src/auth/login.ts', '1\n2\n3\n')
        write(f'{self.wt}/README.md', 'a\nc\n')
        os.remove(f'{self.wt}/src/old.ts')
        git(self.wt, 'add', '-A')
        git(self.wt, 'commit', '-qm', 'fix')
        # Main moves on: the branch's own changes are counted from the fork point, not main's tip.
        write(f'{self.main}/later.ts', 'z\n')
        git(self.main, 'add', '.')
        git(self.main, 'commit', '-qm', 'later')
        # Not committed: an edit on top of the commit, and a new file.
        write(f'{self.wt}/src/auth/login.ts', '1\n2\n3\n4\n')
        write(f'{self.wt}/notes.md', 'n\n')

    def test_committed_and_unsaved_changes_since_the_fork_point(self):
        base = subprocess.run(['git', '-C', self.wt, 'merge-base', 'main', 'HEAD'], capture_output=True, text=True).stdout.strip()
        self.assertEqual(status.changed_files(self.wt, base), [
            {'path': 'README.md', 'status': 'M', 'add': 1, 'del': 1, 'unsaved': False},
            {'path': 'notes.md', 'status': '?', 'add': 0, 'del': 0, 'unsaved': True},
            {'path': 'src/auth/login.ts', 'status': 'A', 'add': 4, 'del': 0, 'unsaved': True},
            {'path': 'src/old.ts', 'status': 'D', 'add': 0, 'del': 1, 'unsaved': False},
        ])

    def test_worktrees_carry_their_files_capped(self):
        a = {'main_branch': 'main'}
        with mock.patch.object(status, 'FILES_CAP', 3):
            trees = {t['name']: t for t in status.worktrees(a, self.main, set())}
        self.assertEqual([f['path'] for f in trees['repo-342']['files']], ['README.md', 'notes.md', 'src/auth/login.ts'])
        self.assertEqual(trees['repo-342']['files_more'], 1)
        # Main's files are its uncommitted ones: none here.
        self.assertEqual(trees['repo']['files'], [])
        self.assertEqual(trees['repo']['files_more'], 0)


if __name__ == '__main__':
    unittest.main()
