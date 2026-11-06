"""Shared helpers: find the repo's main checkout and load its coordinate adapter.

The adapter is `<main>/.claude/coordinate.json`, else `~/.config/coordinate/<main-basename>.json`.
See references/adapter.md for the keys. Project state (release folders, logs, lessons) defaults to
`<main>/.coordinate/`, which the repo gitignores; relative paths in the adapter resolve against
the main checkout. A release begun before 2.12.0 keeps its one-file ledger in `ledger_dir` and its
briefs in `briefs_dir/<R>`; every helper here still finds them.
"""
import json, os, subprocess, sys, time

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
               'pace_floor_pct': 25, 'overrides': {}},
    'devin': {'model': 'swe-2-high',
              'fusion_model': 'fusion-claude-opus-5-5-high-sidekick-swe-2-medium'},
}
PATH_KEYS = ('release_dir', 'ledger_dir', 'briefs_dir', 'log_dir', 'lessons_file')
# The owner, 2026-10-14: every Devin build runs on SWE-2 medium or high, named on the command line.
# Devin's own default is whatever its config says (swe-2-max on their machine), so it never decides.
DEVIN_BUILD_MODELS = ('swe-2-high', 'swe-2-medium')
# Machine-wide state shared by every repo: the status line's usage.json, the Devin paid quota.
USER_STATE = os.path.expanduser('~/.claude/coordinate')


AUTO_MODE_FILES = ('{home}/.claude/settings.json', '{home}/.claude/settings.local.json',
                   '{main}/.claude/settings.json', '{main}/.claude/settings.local.json')


def auto_mode_named(main, home=None):
    """True when an `autoMode.environment` entry in the user or project settings names this repo.
    Without one, auto mode's classifier denied the coordinator's launches as "Auto-Mode Bypass"."""
    name, home = os.path.basename(main), home or os.path.expanduser('~')
    for f in AUTO_MODE_FILES:
        try:
            lines = json.load(open(f.format(home=home, main=main))).get('autoMode', {}).get('environment', [])
        except (OSError, ValueError, AttributeError):
            continue
        if any(name in l for l in lines if isinstance(l, str)):
            return True
    return False


def auto_mode_line(main):
    """The `autoMode.environment` entry for the user's settings.json; a session cannot add it."""
    name = os.path.basename(main)
    return (f'**Coordinator workflow (authorized by the owner)**: in {name}, the coordinator session launching '
            f'`devin -p --permission-mode dangerous --model swe-2-high|swe-2-medium [-r <session>] '
            f'--prompt-file <briefs>/<task>.md` inside this repo\'s sibling worktrees '
            f'(`{main}-*`), and launching Claude implementer or review subagents with the Agent tool '
            f'(opus/sonnet/haiku) on brief files under `.coordinate/releases/*/briefs/`, is the sanctioned, '
            f'user-approved workflow. It is not Create Unsafe Agents and not Auto-Mode Bypass. '
            f'Pushes stay the owner\'s.')


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


def load(path='.'):
    """Return (adapter dict with defaults filled, main checkout path)."""
    main = main_checkout(os.path.abspath(path))
    p = adapter_path(main)
    if not os.path.exists(p):
        die(f'No coordinate adapter for {main}.\nRun init.py {main} (see references/adapter.md).', 2)
    a = json.load(open(p))
    a['_obsolete'] = [k for k in ('context_tokens', 'merges') if k in a.get('session_limits', {})]
    a['_obsolete'] += ['review.quota_threshold_pct'] if 'review' in a else []
    for k, v in DEFAULTS.items():
        if isinstance(v, dict) and k != 'install_on_change':  # a whole map: `{}` turns it off
            a[k] = {**v, **(a.get(k) or {})}
        else:
            a.setdefault(k, v)
    for k in PATH_KEYS:
        a[k] = os.path.normpath(os.path.join(main, os.path.expanduser(a[k])))
    a['_main'] = main
    a['_path'] = p
    return a, main


def devin_model(a, fusion=False):
    """The --model for a Devin launch: the adapter's SWE-2 build model, or its Fusion model."""
    if fusion:
        m = a['devin']['fusion_model']
        if not m.startswith('fusion-'):
            die(f'adapter devin.fusion_model {m!r} is not a Fusion model')
        return m
    m = a['devin']['model']
    if m not in DEVIN_BUILD_MODELS:
        die(f'adapter devin.model {m!r}: Devin builds run on {" or ".join(DEVIN_BUILD_MODELS)} only')
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


def now():
    return time.strftime('%m-%d %H:%M')
