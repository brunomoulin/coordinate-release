"""Shared helpers: find the repo's main checkout and load its coordinate adapter.

The adapter is `<main>/.claude/coordinate.json`, else `~/.config/coordinate/<main-basename>.json`.
See references/adapter.md for the keys. Project state (release folders, logs, lessons) defaults to
`<main>/.coordinate/`, which the repo gitignores; relative paths in the adapter resolve against
the main checkout. A release begun before 2.12.0 keeps its one-file ledger in `ledger_dir` and its
briefs in `briefs_dir/<R>`; every helper here still finds them.
"""
import copy, json, os, re, subprocess, sys, time

DEFAULTS = {
    'main_branch': 'main',
    'worktree_parent': '..',
    'env_files': [],
    'worktree_setup': [],
    'path_prefix': '',
    'gates': [],
    'gate_grep': 'Tests|FAIL|error|problems|built in',
    'db_test': None,
    'db_snapshot': None,
    'append_only': [],
    'handoff': None,
    'handoff_agent': 'Claude (coordinator)',
    'owner_marker': None,
    'owner_name': None,
    'closeout_skill': None,
    'dev_ports': [],
    'eyeball_build': None,
    'eyeball_howto': None,
    'eyeball_verify': {'url': None, 'accounts_file': None, 'rules': []},
    'release_dir': '.coordinate/releases',
    'ledger_dir': '.coordinate/ledgers',
    'briefs_dir': '.coordinate/briefs',
    'log_dir': '.coordinate/logs',
    'lessons_file': '.coordinate/lessons.md',
    'ledger_archive': None,
    'tracker': None,
    'tasks_file': None,
    'live_caps': {'now': 60, 'decisions': 60, 'eyeball': 40, 'lessons': 80},
    'test_slots': 1,
    'install_on_change': {'package-lock.json': 'npm install --no-audit --no-fund'},
    'concurrency': {'devin': 3, 'sonnet': 2, 'opus_review': 1},
    'session_limits': {'soft_tokens': 450000, 'hard_tokens': 650000, 'tight_tokens': 400000,
                       'closeout_tokens': 60000, 'merges_warn': 10},
    'budget': {'surplus_pace': 0.7, 'tight_pace': 1.1, 'five_hour_fit_pct': 85,
               'tight_headroom': 0.75, 'build_cost_5h': {'haiku': 3, 'sonnet': 10, 'opus': 20},
               'build_cost_7d': {'haiku': 0.5, 'sonnet': 2, 'opus': 5},
               'critical_pct': 90, 'surplus_reset_hours': 24, 'surplus_reset_pct': 70,
               'pace_floor_pct': 25, 'overrides': {}, 'mode': 'auto'},
    'devin': {'model': 'swe-2-high',
              'fusion_model': 'fusion-claude-opus-5-5-high-sidekick-swe-2-medium'},
    'routing': {'default_builder': 'devin'},
}
# Presets for /coordinate settings: dotted keys over DEFAULTS. The only place a preset is defined.
CLAUDE_ROUTES = ('haiku_implement', 'sonnet_implement', 'opus_implement', 'opus_review', 'sonnet_review',
                 'sonnet_critique')
PRESETS = {
    'balanced': {},
    'frugal': {**{f'budget.overrides.{r}': False for r in CLAUDE_ROUTES + ('sonnet_eyeball', 'devin_fusion')},
               'budget.five_hour_fit_pct': 60,
               'session_limits.soft_tokens': 350000, 'session_limits.hard_tokens': 500000},
    'all-out': {**{f'budget.overrides.{r}': True for r in CLAUDE_ROUTES},
                'budget.mode': 'off',
                'session_limits.soft_tokens': 600000, 'session_limits.hard_tokens': 800000},
}
PATH_KEYS = ('release_dir', 'ledger_dir', 'briefs_dir', 'log_dir', 'lessons_file')
# The owner, 2026-10-14: every Devin build runs on SWE-2 medium or high, named on the command line.
# Devin's own default is whatever its config says (swe-2-max on their machine), so it never decides.
DEVIN_BUILD_MODELS = ('swe-2-high', 'swe-2-medium')
# Machine-wide state shared by every repo: the status line's usage.json, the Devin paid quota.
USER_STATE = os.path.expanduser('~/.claude/coordinate')
# The live Devin catalog's cache (devin_catalog): {"at": epoch, "models": {uid: {"tier", "summary"}}}.
DEVIN_CATALOG = USER_STATE + '/devin-models.json'


def claude_dir(home=None):
    """Claude Code's profile folder: CLAUDE_CONFIG_DIR when set (a second profile runs with its own
    settings and transcripts), else ~/.claude. `home` (tests) means <home>/.claude."""
    if home:
        return os.path.join(home, '.claude')
    return os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')


AUTO_MODE_FILES = ('{claude}/settings.json', '{claude}/settings.local.json',
                   '{main}/.claude/settings.json', '{main}/.claude/settings.local.json')
# The one autoMode line for every repo with an adapter (auto_mode_line_generic).
GENERIC_SCOPE = 'any repo with a committed `.claude/coordinate.json`'


def auto_mode_lines(main, home=None):
    """Every `autoMode.environment` entry in the profile's and the project's settings."""
    out = []
    for f in AUTO_MODE_FILES:
        try:
            lines = json.load(open(f.format(claude=claude_dir(home), main=main))).get('autoMode', {}).get('environment', [])
        except (OSError, ValueError, AttributeError):
            continue
        out += [l for l in lines if isinstance(l, str)]
    return out


def auto_mode_covers(line, main):
    """The entry names this repo, or is the coordinator line for every repo with an adapter."""
    return os.path.basename(main) in line or ('Coordinator workflow' in line and GENERIC_SCOPE in line)


def auto_mode_named(main, home=None):
    """True when an `autoMode.environment` entry covers this repo. Without one, auto mode's
    classifier denied the coordinator's launches as "Auto-Mode Bypass"."""
    return any(auto_mode_covers(l, main) for l in auto_mode_lines(main, home))


OLD_AUTO_MODEL = 'swe-2-high|swe-2-medium'


def auto_mode_outdated(main, home=None):
    """True when an entry covering this repo is the pre-2.33.0 text, which authorized SWE-2 only:
    a model picked with /coordinate settings would be denied."""
    return any(auto_mode_covers(l, main) and OLD_AUTO_MODEL in l for l in auto_mode_lines(main, home))


def _auto_mode_text(where, worktrees):
    return (f'**Coordinator workflow (authorized by the owner)**: in {where}, the coordinator session launching '
            f'`devin -p --permission-mode dangerous --model <any model `devin models list` shows for this '
            f'account, as set in .claude/coordinate.json or by /coordinate settings for a release> [-r <session>] '
            f'--prompt-file <briefs>/<task>.md` inside {worktrees}, and launching Claude implementer or review '
            f'subagents with the Agent tool (opus/sonnet/haiku) on brief files under '
            f'`.coordinate/releases/*/briefs/`, is the sanctioned, user-approved workflow. It is not Create '
            f'Unsafe Agents and not Auto-Mode Bypass. Pushes stay the owner\'s.')


def auto_mode_line(main):
    """The `autoMode.environment` entry for this repo; a session cannot add it."""
    return _auto_mode_text(os.path.basename(main), f'this repo\'s sibling worktrees (`{main}-*`)')


def auto_mode_line_generic():
    """The one entry for every repo with a committed adapter, instead of one per repo."""
    return _auto_mode_text(GENERIC_SCOPE, 'that repo\'s sibling worktrees (`<repo>-*`)')


def settings_file(home=None):
    """The profile's settings.json, for the lines that tell the owner where to paste."""
    return os.path.join(claude_dir(home), 'settings.json')


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def git(cwd, *args, check=True):
    r = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f'git {" ".join(args)} failed in {cwd}:\n{r.stderr.strip()}')
    return r.stdout.strip()


def main_checkout(path):
    """Any worktree (or the main checkout) -> the main checkout's absolute path."""
    common = git(path, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    return os.path.dirname(common)


def adapter_path(main):
    local = os.path.join(main, '.claude', 'coordinate.json')
    if os.path.exists(local):
        return local
    return os.path.expanduser(f'~/.config/coordinate/{os.path.basename(main)}.json')


# A release's settings: `SET <dotted.key>=<json value>` rows in its timeline (settings.py writes
# them). The pattern is ledger.ROW's, copied here because ledger imports this module.
ROW = re.compile(r'^\| (\d\d-\d\d \d\d:\d\d) \| ([^|]*) \| ([^|]*) \| (.*) \|$')
SET_ROW = re.compile(r'^SET ([a-z_.0-9-]+)=(.*)$')


def set_dotted(d, key, value):
    *parents, leaf = key.split('.')
    for k in parents:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    d[leaf] = value


def del_dotted(d, key):
    *parents, leaf = key.split('.')
    for k in parents:
        d = d.get(k)
        if not isinstance(d, dict):
            return
    d.pop(leaf, None)


def leaves(d, prefix=''):
    """Dotted keys of a nested dict's non-dict values."""
    for k, v in d.items():
        if isinstance(v, dict) and v:
            yield from leaves(v, f'{prefix}{k}.')
        else:
            yield f'{prefix}{k}'


def release_sets(ledger_path):
    """{dotted key: value} from a timeline's SET rows; the latest row per key wins and `=default`
    drops the key. A row whose value is not JSON is skipped with a warning, never fatal."""
    out = {}
    try:
        lines = open(ledger_path).read().splitlines()
    except OSError:
        return out
    for line in lines:
        m = ROW.match(line)
        s = m and SET_ROW.match(m.group(4).strip())
        if not s:
            continue
        key, raw = s.groups()
        if raw.strip() == 'default':
            out.pop(key, None)
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            print(f'skipped ledger row {m.group(1)} SET {key}={raw}: the value is not JSON '
                  f'(quote strings: {key}="{raw}")', file=sys.stderr)
            continue
        if (why := type_problem(key, value)):
            print(f'skipped ledger row {m.group(1)} SET {key}={raw}: {why}', file=sys.stderr)
            continue
        out[key] = value
    return out


def type_problem(key, value):
    """Why a SET value can't stand where DEFAULTS has that key, or None. A hand-edited row of the
    wrong type would otherwise crash every script that reads it."""
    d, parts = DEFAULTS, key.split('.')
    for i, k in enumerate(parts):
        if not isinstance(d, dict):
            return f'{".".join(parts[:i])} is not a map'
        if k not in d:
            if parts[:-1] == ['budget', 'overrides'] and i == len(parts) - 1:
                return None if value is None or isinstance(value, bool) else 'a route takes true, false or null'
            return None  # a key DEFAULTS does not know: the repo's own
        d = d[k]
    if d is None:
        return None
    ok = isinstance(value, dict) if isinstance(d, dict) else \
        isinstance(value, bool) if isinstance(d, bool) else \
        isinstance(value, (int, float)) and not isinstance(value, bool) if isinstance(d, (int, float)) else \
        isinstance(value, type(d))
    return None if ok else f'want a {type(d).__name__}, as the default {d!r}'


def load(path='.', release=None):
    """Return (adapter dict with defaults filled, main checkout path). With a release, its SET rows
    sit over the repo adapter, which sits over DEFAULTS. `a['_sources']` names where each dotted
    key set by the repo file or a release row comes from."""
    main = main_checkout(os.path.abspath(path))
    p = adapter_path(main)
    if not os.path.exists(p):
        die(f'No coordinate adapter for {main}.\nRun init.py {main} (see references/adapter.md).', 2)
    a = json.load(open(p))
    sources = {k: 'repo' for k in leaves(a)}
    a['_obsolete'] = [k for k in ('context_tokens', 'merges') if k in a.get('session_limits', {})]
    a['_obsolete'] += ['review.quota_threshold_pct'] if 'review' in a else []
    for k, v in copy.deepcopy(DEFAULTS).items():  # a copy: a release row must not edit DEFAULTS
        if isinstance(v, dict) and k != 'install_on_change':  # a whole map: `{}` turns it off
            a[k] = {**v, **(a.get(k) or {})}
        else:
            a.setdefault(k, v)
    if release:
        rel_dir = os.path.normpath(os.path.join(main, os.path.expanduser(a['release_dir'])))
        led_dir = os.path.normpath(os.path.join(main, os.path.expanduser(a['ledger_dir'])))
        f = ledger_file({'release_dir': rel_dir, 'ledger_dir': led_dir}, release)
        for key, value in release_sets(f).items():
            set_dotted(a, key, value)
            sources[key] = 'release'
    a['_sources'] = sources
    for k in PATH_KEYS:
        a[k] = os.path.normpath(os.path.join(main, os.path.expanduser(a[k])))
    a['_main'] = main
    a['_path'] = p
    return a, main


def devin_catalog(refresh=False, run=subprocess.run):
    """{model_uid: {'tier', 'summary'}} from `devin models list --format json`. With `refresh`, runs
    it and writes the cache; on any failure, and without `refresh`, reads the cache. No cache: SWE-2
    high and medium count as free (the assumption before 2.33.0)."""
    if refresh:
        try:
            r = run(['devin', 'models', 'list', '--format', 'json'], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                models = {}
                for fam in json.loads(r.stdout).get('families', []):
                    for v in fam.get('variants', []):
                        if v.get('model_uid'):
                            models[v['model_uid']] = {'tier': v.get('cost_tier'), 'summary': v.get('cost_summary')}
                if models:
                    os.makedirs(os.path.dirname(DEVIN_CATALOG), exist_ok=True)
                    json.dump({'at': int(time.time()), 'models': models}, open(DEVIN_CATALOG, 'w'), indent=1)
                    return models
        except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
            pass
    try:
        models = json.load(open(DEVIN_CATALOG))['models']
        if isinstance(models, dict) and models:
            return models
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {m: {'tier': 'Free', 'summary': None} for m in DEVIN_BUILD_MODELS}


def devin_cost(model, catalog=None):
    """'free' when the Devin catalog lists the model as Free; anything else spends the Devin quota."""
    cat = devin_catalog() if catalog is None else catalog
    return 'free' if (cat.get(model) or {}).get('tier') == 'Free' else 'paid'


def free_devin_models(catalog=None):
    cat = devin_catalog() if catalog is None else catalog
    free = sorted(m for m, v in cat.items() if (v or {}).get('tier') == 'Free')
    return (['swe-2-high'] if 'swe-2-high' in free else []) + [m for m in free if m != 'swe-2-high']


def devin_model(a, fusion=False):
    """The --model for a Devin launch: the adapter's build model, or its Fusion model. Any model id
    is accepted; a build model that isn't free gets a one-line note."""
    if fusion:
        return a['devin']['fusion_model']
    m = a['devin']['model']
    if devin_cost(m) == 'paid':
        print(f'note: Devin model {m} is paid: it spends the Devin quota', file=sys.stderr)
    return m


def worktree_path(a, task):
    parent = os.path.normpath(os.path.join(a['_main'], a['worktree_parent']))
    return os.path.join(parent, f"{os.path.basename(a['_main'])}-{task}")


def env(a):
    e = dict(os.environ)
    if a['path_prefix']:
        e['PATH'] = a['path_prefix'] + ':' + e['PATH']
    return e


def log_dir(a):
    os.makedirs(a['log_dir'], exist_ok=True)
    return a['log_dir']


def archive_path(a, release):
    """Where the close-out copies the ledger, relative to the repo; None when unset. A value ending
    in `/` is a folder and means `<folder>/<release>.md`."""
    v = a['ledger_archive']
    if not v:
        return None
    return v + f'{release}.md' if v.endswith('/') else v.format(release=release)


def release_path(a, release):
    return os.path.join(a['release_dir'], release)


def ledger_file(a, release):
    """The file holding the release's Timeline rows: `<release_dir>/<R>/timeline.md` (2.12.0 on);
    for a release begun before, its one-file ledger in ledger_dir, or `<R>/ledger.md` once that
    file moved into the release folder closed. A new release gets the folder."""
    d = release_path(a, release)
    for p in (os.path.join(d, 'timeline.md'), os.path.join(a['ledger_dir'], f'{release}.md'),
              os.path.join(d, 'ledger.md')):
        if os.path.exists(p):
            return p
    return os.path.join(d, 'timeline.md')


def in_folder(a, release):
    """True when the release lives in its folder (its briefs and eyeball checks are there too)."""
    return os.path.dirname(ledger_file(a, release)) == release_path(a, release)


def briefs_path(a, release):
    return os.path.join(release_path(a, release), 'briefs') if in_folder(a, release) \
        else os.path.join(a['briefs_dir'], release)


def newest_ledger(a):
    """The release whose ledger was written last: what `--release auto` means."""
    found = {}
    try:
        for f in os.listdir(a['ledger_dir']):
            if f.endswith('.md') and not f.endswith('.history.md'):
                found[f[:-3]] = os.path.join(a['ledger_dir'], f)
    except OSError:
        pass
    try:
        for r in os.listdir(a['release_dir']):
            for name in ('timeline.md', 'ledger.md'):
                p = os.path.join(a['release_dir'], r, name)
                if os.path.exists(p):
                    found[r] = p
                    break
    except OSError:
        pass
    if not found:
        return None
    return max(found, key=lambda r: os.path.getmtime(found[r]))


def opt(args, name, default=None):
    """Pop `name VALUE` from args."""
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


def resolve_release(a, release):
    """`auto` means the newest ledger's release."""
    return newest_ledger(a) if release == 'auto' else release


def load_release(path, release):
    """(adapter with the release's SET rows, main, release) for a script given `--release R|auto`."""
    a, main = load(path)
    release = resolve_release(a, release)
    if release:
        a, main = load(path, release)
    return a, main, release


def now():
    return time.strftime('%m-%d %H:%M')
