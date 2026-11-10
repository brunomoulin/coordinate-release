"""Findings from recording the README demos (2.33.1): a second Claude profile (CLAUDE_CONFIG_DIR),
the generic autoMode line, quests that merge, and the away-pick review batch.
Run: python3 -m unittest discover tests"""
import io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
sys.path.insert(0, os.path.dirname(__file__))
import adapter as ad
import ledger as lg
import preflight
import session
from test_settings import Repo

GENERIC = ('**Coordinator workflow (authorized by the owner)**: in any repo with a committed '
           '`.claude/coordinate.json`, the coordinator session launching `devin -p ...` is the sanctioned workflow.')


def profile(d, settings):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'settings.json'), 'w').write(json.dumps(settings))
    return d


class ConfigDir(unittest.TestCase):
    """CLAUDE_CONFIG_DIR names the profile Claude Code runs with: its settings and transcripts."""

    def test_default_is_home_claude(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CLAUDE_CONFIG_DIR', None)
            self.assertEqual(ad.claude_dir(), os.path.expanduser('~/.claude'))

    def test_env_wins(self):
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/x/demo'}):
            self.assertEqual(ad.claude_dir(), '/x/demo')

    def test_auto_mode_read_from_the_profile(self):
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, 'proj')
            os.makedirs(main)
            prof = profile(os.path.join(d, 'demo'), {'autoMode': {'environment': ['in proj, the workflow']}})
            with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': prof}):
                self.assertTrue(ad.auto_mode_named(main))
                self.assertIsNone(preflight.auto_mode_warning(main))

    def test_allow_rules_read_from_the_profile(self):
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, 'proj')
            os.makedirs(main)
            prof = profile(os.path.join(d, 'demo'), {'permissions': {'allow': ['Bash(devin -p *)']}})
            with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': prof}):
                self.assertIn('Bash(devin -p *)', preflight.allow_rules(main))

    def test_transcript_from_the_profile(self):
        with tempfile.TemporaryDirectory() as d:
            mine = os.path.join(d, 'demo', 'projects', '-tmp-proj', 'abc.jsonl')
            os.makedirs(os.path.dirname(mine))
            open(mine, 'w').close()
            with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': os.path.join(d, 'demo'),
                                              'CLAUDE_CODE_SESSION_ID': 'abc'}):
                self.assertEqual(session.transcript(), mine)
            with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': os.path.join(d, 'demo')}):
                os.environ.pop('CLAUDE_CODE_SESSION_ID', None)
                self.assertEqual(session.transcript(), mine)

    def test_warning_names_the_profile_settings(self):
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, 'proj')
            os.makedirs(main)
            with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': os.path.join(d, 'demo')}):
                self.assertIn(os.path.join(d, 'demo', 'settings.json'), preflight.auto_mode_warning(main))


class AllowRules(unittest.TestCase):
    def test_broader_rules_cover(self):
        for have in ({'Bash(devin -p *)'}, {'Bash(devin:*)'}, {'Bash(devin *)'}, {'Bash(*)'}, {'Bash'}):
            self.assertTrue(preflight.allowed('Bash(devin -p *)', have), have)

    def test_other_rules_do_not(self):
        for have in (set(), {'Bash(devin list *)'}, {'Bash(dev:*)'}, {'Bash(git:*)'}):
            self.assertFalse(preflight.allowed('Bash(devin -p *)', have), have)


class GenericLine(unittest.TestCase):
    """One line for every repo with an adapter covers this one too."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.main = os.path.join(self.home, 'proj')
        os.makedirs(self.main)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generic_line_covers_any_repo(self):
        profile(os.path.join(self.home, '.claude'), {'autoMode': {'environment': [GENERIC]}})
        self.assertTrue(ad.auto_mode_named(self.main, home=self.home))
        self.assertIsNone(preflight.auto_mode_warning(self.main, home=self.home))

    def test_generic_swe2_only_is_outdated(self):
        old = GENERIC.replace('`devin -p ...`', '`devin -p --model swe-2-high|swe-2-medium`')
        profile(os.path.join(self.home, '.claude'), {'autoMode': {'environment': [old]}})
        self.assertTrue(ad.auto_mode_outdated(self.main, home=self.home))

    def test_other_coordinator_line_does_not(self):
        other = GENERIC.replace('any repo with a committed `.claude/coordinate.json`', 'other-repo')
        profile(os.path.join(self.home, '.claude'), {'autoMode': {'environment': [other]}})
        self.assertFalse(ad.auto_mode_named(self.main, home=self.home))

    def test_generic_line_text(self):
        line = ad.auto_mode_line_generic()
        self.assertIn('any repo with a committed `.claude/coordinate.json`', line)
        self.assertTrue(ad.auto_mode_covers(line, self.main))


class Quests(Repo):
    """The pane's XP: build tasks that merge. Reviews and the release's own rows are not quests."""

    def tasks(self):
        import status
        with mock.patch.object(status, 'devin_procs', return_value=[]):
            return {t['task']: t for t in status.as_json(*ad.load(self.repo, '1.1'), '1.1')['tasks']}

    def add(self, task, ev):
        quiet = io.StringIO()
        with redirect_stdout(quiet):
            lg.add(self.f, task, 'coordinator', ev)

    def test_builds_reviews_and_release_rows(self):
        self.add('median', 'ROUTE -> devin_swe2 posture=ON_PACE why="default builder"')
        self.add('median', 'LAUNCHED feat/0.2-median')
        self.add('review-median', 'ROUTE -> opus_review posture=ON_PACE why="before merge"')
        self.add('review-median', 'DONE bugs=0')
        self.add('crit-median', 'ROUTE -> swe2_review posture=ON_PACE why="critique"')
        self.add('-', 'AWAY on')
        self.add('legacy', 'LAUNCHED feat/legacy')
        t = self.tasks()
        self.assertTrue(t['median']['quest'])
        self.assertTrue(t['legacy']['quest'])
        self.assertFalse(t['review-median']['quest'])
        self.assertFalse(t['crit-median']['quest'])
        self.assertFalse(t['-']['quest'])

    def test_reroute_to_a_build_counts(self):
        self.add('x', 'ROUTE -> opus_review posture=ON_PACE why="mistake"')
        self.add('x', 'ROUTE -> sonnet_implement posture=ON_PACE why="it is a build"')
        self.assertTrue(self.tasks()['x']['quest'])


class AwayReviewBatch(unittest.TestCase):
    """AskUserQuestion takes at most 4 options: 5 picks in one question lost one (A3, 0.3 demo)."""

    def test_skill_splits_picks_by_four(self):
        p = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'SKILL.md')
        text = open(p).read()
        step = text.split('## 0.', 1)[1].split('\n## ', 1)[0]
        self.assertIn('at most 4 options', step)
        self.assertNotIn('(one multiSelect question)', text)


if __name__ == '__main__':
    unittest.main()
