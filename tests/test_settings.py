"""`/coordinate settings`: release SET rows, presets, the live Devin catalog, budget off, settings.py.
Run: python3 -m unittest discover tests"""
import io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import adapter as ad
import ledger as lg


def quiet(fn, *args, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kw)


def git(cwd, *args):
    subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True, text=True)


class Repo(unittest.TestCase):
    """A temp git repo with `.claude/coordinate.json` and a release folder 1.1."""
    adapter = {'session_limits': {'hard_tokens': 650000}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(os.path.join(self.tmp.name, 'proj'))
        os.makedirs(os.path.join(self.repo, '.claude'))
        git(self.repo, 'init', '-q', '-b', 'main')
        git(self.repo, 'config', 'user.email', 't@t')
        git(self.repo, 'config', 'user.name', 't')
        self.write_adapter(self.adapter)
        self.rel = os.path.join(self.repo, '.coordinate', 'releases', '1.1')
        quiet(lg.init, self.rel, '1.1')
        self.f = lg.resolve(self.rel)

    def tearDown(self):
        self.tmp.cleanup()

    def write_adapter(self, d):
        with open(os.path.join(self.repo, '.claude', 'coordinate.json'), 'w') as fh:
            json.dump(d, fh, indent=2)
            fh.write('\n')

    def row(self, event):
        quiet(lg.add, self.f, '-', 'owner', event)


class ReleaseOverlay(Repo):
    def test_set_row_overrides_repo(self):
        self.row('SET session_limits.hard_tokens=800000')
        a, _ = ad.load(self.repo, '1.1')
        self.assertEqual(a['session_limits']['hard_tokens'], 800000)
        self.assertEqual(a['_sources']['session_limits.hard_tokens'], 'release')
        self.assertEqual(ad.load(self.repo)[0]['session_limits']['hard_tokens'], 650000)

    def test_latest_row_wins_and_default_clears(self):
        self.row('SET session_limits.hard_tokens=700000')
        self.row('SET session_limits.hard_tokens=750000')
        self.assertEqual(ad.load(self.repo, '1.1')[0]['session_limits']['hard_tokens'], 750000)
        self.row('SET session_limits.hard_tokens=default')
        a, _ = ad.load(self.repo, '1.1')
        self.assertEqual(a['session_limits']['hard_tokens'], 650000)
        self.assertEqual(a['_sources']['session_limits.hard_tokens'], 'repo')

    def test_override_merges_per_route(self):
        self.write_adapter({'budget': {'overrides': {'opus_implement': False, 'sonnet_review': False}}})
        self.row('SET budget.overrides.opus_implement=true')
        a, _ = ad.load(self.repo, '1.1')
        self.assertEqual(a['budget']['overrides'], {'opus_implement': True, 'sonnet_review': False})

    def test_bad_json_row_is_skipped(self):
        self.row('SET budget.mode=off')
        err = io.StringIO()
        with redirect_stderr(err):
            a, _ = ad.load(self.repo, '1.1')
        self.assertEqual(a['budget'].get('mode', 'auto'), 'auto')
        self.assertIn('skipped', err.getvalue())

    def test_a_row_never_touches_defaults(self):
        self.row('SET budget.overrides.opus_implement=true')
        ad.load(self.repo, '1.1')
        self.assertEqual(ad.DEFAULTS['budget']['overrides'], {})

    def test_missing_release_folder_means_no_rows(self):
        a, _ = ad.load(self.repo, '9.9')
        self.assertEqual(a['session_limits']['hard_tokens'], 650000)


def catalog_json(high_tier='Free'):
    """A trimmed copy of the real `devin models list --format json` (2026-11-09)."""
    return json.dumps({'families': [
        {'family_uid': 'swe-2', 'variants': [
            {'model_uid': 'swe-2-high', 'label': 'SWE-2 High', 'cost_tier': high_tier,
             **({} if high_tier == 'Free' else {'cost_summary': '$0.3 / 1M Input · $1.2 / 1M Output'})},
            {'model_uid': 'swe-2-flash-high', 'label': 'SWE-2 Flash High', 'cost_tier': 'Free'}]},
        {'family_uid': 'gemini-4-argon', 'variants': [
            {'model_uid': 'gemini-4-argon-high', 'label': 'Gemini 4 Argon High', 'cost_tier': 'High cost',
             'cost_summary': '$2 / 1M Input · $0.2 / 1M Cached input · $10 / 1M Output'}]}]})


def fake_run(out=None, code=0, exc=None):
    def run(argv, **kw):
        if exc:
            raise exc
        return subprocess.CompletedProcess(argv, code, out or '', '')
    return run


class CatalogCase(unittest.TestCase):
    """DEVIN_CATALOG points at a temp file."""
    def setUp(self):
        self.ctmp = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.ctmp.name, 'devin-models.json')
        p = mock.patch.object(ad, 'DEVIN_CATALOG', self.cache)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.ctmp.cleanup)

    def refresh(self, **kw):
        return ad.devin_catalog(refresh=True, run=fake_run(**kw))


class Catalog(CatalogCase):
    def test_catalog_parses_and_caches(self):
        cat = self.refresh(out=catalog_json())
        self.assertEqual(cat['gemini-4-argon-high']['tier'], 'High cost')
        self.assertTrue(os.path.exists(self.cache))
        self.assertEqual(ad.free_devin_models(), ['swe-2-high', 'swe-2-flash-high'])

    def test_catalog_failure_uses_cache(self):
        self.assertEqual(sorted(self.refresh(exc=FileNotFoundError())), ['swe-2-high', 'swe-2-medium'])
        self.refresh(out=catalog_json())
        for kw in ({'exc': FileNotFoundError()}, {'code': 1}, {'out': 'not json'},
                   {'exc': subprocess.TimeoutExpired('devin', 60)}):
            self.assertIn('gemini-4-argon-high', self.refresh(**kw), kw)

    def test_tier_change_flips_cost(self):
        self.refresh(out=catalog_json())
        self.assertEqual(ad.devin_cost('swe-2-high'), 'free')
        self.refresh(out=catalog_json('Low cost'))
        self.assertEqual(ad.devin_cost('swe-2-high'), 'paid')

    def test_unlisted_model_is_paid(self):
        self.refresh(out=catalog_json())
        self.assertEqual(ad.devin_cost('gpt-astra'), 'paid')
        self.assertEqual(ad.devin_cost('gemini-4-argon-high'), 'paid')

    def test_devin_model_accepts_other(self):
        self.refresh(out=catalog_json())
        err = io.StringIO()
        with redirect_stderr(err):
            m = ad.devin_model({'devin': {'model': 'gpt-astra'}})
        self.assertEqual(m, 'gpt-astra')
        self.assertIn('paid', err.getvalue())
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(ad.devin_model({'devin': {'model': 'swe-2-high'}}), 'swe-2-high')
        self.assertEqual(err.getvalue(), '')

    def test_auto_mode_line_names_adapter(self):
        line = ad.auto_mode_line('/home/b/products/my-ext')
        self.assertNotIn('swe-2-high|', line)
        self.assertIn('any model `devin models list` shows', line)  # owner, 2026-11-09: release switches too

    def test_auto_mode_outdated(self):
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, 'proj')
            os.makedirs(os.path.join(main, '.claude'))
            sf = os.path.join(main, '.claude', 'settings.json')
            old = 'in proj, the coordinator launching `devin --model swe-2-high|swe-2-medium` in proj-*'
            json.dump({'autoMode': {'environment': [old]}}, open(sf, 'w'))
            self.assertTrue(ad.auto_mode_outdated(main, home=d))
            json.dump({'autoMode': {'environment': [ad.auto_mode_line(main)]}}, open(sf, 'w'))
            self.assertFalse(ad.auto_mode_outdated(main, home=d))

    def test_presets_only_known_keys(self):
        self.assertEqual(ad.PRESETS['balanced'], {})
        for name, overlay in ad.PRESETS.items():
            for key in overlay:
                parent = key.rsplit('.', 1)[0].split('.')
                d = ad.DEFAULTS
                for k in parent:
                    self.assertIn(k, d, f'{name}: {key}')
                    d = d[k]
                self.assertIsInstance(d, dict, f'{name}: {key}')
        self.assertEqual(ad.DEFAULTS['budget']['mode'], 'auto')
        self.assertEqual(ad.DEFAULTS['routing'], {'default_builder': 'devin'})
        self.assertIs(ad.PRESETS['frugal']['budget.overrides.opus_implement'], False)
        self.assertEqual(ad.PRESETS['all-out']['budget.mode'], 'off')


def sig(seven=50, elapsed=50, five=20):
    import time
    return {'five_hour_pct': five, 'five_hour_resets_at': None, 'seven_day_pct': seven,
            'seven_day_resets_at': time.time() + (1 - elapsed / 100) * 7 * 86400,
            'week_elapsed_pct': elapsed, 'devin_paid': None, 'context_tokens': None}


def adapter_with(**dotted):
    import copy
    a = copy.deepcopy(ad.DEFAULTS)
    for k, v in dotted.items():
        ad.set_dotted(a, k.replace('__', '.'), v)
    return a


class Routing(CatalogCase):
    """budget.py under the settings: mode off, ticked routes, the default builder, paid Devin."""
    def setUp(self):
        super().setUp()
        import budget, session
        self.budget, self.session = budget, session
        for name, val in (('spend', None), ('questions', [])):
            p = mock.patch.object(budget, name, return_value=val)
            p.start()
            self.addCleanup(p.stop)
        self.devin_state = {}
        p = mock.patch.object(budget, '_load', side_effect=lambda path: self.devin_state)
        p.start()
        self.addCleanup(p.stop)
        ad.devin_catalog(refresh=True, run=fake_run(out=catalog_json()))

    def allowed(self, a, s):
        p, _, _ = self.budget.posture(a, s)
        return p, self.budget.allowed(a, p, s)

    def test_off_never_parks(self):
        a = adapter_with(budget__mode='off')
        p, r = self.allowed(a, sig(seven=95, elapsed=95, five=95))
        self.assertEqual(p, 'OFF')
        self.assertIs(self.session.limits(a, 'OFF')[2], False)
        self.assertIn('opus_implement', r['build'])
        self.assertIsNone(self.budget.misfit(a, p, sig(five=95), 'opus_implement'))

    def test_ticked_opus_on_pace(self):
        a = adapter_with(budget__overrides__opus_implement=True)
        p, r = self.allowed(a, sig(five=20))
        self.assertEqual(p, 'ON PACE')
        self.assertIn('opus_implement', r['build'])
        _, r = self.allowed(a, sig(five=80))
        self.assertNotIn('opus_implement', r['build'])
        _, r = self.allowed(adapter_with(), sig(five=20))
        self.assertNotIn('opus_implement', r['build'])

    def test_ticked_review_joins_its_kind(self):
        a = adapter_with(budget__overrides__opus_review=True)
        p, r = self.allowed(a, sig(seven=95, elapsed=95))
        self.assertEqual(p, 'CRITICAL')
        self.assertIn('opus_review', r['review'])
        self.assertNotIn('opus_review', r['build'])

    def test_default_builder_first(self):
        a = adapter_with(routing__default_builder='sonnet')
        self.assertEqual(self.allowed(a, sig())[1]['build'][0], 'sonnet_implement')
        a = adapter_with(routing__default_builder='sonnet', budget__overrides__sonnet_implement=False)
        self.assertNotIn('sonnet_implement', self.allowed(a, sig())[1]['build'])

    def test_paid_devin_dropped_when_exhausted(self):
        self.devin_state = {'pct': 'exhausted'}
        a = adapter_with(devin__model='gpt-astra')
        self.assertNotIn('devin_swe2', self.allowed(a, sig())[1]['build'])
        a = adapter_with(devin__model='swe-2-high')
        self.assertIn('devin_swe2', self.allowed(a, sig())[1]['build'])

    def test_summary_says_budget_off(self):
        a = adapter_with(budget__mode='off')
        with mock.patch.object(self.budget, 'signals', return_value=sig(five=95)):
            self.assertIn('posture OFF (budget off)', self.budget.summary(a)['line'])


class RouteRowOff(Repo):
    def test_route_row_off(self):
        import budget
        self.row('SET budget.mode="off"')
        a, _ = ad.load(self.repo, '1.1')
        with mock.patch.object(budget, 'signals', return_value=sig(seven=95, elapsed=95, five=95)), \
                mock.patch.object(budget, 'spend', return_value=None), \
                mock.patch.object(budget, 'questions', return_value=[]):
            quiet(budget.route_row, a, '1.1', '7', 'opus_implement')
        last = open(self.f).read().strip().splitlines()[-1]
        self.assertIn('posture=OFF', last)
        self.assertNotIn('offposture', last)


class Callers(Repo):
    """Scripts given --release read the release's SET rows."""
    def test_status_json_lists_release_settings(self):
        import status
        with mock.patch.object(status, 'devin_procs', return_value=[]):
            self.assertEqual(status.as_json(*ad.load(self.repo, '1.1'), '1.1')['settings'], {})
            self.row('SET budget.mode="off"')
            j = status.as_json(*ad.load(self.repo, '1.1'), '1.1')
        self.assertEqual(j['settings'], {'budget.mode': 'off'})
        self.assertEqual(j['posture'], 'OFF')

    def test_status_main_loads_the_release(self):
        import status
        self.row('SET budget.mode="off"')
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['status.py', self.repo, '--release', '1.1', '--json']), \
                mock.patch.object(status, 'devin_procs', return_value=[]), redirect_stdout(out):
            status.main()
        self.assertEqual(json.loads(out.getvalue())['posture'], 'OFF')

    def test_status_paid_flag_follows_the_catalog(self):
        import status
        procs = [(1, '/w/proj-7', '/w/7.log', 'swe-2-high'), (2, '/w/proj-8', '/w/8.log', 'gpt-astra')]
        with mock.patch.object(status, 'devin_procs', return_value=procs), \
                mock.patch.object(status, 'elapsed', return_value=1), \
                mock.patch.object(ad, 'devin_catalog', return_value={'swe-2-high': {'tier': 'Free'}}):
            j = status.as_json(*ad.load(self.repo, '1.1'), '1.1')
        self.assertEqual([d['paid'] for d in j['devin']], [False, True])

    def test_chain_uses_release_model(self):
        import chain
        self.row('SET devin.model="gpt-astra"')
        wt = ad.worktree_path(ad.load(self.repo)[0], '7')
        os.makedirs(wt)
        bdir = os.path.join(self.rel, 'briefs')
        os.makedirs(bdir)
        open(os.path.join(bdir, '7.md'), 'w').write('brief')
        calls, real_run = [], subprocess.run

        def run(cmd, **kw):
            if cmd[:1] != ['devin']:
                return real_run(cmd, **kw)
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)
        r, w = os.pipe()
        self.addCleanup(os.close, r)
        argv = ['chain.py', self.repo, '--release', '1.1', '--worker', str(w), '7=7.md']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(chain.subprocess, 'run', side_effect=run), \
                mock.patch.object(chain, 'wait_for_slot'), redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()):
            chain.main()
        os.close(w)
        launch = next(c for c in calls if c[:1] == ['devin'])
        self.assertEqual(launch[launch.index('--model') + 1], 'gpt-astra')

    def test_session_main_loads_the_release(self):
        import session, budget
        self.row('SET budget.mode="off"')
        seen = {}
        real = budget.summary

        def summary(a):
            seen['mode'] = a['budget']['mode']
            return real(a)
        t = os.path.join(self.tmp.name, 't.jsonl')
        open(t, 'w').write('')
        with mock.patch.object(sys, 'argv', ['session.py', self.repo, '--release', '1.1']), \
                mock.patch.object(session, 'transcript', return_value=t), \
                mock.patch.object(budget, 'summary', side_effect=summary), redirect_stdout(io.StringIO()):
            try:
                session.main()
            except SystemExit:
                pass
        self.assertEqual(seen['mode'], 'off')


class SettingsCli(Repo):
    adapter = {}

    def setUp(self):
        super().setUp()
        import settings
        self.settings = settings
        self.ctmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.ctmp.cleanup)
        p = mock.patch.object(ad, 'DEVIN_CATALOG', os.path.join(self.ctmp.name, 'devin-models.json'))
        p.start()
        self.addCleanup(p.stop)
        ad.devin_catalog(refresh=True, run=fake_run(out=catalog_json()))

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                self.settings.main(list(args))
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int) and e.code:
                    err.write(str(e.code))
        return code, out.getvalue(), err.getvalue()

    def sets(self):
        return ad.release_sets(self.f)

    def commit_all(self):
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'init')

    def test_show_json_groups(self):
        code, out, _ = self.cli('show', self.repo, '--release', '1.1', '--json')
        self.assertEqual(code, 0)
        j = json.loads(out)
        self.assertEqual([g['name'] for g in j['groups']],
                         ['WHO DOES THE WORK', 'HOW HARD TO SPEND', 'WHEN TO HAND OFF'])
        self.assertEqual(j['preset'], 'balanced')
        self.assertEqual(j['release'], '1.1')
        knobs = {k['key']: k for g in j['groups'] for k in g['knobs']}
        self.assertEqual(knobs['budget.mode']['source'], 'default')
        self.assertEqual(knobs['devin.model']['choices'][0]['value'], 'swe-2-high')
        self.assertIn('frugal', j['presets'])
        code, out, _ = self.cli('show', self.repo)
        self.assertIn('WHO DOES THE WORK', out)
        self.assertIn('resume costs ~100k', out)

    def test_set_release_row(self):
        code, out, _ = self.cli('set', self.repo, '--release', '1.1', 'budget.overrides.opus_implement=true')
        self.assertEqual(code, 0)
        self.assertEqual(self.sets(), {'budget.overrides.opus_implement': True})
        self.assertIn('SET budget.overrides.opus_implement=true', open(self.f).read())
        self.assertIn('Opus', out)
        self.assertIn('release 1.1', out)

    def test_release_true_over_repo_false_says_so(self):
        self.write_adapter({'budget': {'overrides': {'opus_implement': False}}})
        _, out, _ = self.cli('set', self.repo, '--release', '1.1', 'budget.overrides.opus_implement=true')
        self.assertIn('the repo has it off', out)

    def test_budget_off_warns(self):
        _, out, _ = self.cli('set', self.repo, '--release', '1.1', 'budget.mode=off')
        self.assertEqual(self.sets(), {'budget.mode': 'off'})
        self.assertIn('may use up your 5-hour and 7-day windows', out)

    def test_set_unknown_key_exit_2(self):
        code, _, err = self.cli('set', self.repo, '--release', '1.1', 'budget.nope=1')
        self.assertEqual(code, 2)
        self.assertIn('budget.mode', err)
        code, _, err = self.cli('set', self.repo, '--release', '1.1', 'routing.default_builder=gpt')
        self.assertEqual(code, 2)
        self.assertIn('sonnet', err)
        self.assertEqual(self.sets(), {})

    def test_set_bad_limits_exit_2(self):
        code, _, err = self.cli('set', self.repo, '--release', '1.1', 'session_limits.soft_tokens=700000')
        self.assertEqual(code, 2)
        self.assertIn('soft', err)
        code, _, _ = self.cli('set', self.repo, '--release', '1.1', 'session_limits.soft_tokens=600000',
                              'session_limits.hard_tokens=800000')
        self.assertEqual(code, 0)

    def test_no_release_folder_refused(self):
        code, _, err = self.cli('set', self.repo, '--release', '9.9', 'budget.mode=off')
        self.assertEqual(code, 1)
        self.assertIn('no release folder', err)

    def test_preset_frugal_release_then_balanced_clears(self):
        code, out, _ = self.cli('preset', self.repo, '--release', '1.1', 'frugal')
        self.assertEqual(code, 0)
        self.assertEqual(self.sets(), ad.PRESETS['frugal'])
        j = json.loads(self.cli('show', self.repo, '--release', '1.1', '--json')[1])
        self.assertEqual(j['preset'], 'frugal')
        code, _, _ = self.cli('preset', self.repo, '--release', '1.1', 'balanced')
        self.assertEqual(self.sets(), {})
        j = json.loads(self.cli('show', self.repo, '--release', '1.1', '--json')[1])
        self.assertEqual(j['preset'], 'balanced')

    def test_repo_scope_commits_on_chore_branch(self):
        self.write_adapter({'main_branch': 'main', 'gates': []})
        self.commit_all()
        code, out, err = self.cli('set', self.repo, '--repo', 'budget.mode=off')
        self.assertEqual(code, 0, err)
        d = json.load(open(os.path.join(self.repo, '.claude', 'coordinate.json')))
        self.assertEqual(list(d), ['main_branch', 'gates', 'budget'])
        self.assertEqual(d['budget'], {'mode': 'off'})
        log = subprocess.run(['git', '-C', self.repo, 'log', '--merges', '--format=%s'],
                             capture_output=True, text=True).stdout
        self.assertIn('chore/settings-', log)
        self.assertIn('pushed? no', out)
        self.assertEqual(subprocess.run(['git', '-C', self.repo, 'status', '--porcelain'],
                                        capture_output=True, text=True).stdout, '')

    def test_repo_scope_refuses_dirty_main(self):
        self.commit_all()
        open(os.path.join(self.repo, 'stray.txt'), 'w').write('x')
        before = open(os.path.join(self.repo, '.claude', 'coordinate.json')).read()
        code, _, err = self.cli('set', self.repo, '--repo', 'budget.mode=off')
        self.assertEqual(code, 1)
        self.assertIn('dirty', err)
        self.assertEqual(open(os.path.join(self.repo, '.claude', 'coordinate.json')).read(), before)

    def test_repo_scope_untracked_writes_in_place(self):
        code, _, err = self.cli('set', self.repo, '--repo', 'session_limits.hard_tokens=700000')
        self.assertEqual(code, 0, err)
        d = json.load(open(os.path.join(self.repo, '.claude', 'coordinate.json')))
        self.assertEqual(d['session_limits']['hard_tokens'], 700000)

    def test_set_paid_devin_model_notes_free(self):
        _, out, _ = self.cli('set', self.repo, '--release', '1.1', 'devin.model=gemini-4-argon-high')
        self.assertEqual(self.sets(), {'devin.model': 'gemini-4-argon-high'})
        self.assertIn('spends the Devin quota', out)
        self.assertIn('free: swe-2-high', out)


class PreflightInit(CatalogCase):
    def setUp(self):
        super().setUp()
        import preflight
        self.pf = preflight

    def checks(self, a, which='/usr/bin/devin', **run):
        return self.pf.devin_checks(a, which=lambda _: which, run=fake_run(**run))

    def test_no_devin_not_fatal_with_sonnet_builder(self):
        fails, warns = self.checks(adapter_with(routing__default_builder='sonnet'), which=None,
                                   exc=FileNotFoundError())
        self.assertEqual(fails, [])
        self.assertTrue(any('builds go to sonnet' in w for w in warns), warns)
        fails, _ = self.checks(adapter_with(), which=None, exc=FileNotFoundError())
        self.assertTrue(any('devin CLI not on PATH' in f for f in fails))

    def test_paid_adapter_model_is_a_warning(self):
        fails, warns = self.checks(adapter_with(devin__model='gemini-4-argon-high'), out=catalog_json())
        self.assertEqual(fails, [])
        self.assertTrue(any('is paid ($2 / 1M Input' in w and 'Free now: swe-2-high' in w for w in warns), warns)

    def test_preflight_warns_when_free_model_turns_paid(self):
        self.refresh(out=catalog_json())
        _, warns = self.checks(adapter_with(), out=catalog_json('Low cost'))
        hit = [w for w in warns if 'no longer free' in w]
        self.assertEqual(len(hit), 1, warns)
        self.assertIn('swe-2-high', hit[0])
        self.assertIn('Free now: swe-2-flash-high', hit[0])
        _, warns = self.checks(adapter_with(), out=catalog_json('Low cost'))
        self.assertFalse(any('no longer free' in w for w in warns))

    def test_outdated_auto_mode_line_warns(self):
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, 'proj')
            os.makedirs(os.path.join(main, '.claude'))
            old = 'in proj, launching `devin --model swe-2-high|swe-2-medium` in proj-* worktrees'
            json.dump({'autoMode': {'environment': [old]}}, open(os.path.join(main, '.claude', 'settings.json'), 'w'))
            w = self.pf.auto_mode_warning(main, home=d)
            self.assertIn('re-paste it once', w)
            self.assertIn('coordinate.json', w)

    def test_chain_quota_out_suggests_free(self):
        import chain
        self.refresh(out=catalog_json())
        log = os.path.join(self.ctmp.name, '7.log')
        with open(log, 'w') as fh:
            fh.write('... Error: out of quota for this billing period\n')
        with mock.patch.object(chain.budget, '_save'), mock.patch.object(chain.budget, '_load', return_value={}):
            msg = chain.quota_out(log, 'gpt-astra', '/w/proj', '1.1', run=fake_run(out=catalog_json()))
        self.assertIn('Devin quota ran out on gpt-astra', msg)
        self.assertIn('Free now: swe-2-high, swe-2-flash-high', msg)
        self.assertIn('settings.py set /w/proj --release 1.1 devin.model=swe-2-high', msg)
        with open(log, 'w') as fh:
            fh.write('all good\n')
        self.assertIsNone(chain.quota_out(log, 'gpt-astra', '/w/proj', '1.1', run=fake_run(out=catalog_json())))

    def test_init_without_devin_drafts_sonnet(self):
        import init
        with tempfile.TemporaryDirectory() as d:
            git(d, 'init', '-q')
            out = io.StringIO()
            with mock.patch.object(sys, 'argv', ['init.py', d]), mock.patch.object(init.shutil, 'which', return_value=None), \
                    redirect_stdout(out):
                init.main()
            draft = json.load(open(os.path.join(d, '.claude', 'coordinate.json')))
            self.assertEqual(draft['routing'], {'default_builder': 'sonnet'})
            self.assertIn('Default implementer: sonnet (change with /coordinate settings)', out.getvalue())
            self.assertIn('7. ', out.getvalue())
            self.assertNotIn('8. ', out.getvalue())


class ReviewFixes(Repo):
    """The final review's findings, each reproduced."""
    adapter = {}

    def setUp(self):
        super().setUp()
        import budget, settings
        self.budget, self.settings = budget, settings
        self.ctmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.ctmp.cleanup)
        for obj, name, val in ((ad, 'DEVIN_CATALOG', os.path.join(self.ctmp.name, 'c.json')),):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)
        for name, val in (('spend', None), ('questions', [])):
            p = mock.patch.object(budget, name, return_value=val)
            p.start()
            self.addCleanup(p.stop)

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            self.settings.main(list(args))
        return out.getvalue()

    def show(self):
        return json.loads(self.cli('show', self.repo, '--release', '1.1', '--json'))

    def test_budget_main_reads_the_release(self):
        self.write_adapter({'budget': {'mode': 'off'}})
        self.row('SET budget.mode="auto"')
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['budget.py', self.repo, '--release', '1.1']), \
                mock.patch.object(self.budget, 'signals', return_value=sig()), redirect_stdout(out):
            self.budget.main()
        self.assertIn('posture ON PACE', out.getvalue())

    def test_default_builder_never_overrides_the_posture(self):
        a = adapter_with(routing__default_builder='opus')
        with mock.patch.object(self.budget, '_load', return_value={}):
            s = sig(seven=95, elapsed=95)
            p, _, _ = self.budget.posture(a, s)
            self.assertEqual(p, 'CRITICAL')
            self.assertNotIn('opus_implement', self.budget.allowed(a, p, s)['build'])
            s = sig(seven=10, elapsed=50, five=20)
            p, _, _ = self.budget.posture(a, s)
            self.assertEqual(self.budget.allowed(a, p, s)['build'][0], 'opus_implement')

    def test_release_preset_over_a_tuned_repo_is_the_preset(self):
        self.write_adapter({'budget': {'mode': 'off'}, 'session_limits': {'hard_tokens': 700000}})
        self.cli('preset', self.repo, '--release', '1.1', 'frugal')
        self.assertEqual(self.show()['preset'], 'frugal')
        self.cli('preset', self.repo, '--release', '1.1', 'balanced')
        j = self.show()
        self.assertEqual(j['preset'], 'balanced')
        knobs = {k['key']: k['value'] for g in j['groups'] for k in g['knobs']}
        self.assertEqual(knobs['budget.mode'], 'auto')

    def test_repo_preset_keeps_who_builds_and_the_models(self):
        self.write_adapter({'routing': {'default_builder': 'sonnet'}, 'devin': {'model': 'swe-2-medium'}})
        self.assertEqual(self.show()['preset'], 'balanced')
        self.cli('preset', self.repo, '--repo', 'frugal')
        d = json.load(open(os.path.join(self.repo, '.claude', 'coordinate.json')))
        self.assertEqual(d['routing'], {'default_builder': 'sonnet'})
        self.assertEqual(d['devin']['model'], 'swe-2-medium')
        self.cli('preset', self.repo, '--repo', 'balanced')
        d = json.load(open(os.path.join(self.repo, '.claude', 'coordinate.json')))
        self.assertEqual(d['routing'], {'default_builder': 'sonnet'})
        self.assertEqual(self.show()['preset'], 'balanced')

    def test_frugal_builds_on_swe2_only(self):
        self.assertIs(ad.PRESETS['frugal']['budget.overrides.devin_fusion'], False)

    def test_a_wrong_type_row_is_skipped(self):
        self.row('SET budget.five_hour_fit_pct="85"')
        self.row('SET budget=1')
        self.row('SET budget.overrides.opus_implement=null')
        err = io.StringIO()
        with redirect_stderr(err):
            a, _ = ad.load(self.repo, '1.1')
        self.assertEqual(a['budget']['five_hour_fit_pct'], 85)
        self.assertIsInstance(a['budget'], dict)
        self.assertEqual(err.getvalue().count('skipped'), 2)


class SkillText(unittest.TestCase):
    def test_skill_mentions_settings(self):
        p = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'SKILL.md')
        text = open(p).read()
        front = text.split('---')[1]
        self.assertIn('/coordinate settings', front)
        section = text.split('## Settings', 1)[1].split('\n## ', 1)[0]
        self.assertIn('settings.py show', section)
        self.assertIn('--json', section)
        self.assertLessEqual(len(section.strip().splitlines()), 30)


if __name__ == '__main__':
    unittest.main()
