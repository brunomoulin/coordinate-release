"""One screen of what is running and where things stand. Read-only.

  status.py <repo> [--release R|auto] [--json]

Shows: free slots (Devin running vs adapter `concurrency.devin`, test slots in use), running
`devin -p` processes (worktree, model, log, last log lines; FOLDER DELETED when its worktree was
removed under it), every worktree read live from
`git worktree list` (branch, commits ahead of main, uncommitted files, a REMOVABLE verdict with
the exact removal command, and worktrees whose folder is gone; --json adds each one's changed
files), the stash count (stashes are
shared by all worktrees), the ledger's latest row per task, the live files past their cap (`live_caps`), the budget
posture and the session budget. `--release auto` (the default with --json) follows the newest ledger.
Background Sonnet agents are not visible from here: count them from your own Agent launches.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import testlock

HERE = os.path.dirname(os.path.abspath(__file__))
# The changed files --json lists per worktree, for the pane's MAP trees; the rest are counted.
FILES_CAP = 40
sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child scripts'


def devin_procs():
    r = subprocess.run(['pgrep', '-af', 'devin -p'], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        pid, _, cmd = line.partition(' ')
        if 'pgrep' in cmd or not cmd.startswith('devin'):
            continue
        try:
            cwd = os.readlink(f'/proc/{pid}/cwd')
            log = os.readlink(f'/proc/{pid}/fd/1')
        except OSError:
            cwd, log = '?', '?'
        m = re.search(r'--model\s+(\S+)', cmd)
        out.append((pid, cwd, log, m.group(1) if m else 'UNPINNED (no --model: Devin default)'))
    return out


def agent_rows():
    """`claude agents --json --all` as a list, or None when claude is missing or says nothing usable."""
    try:
        r = subprocess.run(['claude', 'agents', '--json', '--all'], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def wake_pidfile(a, release):
    return os.path.join(a['log_dir'], f'wake-{release}.pid')


def wake_lines(a, release):
    """What a resume must know before it starts working: a wake armed and sleeping (the old session
    parked and left), or a woken background session still coordinating this release."""
    out = []
    try:
        pid = int(open(wake_pidfile(a, release)).read().strip())
        if os.path.exists(f'/proc/{pid}'):
            out.append(f'WAKE ARMED pid {pid}: a fresh session starts by itself; `kill {pid}` cancels it '
                       f'(log {a["log_dir"]}/wake-{release}.log)')
    except (OSError, ValueError):
        pass
    for x in agent_rows() or []:
        st = x.get('state') or x.get('status')
        if x.get('name') == f'wake {release}' and st not in ('done', 'stopped', None):
            out.append(f'WAKE SESSION RUNNING {x.get("id")} ({st}): it is coordinating {release} now. '
                       f'Wait for its park, or `claude stop {x.get("id")}` first: two coordinators on one '
                       f'release double-launch work')
    return out


def devin_in(wt):
    """[(pid, prompt file)] of the Devin runs working in <wt>."""
    wt = os.path.realpath(wt)
    out = []
    for pid, cwd, _, _ in devin_procs():
        if cwd == wt:
            try:
                argv = open(f'/proc/{pid}/cmdline').read().split('\0')
            except OSError:
                argv = []
            pf = argv[argv.index('--prompt-file') + 1] if '--prompt-file' in argv[:-1] else ''
            out.append((pid, pf))
    return out


def is_review_brief(path):
    """A review, re-review or critique brief: that Devin reads the worktree, it does not write it."""
    return os.path.basename(path).startswith(('review', 'critique', 'rereview', 're-review'))


def tail(path, n=3):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4000))
            lines = f.read().decode('utf-8', 'replace').splitlines()
        return [l.strip()[:160] for l in lines if l.strip()][-n:]
    except OSError:
        return []


def elapsed(pid):
    r = subprocess.run(['ps', '-o', 'etimes=', '-p', pid], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def changed_files(wt, base):
    """A worktree's files changed since `base`, committed or not: git's status letter (A M D,
    `?` untracked), lines added and removed, and `unsaved` when not committed yet. Not
    `status --porcelain`: ad.git strips the first line's leading space."""
    lines = {}
    for line in ad.git(wt, 'diff', '--numstat', '--no-renames', base, check=False).splitlines():
        add, rm, path = line.split('\t', 2)
        lines[path] = (int(add) if add != '-' else 0, int(rm) if rm != '-' else 0)
    unsaved = set(ad.git(wt, 'diff', '--name-only', '--no-renames', 'HEAD', check=False).splitlines())
    files = []
    for line in ad.git(wt, 'diff', '--name-status', '--no-renames', base, check=False).splitlines():
        st, path = line.split('\t', 1)
        add, rm = lines.get(path, (0, 0))
        files.append({'path': path, 'status': st[0], 'add': add, 'del': rm, 'unsaved': path in unsaved})
    for path in ad.git(wt, 'ls-files', '--others', '--exclude-standard', check=False).splitlines():
        files.append({'path': path, 'status': '?', 'add': 0, 'del': 0, 'unsaved': True})
    return sorted(files, key=lambda f: f['path'])


def worktrees(a, main_, running):
    """Every worktree, live. `deletable`: merged into main, clean, nothing running in it."""
    mb = a['main_branch']
    # Branch tips that main merged (--no-ff merges: the tip is a merge commit's second parent).
    # Not `is-ancestor`: a fresh worktree with no commits yet is an ancestor of main too.
    merged_tips = set()
    for line in ad.git(main_, 'log', '--merges', '--format=%P', '-n', '500', mb, check=False).splitlines():
        merged_tips.update(line.split()[1:])
    trees = []
    for block in ad.git(main_, 'worktree', 'list', '--porcelain').split('\n\n'):
        lines = block.splitlines()
        kv = dict(l.split(' ', 1) for l in lines if ' ' in l)
        wt = kv.get('worktree')
        if not wt:
            continue
        br = kv.get('branch', '(detached)').replace('refs/heads/', '')
        is_main = br == mb and wt == main_
        if 'prunable' in kv or any(l.startswith('prunable') for l in lines) or not os.path.isdir(wt):
            trees.append({'name': os.path.basename(wt), 'path': wt, 'branch': br, 'main': False,
                          'ahead': 0, 'dirty': 0, 'running': False, 'deletable': False, 'missing': True})
            continue
        dirty = len(ad.git(wt, 'status', '--porcelain', check=False).splitlines())
        ahead = 0 if is_main else int(ad.git(wt, 'rev-list', '--count', f'{mb}..HEAD', check=False) or 0)
        merged = not is_main and kv.get('HEAD') in merged_tips
        # A branch's changes count from its fork point; main's are its uncommitted ones.
        base = 'HEAD' if is_main else ad.git(wt, 'merge-base', mb, 'HEAD', check=False) or mb
        files = changed_files(wt, base)
        trees.append({'name': os.path.basename(wt), 'path': wt, 'branch': br, 'main': is_main,
                      'ahead': ahead, 'dirty': dirty, 'running': wt in running, 'missing': False,
                      'deletable': merged and dirty == 0 and wt not in running,
                      'files': files[:FILES_CAP], 'files_more': max(0, len(files) - FILES_CAP)})
    return trees


def queued(script, held, flag=None):
    """Python processes running `script` (with `flag`, when given) that are not a holder pid."""
    r = subprocess.run(['pgrep', '-f', script], capture_output=True, text=True)
    n = 0
    for pid in r.stdout.split():
        try:
            argv = open(f'/proc/{pid}/cmdline').read().split('\0')
        except OSError:
            continue
        # A python running the script itself, not a shell whose command line mentions it.
        if (len(argv) > 1 and os.path.basename(argv[0]).startswith('python')
                and argv[1].endswith(script) and '--status' not in argv and pid not in held
                and (flag is None or flag in argv)):
            n += 1
    return n


def test_waiting(holders):
    """`testlock.py` runs queued for a slot: running, but not the pid written in any slot file."""
    return queued('testlock.py', {h.split()[0] for _, h in holders if h})


def db_run(a):
    """The DB tier's one run (its own lock, not a test slot: 2.11.0's merges ran it unseen in the
    pane): {'holder': 'pid time db <tree>' or None, 'waiting': `db.py --wait` runs behind it}, or
    None when the adapter has no `db_test`."""
    if not a.get('db_test'):
        return None
    h = testlock.held(testlock.db_lock_path(a))
    return {'holder': h, 'waiting': queued('db.py', {h.split()[0]} if h else set(), '--wait')}


def over_caps(a, release):
    """Live files a resume reads, past their adapter `live_caps` line count: what is done in them
    belongs in history (ledger.py park, decide, eyeball.py checks ok, the lessons promotion pass)."""
    import ledger as lg
    caps, out = a['live_caps'], []

    def check(p, n, cap, fix):
        if n > cap:
            out.append(f'{os.path.relpath(p, a["_main"])}: {n} lines, cap {cap}: {fix}')
    lf = ad.ledger_file(a, release) if release else None
    if lf and os.path.exists(lf):
        if lg.folder(lf):
            for name, fix in (('now', 'park replaces it whole'), ('decisions', 'decisions done belong in history.md'),
                              ('eyeball', 'checks ok moves passed checks out')):
                p = lg.sibling(lf, name)
                if os.path.exists(p):
                    check(p, len(open(p).read().splitlines()), caps[name], fix)
        else:
            parked = lg.section(open(lf).read(), 'Parked')
            check(lf, len(parked.strip().splitlines()), caps['now'],
                  'its Parked section; `ledger.py park` replaces it and keeps the old text in history')
    if os.path.exists(a['lessons_file']):
        check(a['lessons_file'], len(open(a['lessons_file']).read().splitlines()), caps['lessons'],
              'lessons a SKILL.md rule, script or tooling-facts line now carries move to lessons-history.md')
    return out


def as_json(a, main_, release):
    """The same picture as data, for the command-center mod's pane."""
    import budget, checks as ck, ledger as lg
    procs = devin_procs()
    running = {cwd for _, cwd, _, _ in procs}
    devin = [{'pid': pid, 'worktree': os.path.basename(cwd), 'log': log, 'model': model,
              'paid': 'fusion' in model or 'opus' in model, 'seconds': elapsed(pid),
              'last': (tail(log, 1) or [''])[0]} for pid, cwd, log, model in procs]
    tasks = []
    if release:
        lf = ad.ledger_file(a, release)
        if os.path.exists(lf):
            last, merged = {}, set()
            for t, task, who, ev in lg.rows(lf):
                task, ev = task.strip(), ev.strip()
                last[task] = {'time': t, 'task': task, 'who': who.strip(), 'event': ev}
                # The pane's merged count: a task with a MERGED row, whenever it landed (the
                # OUTCOME row merge.py writes after it becomes the task's latest event).
                if ev.startswith('MERGED'):
                    merged.add(task)
            for task in merged:
                last[task]['merged'] = True
            tasks = sorted(last.values(), key=lambda r: r['time'])
    # The mod's 👁 marker: eyeball checks still waiting on the owner (feedback is a fix round, not
    # their queue; `fixed` returns it as `recheck`). An agent verdict does not close one.
    open_checks = [{'id': i, 'task': c['task'], 'where': c['where'], 'what': c['what'], 'state': c['state']}
                   for i, c in ck.load(ck.path(a, release)).items()
                   if c['state'] in ck.WAITING and c['state'] != 'feedback'] if release else []
    holders = testlock.holders(a)
    b = budget.summary(a)
    return {'release': release, 'devin': devin, 'worktrees': worktrees(a, main_, running),
            'stashes': len(ad.git(main_, 'stash', 'list', check=False).splitlines()),
            'tasks': tasks, 'limits': a['session_limits'], 'concurrency': a['concurrency'],
            'test_slots': [{'slot': n, 'holder': h} for n, h in holders],
            'test_waiting': test_waiting(holders), 'db': db_run(a), 'checks': open_checks,
            'posture': b['posture'], 'budget_line': b['line']}


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    release = ad.opt(args, '--release')
    want_json = '--json' in args
    a, main_ = ad.load(args[0])
    release = ad.resolve_release(a, release or ('auto' if want_json else None))
    if want_json:
        import json
        print(json.dumps(as_json(a, main_, release)))
        return
    procs = devin_procs()
    holders = testlock.holders(a)
    busy = [h for _, h in holders if h]
    cap = a['concurrency']
    db = db_run(a)
    db_txt = '' if db is None else \
        f"db {'running' if db['holder'] else 'free'}{f', {db['waiting']} queued' if db['waiting'] else ''} · "
    print(f"## Slots: devin {max(0, cap['devin'] - len(procs))}/{cap['devin']} free · "
          f"tests {len(holders) - len(busy)}/{len(holders)} free, {test_waiting(holders)} queued · {db_txt}"
          f"sonnet cap {cap['sonnet']}, opus review cap {cap['opus_review']} (count your own Agent launches)")
    for h in busy:
        print(f'    test slot held: {h}')
    if db and db['holder']:
        print(f"    db held: {db['holder']}")
    print('\n## Devin running')
    if not procs:
        print('none')
    for pid, cwd, log, model in procs:
        print(f'pid {pid} in {os.path.basename(cwd)} · {model} · log {log}')
        if cwd.endswith(' (deleted)'):
            # 2.10.0: a worktree removed under a running Devin; it recreated the folder by hand,
            # without the env files, and the next launch failed.
            print(f'    FOLDER DELETED under this run: stop it (kill {pid}), recreate the worktree with '
                  f'worktree.py --setup, relaunch')
        for l in tail(log):
            print('    ' + l)
    print('\n## Worktrees')
    trees = worktrees(a, main_, {cwd for _, cwd, _, _ in procs})
    for t in trees:
        if t['missing']:
            print(f"{t['name']:<32} {t['branch']:<48} FOLDER GONE")
            continue
        verdict = ' · REMOVABLE (merged, clean)' if t['deletable'] else ''
        ahead = '-' if t['main'] else t['ahead']
        print(f"{t['name']:<32} {t['branch']:<48} ahead {ahead:>3} · uncommitted {t['dirty']}{verdict}")
    for t in trees:
        if t['deletable']:
            print(f"  remove: git -C {main_} worktree remove {t['path']}")
    if any(t['missing'] for t in trees):
        print(f'  stale entries: git -C {main_} worktree prune')
    stashes = ad.git(main_, 'stash', 'list', check=False).splitlines()
    print(f'\n## Stashes: {len(stashes)}' + (' (an implementer may have stashed: check)' if stashes else ''))
    if release:
        lf = ad.ledger_file(a, release)
        print(f'\n## Ledger {os.path.dirname(lf) if ad.in_folder(a, release) else lf}'
              f' · briefs {ad.briefs_path(a, release)}')
        if os.path.exists(lf):
            subprocess.run([sys.executable, os.path.join(HERE, 'ledger.py'), 'state', lf])
            if ad.in_folder(a, release):
                import ledger as lg
                on, since = lg.auto_on(lf)
                picks, waits = len(lg.items(lf, 'auto', True)), len(lg.items(lf, 'waits', True))
                if on or picks or waits:
                    print(f'AUTO MODE {"on since " + since if on else "off"} · {picks} decided for the owner to '
                          f'review · {waits} waiting for them (now.md lists them)')
        else:
            print('no ledger yet')
        for w in over_caps(a, release):
            print(f'OVER CAP {w}')
        if os.path.exists(lf):
            import ledger as lg, tasks
            for l in tasks.status_lines(a, main_, lg.rows(lf)):
                print(l)
        for w in wake_lines(a, release):
            print(w)
    print('\n## Session')
    subprocess.run([sys.executable, os.path.join(HERE, 'session.py'), main_]
                   + (['--release', release] if release else []))


if __name__ == '__main__':
    main()
