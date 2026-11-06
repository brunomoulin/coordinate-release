"""second pilot v1 lessons, batch 1: archive path, session.py without a release, archive key scan,
preflight archive/untracked checks. Run: python3 -m unittest discover tests"""
import os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import closeout
import preflight
import session


class ArchivePath(unittest.TestCase):
    def test_template(self):
        self.assertEqual(ad.archive_path({'ledger_archive': 'docs/{release}-ledger.md'}, 'v1'), 'docs/v1-ledger.md')

    def test_folder_value_means_release_md(self):
        # v1: "documentation/history/coordinate/" crashed closeout.py
        self.assertEqual(ad.archive_path({'ledger_archive': 'documentation/history/coordinate/'}, 'v1'),
                         'documentation/history/coordinate/v1.md')

    def test_unset(self):
        self.assertIsNone(ad.archive_path({'ledger_archive': None}, 'v1'))


class PreflightArchive(unittest.TestCase):
    def test_fixed_file_name_fails(self):
        self.assertIn('{release}', preflight.archive_problem({'ledger_archive': 'docs/ledger.md'}))

    def test_ok_values(self):
        for v in (None, 'docs/{release}.md', 'docs/history/'):
            self.assertIsNone(preflight.archive_problem({'ledger_archive': v}), v)


class SessionNoRelease(unittest.TestCase):
    def test_merges_since_without_release(self):
        self.assertIsNone(session.merges_since({}, None, '2026-11-02T10:00:00'))


class KeyScan(unittest.TestCase):
    def test_hits(self):
        for s in ('key sk-ant-api03-abcdefghijklmnopqrstuvwx', 'AKIAABCDEFGHIJKLMNOP',
                  'ghp_' + 'a' * 36, 'AIza' + 'b' * 35, '-----BEGIN PRIVATE KEY-----',
                  'API_KEY=abcdef0123456789abcdef0123'):
            self.assertTrue(closeout.key_hits(s), s)

    def test_clean(self):
        self.assertEqual(closeout.key_hits('Fixed T64 in 2.1.0; set API_KEY in .env\n'), [])

    def test_archive_refuses_on_a_hit(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'timeline.md')
            open(src, 'w').write('pasted: ghp_' + 'a' * 36 + '\n')
            dst = os.path.join(d, 'out', 'v1.md')
            with self.assertRaises(closeout.KeyFound):
                closeout.archive(src, dst)
            self.assertFalse(os.path.exists(dst))


class UntrackedOnMain(unittest.TestCase):
    def test_lists_untracked(self):
        with tempfile.TemporaryDirectory() as root:
            for c in (['init', '-q', '-b', 'main'], ['config', 'user.email', 't@t'], ['config', 'user.name', 't']):
                subprocess.run(['git', '-C', root, *c], check=True)
            open(os.path.join(root, 'a'), 'w').write('x')
            subprocess.run(['git', '-C', root, 'add', '-A'], check=True)
            subprocess.run(['git', '-C', root, 'commit', '-qm', 'b'], check=True)
            os.makedirs(os.path.join(root, '.codex'))
            open(os.path.join(root, '.codex', 'f'), 'w').write('x')
            self.assertEqual(preflight.untracked(root), ['.codex/'])


if __name__ == '__main__':
    unittest.main()
