"""v1 portability lessons: eyeball build/howto, generator setup, autoMode line, tasks_file.
Run: python3 -m unittest discover tests"""
import io, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import checks
import eyeball
import init
import preflight
import tasks


def A(**kw):
    a = {'_main': '/repo', 'worktree_parent': '..', 'eyeball_build': None, 'eyeball_howto': None, 'path_prefix': ''}
    a.update(kw)
    return a


class EyeballBuild(unittest.TestCase):
    def test_defaults_are_off(self):
        self.assertIsNone(ad.DEFAULTS['eyeball_build'])
        self.assertIsNone(ad.DEFAULTS['eyeball_howto'])

    def test_no_build_command_is_a_pass(self):
        self.assertTrue(eyeball.build(A(), '/tmp'))

    def test_runs_in_the_tree_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertTrue(eyeball.build(A(eyeball_build='touch built'), d))
            self.assertTrue(os.path.exists(os.path.join(d, 'built')))
            with redirect_stdout(io.StringIO()):
                self.assertFalse(eyeball.build(A(eyeball_build='exit 3'), d))


class EyeballHowto(unittest.TestCase):
    def test_none_when_unset(self):
        self.assertIsNone(eyeball.howto(A(), 'v1'))

    def test_fills_worktree_and_release(self):
        a = A(eyeball_howto='Load {worktree}/.output/chrome-mv3 unpacked; after a fix round reload ({release}).')
        with mock.patch.object(ad, 'worktree_path', return_value='/wt/repo-eyeball-v1'):
            self.assertEqual(eyeball.howto(a, 'v1'),
                             'Load /wt/repo-eyeball-v1/.output/chrome-mv3 unpacked; after a fix round reload (v1).')

    def test_checks_add_prints_it(self):
        with tempfile.TemporaryDirectory() as d:
            a = A(eyeball_howto='Load {worktree}/out.')
            f = os.path.join(d, 'eyeball.md')
            argv = ['add', '/repo', '--release', 'v1', '--task', 'T1', '--where', 'popup', 'look', 'at', 'it']
            with mock.patch.object(checks.ad, 'load', return_value=(a, '/repo')), \
                    mock.patch.object(checks.ad, 'resolve_release', return_value='v1'), \
                    mock.patch.object(checks, 'path', return_value=f), \
                    mock.patch.object(checks.ad, 'worktree_path', return_value='/wt/x'), \
                    redirect_stdout(io.StringIO()) as out:
                checks.run(argv)
            self.assertIn('how to look: Load /wt/x/out.', out.getvalue())


class GeneratorSteps(unittest.TestCase):
    def repo(self, d, files):
        import json
        for path, pkg in files.items():
            os.makedirs(os.path.join(d, os.path.dirname(path)), exist_ok=True)
            open(os.path.join(d, path), 'w').write(json.dumps(pkg))

    def test_wxt_needs_prepare(self):
        with tempfile.TemporaryDirectory() as d:
            self.repo(d, {'package.json': {'devDependencies': {'wxt': '^0.19'}, 'scripts': {'build': 'wxt build'}}})
            self.assertEqual(init.generator_steps(d), ['npx wxt prepare'])

    def test_a_postinstall_that_runs_it_is_enough(self):
        with tempfile.TemporaryDirectory() as d:
            self.repo(d, {'package.json': {'devDependencies': {'wxt': '1'}, 'scripts': {'postinstall': 'wxt prepare'}}})
            self.assertEqual(init.generator_steps(d), [])

    def test_subfolder_and_the_other_generators(self):
        with tempfile.TemporaryDirectory() as d:
            self.repo(d, {'web/package.json': {'dependencies': {'@sveltejs/kit': '1', '@prisma/client': '1'},
                                               'devDependencies': {'prisma': '1', 'nuxt': '1'}}})
            self.assertEqual(init.generator_steps(d),
                             ['(cd web && npx prisma generate)', '(cd web && npx svelte-kit sync)',
                              '(cd web && npx nuxi prepare)'])

    def test_nothing_known_nothing_proposed(self):
        with tempfile.TemporaryDirectory() as d:
            self.repo(d, {'package.json': {'dependencies': {'left-pad': '1'}}})
            self.assertEqual(init.generator_steps(d), [])


class AutoModeEntry(unittest.TestCase):
    def settings(self, d, env):
        import json
        os.makedirs(os.path.join(d, 'proj', '.claude'))
        open(os.path.join(d, 'proj', '.claude', 'settings.json'), 'w').write(json.dumps({'autoMode': {'environment': env}}))
        return os.path.join(d, 'proj')

    def test_line_names_the_worktree_pattern(self):
        line = ad.auto_mode_line('/home/b/products/my-ext')
        self.assertIn('/home/b/products/my-ext-*', line)
        self.assertIn('.coordinate/releases/*/briefs/', line)
        self.assertIn('Pushes stay', line)

    def test_named_when_an_entry_mentions_the_repo(self):
        with tempfile.TemporaryDirectory() as d:
            main = self.settings(d, ['unrelated', 'the workflow in proj-* worktrees'])
            self.assertTrue(ad.auto_mode_named(main, home=d))

    def test_not_named_otherwise(self):
        with tempfile.TemporaryDirectory() as d:
            main = self.settings(d, ['only other-repo here'])
            self.assertFalse(ad.auto_mode_named(main, home=d))
            self.assertIn('autoMode.environment', preflight.auto_mode_warning(main, home=d))

    def test_no_warning_when_named(self):
        with tempfile.TemporaryDirectory() as d:
            main = self.settings(d, ['proj sibling worktrees'])
            self.assertIsNone(preflight.auto_mode_warning(main, home=d))


TASKS = ('# Tasks\n\n## v1\n'
         '- [x] T1 \u2014 done thing\n'
         '- [ ] T2 \u2014 open, in the ledger\n'
         '- [ ] T3 \u2014 open, never started\n'
         '- [ ] T4a \u2014 open, merged\n'
         '- [ ] v2: no id, ignored\n'
         '- [ ] T15\u2013T19 \u2014 a range, first id only\n')


class TasksFile(unittest.TestCase):
    def file(self, d):
        p = os.path.join(d, 'TASKS.md')
        open(p, 'w').write(TASKS)
        return p

    def test_defaults_off(self):
        self.assertIsNone(ad.DEFAULTS['tasks_file'])

    def test_parse(self):
        with tempfile.TemporaryDirectory() as d:
            got = [(t, done) for t, done, _ in tasks.parse(self.file(d))]
        self.assertEqual(got, [('T1', True), ('T2', False), ('T3', False), ('T4a', False), ('T15', False)])

    def test_open_not_in_the_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [('11-02 10:00', 'T2', 'devin-swe2', 'LAUNCHED x'), ('11-02 11:00', 'review-T4a', 'sonnet', 'DONE'),
                    ('11-02 12:00', 'T15+T16', 'x', 'LAUNCHED y')]
            self.assertEqual([t for t, _ in tasks.untracked(self.file(d), rows)], ['T3'])

    def test_sync_ticks_merged_tasks_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.file(d)
            rows = [('11-02 10:00', 'T4a', 'coordinator', 'MERGED abc'), ('11-02 10:05', 'T2', 'coordinator', 'LAUNCHED x'),
                    ('11-02 10:06', 'T1', 'coordinator', 'MERGED def')]
            self.assertEqual(tasks.sync(p, rows), ['T4a'])
            text = open(p).read()
            self.assertIn('- [x] T4a', text)
            self.assertIn('- [ ] T2', text)
            self.assertEqual(tasks.sync(p, rows), [])



TM = {'master': {'tasks': [
    {'id': 10, 'status': 'done'}, {'id': 11, 'status': 'pending'}, {'id': 12, 'status': 'pending'},
    {'id': 13, 'status': 'in-progress'}, {'id': 14, 'status': 'in-progress'}, {'id': 15, 'status': 'cancelled'}]}}


class TaskMasterTracker(unittest.TestCase):
    def file(self, d):
        import json
        p = os.path.join(d, 'tasks.json')
        open(p, 'w').write(json.dumps(TM))
        return p

    def test_statuses(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(tasks.taskmaster(self.file(d))['11'], 'pending')

    def test_ledger_ids_are_plain_numbers_not_versions(self):
        rows = [('', 'review-11', 'x', ''), ('', '12r2', 'x', ''), ('', 'T9', 'x', ''), ('', '2.12.0', 'x', ''),
                ('', '10+11', 'x', '')]
        self.assertEqual(tasks.tm_ids(rows), {'10', '11', '12'})

    def test_drift_is_merged_but_not_done_and_in_progress_untouched(self):
        rows = [('', '11', 'c', 'MERGED abc'), ('', '10', 'c', 'MERGED def'), ('', '13', 'd', 'LAUNCHED x'),
                ('', '12', 'd', 'LAUNCHED y')]
        with tempfile.TemporaryDirectory() as d:
            drift, idle = tasks.tm_drift(self.file(d), rows)
        self.assertEqual(drift, ['11'])
        self.assertEqual(idle, ['14'])

    def test_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            tm = self.file(d)
            self.assertEqual(tasks.tracker({'tracker': None, 'tasks_file': None, 'taskmaster': 'tasks.json'}, d),
                             ('taskmaster', tm))
            self.assertEqual(tasks.tracker({'tracker': None, 'tasks_file': 'T.md', 'taskmaster': None}, d),
                             ('markdown', os.path.join(d, 'T.md')))
            self.assertEqual(tasks.tracker({'tracker': 'none', 'tasks_file': 'T.md', 'taskmaster': 'tasks.json'}, d),
                             (None, None))
            self.assertEqual(tasks.tracker({'tracker': None, 'tasks_file': None, 'taskmaster': None}, d), (None, None))

    def test_taskmaster_lines_report_drift_and_never_write(self):
        rows = [('', '11', 'c', 'MERGED abc')]
        with tempfile.TemporaryDirectory() as d:
            tm = self.file(d)
            before = open(tm).read()
            a = {'tracker': None, 'tasks_file': None, 'taskmaster': 'tasks.json'}
            st = tasks.status_lines(a, d, rows)
            co = tasks.closeout_lines(a, d, rows)
            self.assertEqual(open(tm).read(), before)
        self.assertTrue(any('11' in l and 'not done' in l for l in st + co))
        self.assertTrue(any('set_task_status' in l for l in co))

    def test_markdown_closeout_ticks(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'TASKS.md'), 'w').write('- [ ] T4a \u2014 x\n')
            a = {'tracker': None, 'tasks_file': 'TASKS.md', 'taskmaster': None}
            out = tasks.closeout_lines(a, d, [('', 'T4a', 'c', 'MERGED z')])
            self.assertIn('ticked 1', out[0])
            self.assertIn('[x] T4a', open(os.path.join(d, 'TASKS.md')).read())


class InitTracker(unittest.TestCase):
    def test_detects_taskmaster(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, '.taskmaster', 'tasks'))
            open(os.path.join(d, '.taskmaster', 'tasks', 'tasks.json'), 'w').write('{}')
            self.assertEqual(init.detect_tracker(d), {'tracker': 'taskmaster', 'taskmaster': '.taskmaster/tasks/tasks.json'})

    def test_detects_an_existing_markdown_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'documentation'))
            open(os.path.join(d, 'documentation', 'TASKS.md'), 'w').write('# T\n')
            self.assertEqual(init.detect_tracker(d), {'tracker': 'markdown', 'tasks_file': 'documentation/TASKS.md'})

    def test_default_is_tasks_md_and_init_creates_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(init.detect_tracker(d), {'tracker': 'markdown', 'tasks_file': 'TASKS.md'})
            self.assertTrue(init.ensure_tasks_file(d, 'TASKS.md'))
            self.assertIn('- [ ]', open(os.path.join(d, 'TASKS.md')).read())
            self.assertFalse(init.ensure_tasks_file(d, 'TASKS.md'))


if __name__ == '__main__':
    unittest.main()
