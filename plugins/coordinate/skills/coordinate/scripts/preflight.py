"""Setup check, run once at the start of every coordinator session. Read-only.

  preflight.py <repo>

FAIL lines stop the session until fixed (the owner fixes allow rules: a session cannot edit its own
settings). WARN and QUESTION lines go into the wave's question batch.
"""
import json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import budget

NEEDED_ALLOW = ['Bash(devin -p *)', 'Bash(devin list *)']
REQUIRED_KEYS = ['gates']


def allow_rules(main):
    found, files = set(), [f.format(claude=ad.claude_dir(), main=main) for f in ad.AUTO_MODE_FILES]
    for p in files:
        try:
            found |= set(json.load(open(p)).get('permissions', {}).get('allow', []))
        except (OSError, ValueError):
            pass
    return found


def allowed(rule, have):
    """A needed `Bash(<cmd> *)` rule is present, or a broader one covers it: `Bash(devin:*)`,
    `Bash(devin *)`, `Bash(*)`, `Bash` (the demo profile ran on `Bash(devin:*)` alone)."""
    if rule in have or 'Bash' in have or 'Bash(*)' in have:
        return True
    words = rule[len('Bash('):-len(' *)')].split()
    for n in range(1, len(words)):
        prefix = ' '.join(words[:n])
        if f'Bash({prefix}:*)' in have or f'Bash({prefix} *)' in have:
            return True
    return False


def inotify_limit():
    try:
        return int(open('/proc/sys/fs/inotify/max_user_watches').read())
    except (OSError, ValueError):
        return None


def devin_checks(a, which=shutil.which, run=subprocess.run):
    """(fails, warns) for Devin: the CLI, its config's default model, and the adapter model's cost
    from the live catalog (refreshed here, once per preflight)."""
    fails, warns = [], []
    builder = (a.get('routing') or {}).get('default_builder', 'devin')
    if not which('devin'):
        if builder == 'devin':
            fails.append('devin CLI not on PATH (or /coordinate settings: another default implementer)')
        else:
            warns.append(f'devin CLI not on PATH: builds go to {builder}')
        return fails, warns
    try:
        c = json.load(open(os.path.expanduser('~/.config/devin/config.json')))
        m = (c.get('agent') or {}).get('model') or c.get('model', '')
        if m != a['devin']['model']:
            warns.append(f'Devin config default model is {m}: every launch must pass --model '
                         f'{a["devin"]["model"]}, resumes included')
    except (OSError, ValueError):
        pass
    try:
        prev = json.load(open(ad.DEVIN_CATALOG))['models']
    except (OSError, ValueError, KeyError, TypeError):
        prev = {}
    cat = ad.devin_catalog(refresh=True, run=run)
    m = a['devin']['model']
    if ad.devin_cost(m, cat) == 'paid':
        summary = (cat.get(m) or {}).get('summary') or 'not in the Devin catalog'
        free = ', '.join(ad.free_devin_models(cat)) or 'none listed'
        if (prev.get(m) or {}).get('tier') == 'Free':
            warns.append(f'{m} is no longer free ({summary}). Free now: {free}. /coordinate settings to switch')
        else:
            warns.append(f'Devin model {m} is paid ({summary}): builds spend the Devin quota. Free now: {free}')
    return fails, warns


def auto_mode_warning(main, home=None):
    if ad.auto_mode_outdated(main, home):
        return f'the autoMode line names SWE-2 only: re-paste it once: {ad.auto_mode_line(main)}'
    if ad.auto_mode_named(main, home):
        return None
    return (f'no `autoMode.environment` entry names {os.path.basename(main)}: auto mode may deny the '
            f'launches as "Auto-Mode Bypass". The owner adds this line to {ad.settings_file(home)} '
            f'(autoMode.environment): {ad.auto_mode_line(main)} (or, once for every repo with an adapter: '
            f'{ad.auto_mode_line_generic()})')


def archive_problem(a):
    """A fixed archive file name would make every release overwrite the last."""
    v = a.get('ledger_archive')
    if v and not v.endswith('/') and '{release}' not in v:
        return (f'adapter ledger_archive "{v}" has no {{release}}: use "{v.rsplit("/", 1)[0]}/{{release}}.md" '
                f'or a folder ending in "/"')
    return None


def untracked(main):
    """Untracked paths on main (folders as `dir/`): merge.py refuses to merge into a dirty checkout."""
    out = ad.git(main, 'status', '--porcelain', '--untracked-files=normal', check=False).splitlines()
    return [l[3:] for l in out if l.startswith('??')]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    fails, warns = [], []
    a, main_ = ad.load(sys.argv[1])
    print(f'adapter: {a["_path"]}')
    for k in REQUIRED_KEYS:
        if not a.get(k):
            fails.append(f'adapter key "{k}" missing (references/adapter.md)')
    if a['_obsolete']:
        warns.append(f'v1 adapter keys ignored: {", ".join(a["_obsolete"])}. Limits are now '
                     f'session_limits.soft_tokens/hard_tokens and the budget posture (references/adapter.md)')
    for k in ('release_dir', 'ledger_dir', 'briefs_dir', 'log_dir'):
        p = a[k]
        if p.startswith(main_ + os.sep) and subprocess.run(
                ['git', '-C', main_, 'check-ignore', '-q', os.path.relpath(p, main_) + '/x']).returncode != 0:
            fails.append(f'{os.path.relpath(p, main_)} is inside the repo but not gitignored: add `.coordinate/` '
                         f'to .gitignore (a tracked ledger dirties main and merge.py refuses every merge)')
    p = archive_problem(a)
    if p:
        fails.append(p)
    if w := auto_mode_warning(main_):
        warns.append(w)
    have = allow_rules(main_)
    missing = [r for r in NEEDED_ALLOW if not allowed(r, have)]
    if missing:
        local = os.path.join(ad.claude_dir(), 'settings.local.json')
        fails.append(f'allow rules missing. The owner adds to {local} "permissions.allow": '
                     + ', '.join(json.dumps(m) for m in missing))
    f, w = devin_checks(a)
    fails += f
    warns += w
    cur =ad.git(main_, 'rev-parse', '--abbrev-ref', 'HEAD')
    if cur != a['main_branch']:
        warns.append(f'main checkout is on {cur}, not {a["main_branch"]}')
    dirty = ad.git(main_, 'status', '--porcelain').splitlines()
    if dirty:
        warns.append(f'main checkout has {len(dirty)} uncommitted paths: no merge until clean')
        un = untracked(main_)
        if un:
            warns.append(f'untracked on main: {", ".join(un[:5])}{" ..." if len(un) > 5 else ""}: commit, '
                         f'gitignore or remove before the first merge (merge.py refuses a dirty main)')
    for f in a['env_files']:
        if not os.path.exists(os.path.join(main_, f)):
            warns.append(f'env file {f} missing in the main checkout: worktrees will lack it')
    stashes = ad.git(main_, 'stash', 'list', check=False).splitlines()
    if stashes:
        warns.append(f'{len(stashes)} stash(es) exist; implementers must never pop them')
    n_trees = ad.git(main_, 'worktree', 'list', '--porcelain').count('\nworktree ') + 1
    lim = inotify_limit()
    if lim and lim <= 65536 and n_trees >= 5:
        warns.append(f'{n_trees} worktrees on an inotify limit of {lim}: watchers crash with ENOSPC near 7. '
                     f'Remove merged worktrees (status.py prints the lines); eyeball servers run without watch')
    if a['test_slots'] < 2 and a['concurrency']['devin'] > 1:
        print(f'tests: {a["test_slots"]} test slot, so parallel Devins queue their test runs (testlock.py)')
    if shutil.which('dcg'):
        print('dcg: active. Script files, not heredocs (and no `${…}` in one); commit messages via '
              '`git commit -F <file>`; no `git -C` in shell loops and no `W=…; git -C $W` (literal paths); '
              '`>>` not `>` under ~; `git branch -d`, `worktree remove`, `checkout --`, `restore`, `reset` '
              'are the owner\'s unless their allowlist says otherwise')
    b = budget.summary(a)
    print(b['line'])
    for w in warns:
        print('WARN', w)
    for sig, q in b['questions']:
        print(f'QUESTION ({sig}, once this week): {q}')
    for f in fails:
        print('FAIL', f)
    print('PREFLIGHT ' + ('FAILED' if fails else 'OK'))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
