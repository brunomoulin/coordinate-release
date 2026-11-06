"""The public tree: private planning files left out, the public roadmap in, no private name left.
Runs only in the working repo (the public tree has no publish/). Run: python3 -m unittest discover tests"""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PUBLISH = os.path.join(ROOT, 'publish')


@unittest.skipUnless(os.path.isdir(PUBLISH), 'public tree: nothing to export')
class PublicExport(unittest.TestCase):
    def test_head_exports_clean(self):
        sys.path.insert(0, PUBLISH)
        import export
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, 'pub')
            found = export.export(dest, 'HEAD')
            self.assertEqual(found, [])
            files = {os.path.relpath(os.path.join(r, f), dest) for r, _, fs in os.walk(dest) for f in fs}
            for p in export.PRIVATE[1:]:
                self.assertEqual({f for f in files if f == p or f.startswith(p + '/')} - set(export.KEEP), set(), p)
            self.assertEqual(open(os.path.join(dest, 'ROADMAP.md')).read(),
                             subprocess.run(['git', '-C', ROOT, 'show', 'HEAD:publish/ROADMAP.md'],
                                            capture_output=True, text=True, check=True).stdout)
            self.assertTrue(os.path.exists(os.path.join(dest, 'documentation', 'active', '.gitkeep')))


if __name__ == '__main__':
    unittest.main()
