"""Merge reviewed branches into local main, then gate the MERGED tree before anything is reported.

  merge.py <repo> --release R [--no-db] [--no-handoff] [--note T] [--reviews T] [--next T] <task>=<branch>...
  merge.py <repo> --release R ... --after <task>=<branch>...   (after a hand-resolved conflict)

1. Main must be checked out on the main branch and clean (merge-only main), and each branch's
   worktree must pass the stamp check (db.py `stamp_check`: every new DB test green through
   `db.py` at the branch head); a miss sends the task back before anything is committed.
2. Handoff (adapter `handoff`, unless --no-handoff): writes the "merging" entry under the file's
   `## Log` heading line (`--note`: the owner's OK, what the branches carry) and commits it.
3. `git merge --no-ff --no-edit` each branch in order. A conflict only in the adapter's
   `append_only` files goes through resolve_append.py and is committed. Any other conflict stops
   with exit 2 and the merge left in progress: resolve it by hand, commit, then rerun with --after.
4. Adapter `install_on_change` for each lockfile the merges changed (default: `npm install` where
   a `package-lock.json` changed), then gates on main (gates.py), then the DB tier (db.py) unless
   --no-db.
5. Green: the "MERGED" handoff entry with every gate's tail (`--reviews`, `--next` add lines),
   committed; a MERGED ledger row per task; the removal command for each merged worktree.
   Red: exit 1. Do not report "merged" until this prints MERGED TREE GREEN. Every step's own exit
   code is checked: no pipes.
Use --no-handoff for a branch that rewrites the handoff itself (a release close-out).
"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import gates as gt
import ledger as lg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child scripts'



def five_hour(a):
    """The 5h window now, for the OUTCOME row; a missing usage.json must not fail a merge."""
    try:
        import budget
        return budget.summary(a)['signals']['five_hour_pct']
    except Exception:
        return None

def run(main, *args):
    return subprocess.run(['git', '-C', main, *args], capture_output=True, text=True)


def merge_one(a, main, branch):
    r = run(main, 'merge', '--no-ff', '--no-edit', branch)
    if r.returncode == 0:
        print(f'merged {branch}: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ok"}')
        return
    conflicted = run(main, 'diff', '--name-only', '--diff-filter=U').stdout.split()
    if not conflicted:
        ad.die(f'merge of {branch} failed without conflicts:\n{r.stderr.strip()}')
    other = [f for f in conflicted if f not in a['append_only']]
    if other:
        print(f'CONFLICT merging {branch} outside append-only files: {", ".join(other)}')
        print(f'append-only files also conflicted: {", ".join(set(conflicted) - set(other)) or "none"}')
        print('Resolve by hand (resolve_append.py for the append-only ones), commit, then rerun with --after.')
        sys.exit(2)
    rr = subprocess.run([sys.executable, os.path.join(HERE, 'resolve_append.py'),
                         *[os.path.join(main, f) for f in conflicted]], capture_output=True, text=True)
    print(rr.stdout.strip())
    if rr.returncode != 0:
        print(rr.stderr.strip())
        print('Resolver refused: resolve by hand, commit, then rerun with --after.')
        sys.exit(2)
    for cmd in (['add', *conflicted], ['commit', '--no-edit']):
        c = run(main, *cmd)
        if c.returncode != 0:
            ad.die(f'git {cmd[0]} failed: {c.stderr.strip()}')
    print(f'merged {branch} with keep-both on: {", ".join(conflicted)}')


def pre_merge(where, branches):
    """The first-parent commit before any of these branches was merged in (works after --after too)."""
    for c in ad.git(where, 'rev-list', '--first-parent', '--max-count=200', 'HEAD').split():
        if all(run(where, 'merge-base', '--is-ancestor', b, c).returncode != 0 for b in branches):
            return c
    ad.die('could not find the commit before these merges in the last 200 first-parent commits')


def install_changed(a, where, since):
    """Run adapter `install_on_change` for each lockfile the merges changed. In 2.8.0 a branch added
    `marked` and the merged-tree gate went red: merge.py had not installed it. Returns False on failure."""
    changed = ad.git(where, 'diff', '--name-only', since, 'HEAD').splitlines()
    ok = True
    for path in changed:
        cmd = a['install_on_change'].get(os.path.basename(path))
        if not cmd:
            continue
        d = os.path.join(where, os.path.dirname(path))
        r = subprocess.run(cmd, shell=True, cwd=d, env=ad.env(a), capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
        print(f'{path} changed: `{cmd}` in {d} -> exit {r.returncode}: {" / ".join(tail)}')
        ok = ok and r.returncode == 0
    return ok


def branch_worktrees(main):
    """{branch: worktree path} from `git worktree list`."""
    out = {}
    for block in ad.git(main, 'worktree', 'list', '--porcelain').split('\n\n'):
        kv = dict(l.split(' ', 1) for l in block.splitlines() if ' ' in l)
        if 'branch' in kv:
            out[kv['branch'].replace('refs/heads/', '')] = kv['worktree']
    return out


def stamp_misses(a, trees, branches):
    """The stamp check per branch worktree (db.stamp_check): ['branch: test: why']."""
    if not a['db_test']:
        return []
    import db
    return [f'{b}: {f}: {why}' for b in branches if trees.get(b)
            for f, why in db.stamp_check(a, trees[b])]


def bundle_task(a, wt):
    """The ledger task a worktree was made for (`worktree.py --task`), or None."""
    prefix = os.path.basename(a['_main']) + '-'
    base = os.path.basename(wt or '')
    return base[len(prefix):] if base.startswith(prefix) else None


def stamp():
    z = time.strftime('%z')
    return time.strftime('%Y-%m-%d %H:%M ') + (z[:3] if z.endswith('00') else z)


def handoff_entry(a, main, title, bullets, commit_msg):
    """Insert an entry right under the `## Log` heading line and commit it on main."""
    p = os.path.join(main, a['handoff'])
    lines = open(p).read().split('\n')
    try:
        i = lines.index('## Log')  # the heading line itself, never a mention of it in prose
    except ValueError:
        ad.die(f'{a["handoff"]} has no "## Log" heading line: write the entry by hand')
    entry = [f'## {stamp()} | {a["main_branch"]} | {a["handoff_agent"]} — {title}', '']
    entry += [f'- {b}' for b in bullets if b] + ['']
    rest = lines[i + 1:]
    while rest and rest[0] == '':
        rest.pop(0)
    lines = lines[:i + 1] + [''] + entry + rest
    open(p, 'w').write('\n'.join(lines))
    for cmd in (['add', a['handoff']], ['commit', '-m', commit_msg]):
        c = run(main, *cmd)
        if c.returncode != 0:
            ad.die(f'git {cmd[0]} failed: {c.stderr.strip()}')
    print(f'handoff: "{title}" committed')


def main():
    args = sys.argv[1:]
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    note, reviews, nxt = ad.opt(args, '--note'), ad.opt(args, '--reviews'), ad.opt(args, '--next')
    no_db = '--no-db' in args
    after = '--after' in args
    pairs = [x.split('=', 1) if '=' in x else [x, x] for x in args if not x.startswith('--')]
    a, main_ = ad.load(repo)
    release = ad.resolve_release(a, release)
    if any(b.startswith('eyeball/') for _, b in pairs):
        ad.die('eyeball/* is a throwaway preview: merge the task branches it was built from')
    use_handoff = bool(a['handoff']) and '--no-handoff' not in args
    ids = ' + '.join(t for t, _ in pairs)
    branches = list(dict.fromkeys(b for _, b in pairs))  # a bundle passes one branch per task id
    names = ', '.join(branches)
    trees = branch_worktrees(main_)
    # The ledger task each branch was built under (its ROUTE row's key), for the close-out's routes.
    bundles = list(dict.fromkeys(bundle_task(a, trees.get(b)) or t for t, b in pairs))
    cur = ad.git(main_, 'rev-parse', '--abbrev-ref', 'HEAD')
    if cur != a['main_branch']:
        ad.die(f'main checkout is on {cur}, not {a["main_branch"]}')
    if not after:
        dirty = ad.git(main_, 'status', '--porcelain')
        if dirty:
            ad.die(f'main checkout is not clean; no merge until it is:\n{dirty}')
        misses = stamp_misses(a, trees, branches)
        if misses:
            ad.die('DB STAMP: new DB tests with no green db.py run at the branch head; send the '
                   'task back (brief rule 3):\n' + '\n'.join(misses))
        if use_handoff:
            handoff_entry(a, main_, 'merging ' + ' + '.join(f'`{b}`' for b in branches) + ' to main',
                          [note or f'Reviewed; merging {ids}. `merge.py` gates the merged tree'
                                    + ('' if no_db or not a['db_test'] else ' and runs the DB tier') + '.'],
                          f'docs(handoff): merging {ids}')
        for branch in branches:
            merge_one(a, main_, branch)
    elif run(main_, 'rev-parse', '-q', '--verify', 'MERGE_HEAD').returncode == 0:
        ad.die('a merge is still in progress: commit it first')
    else:
        # --after resumes the run: the branches after the hand-resolved one are still unmerged
        # (2.6.5: the release branch was gated and logged MERGED without ever being merged).
        for branch in branches:
            if run(main_, 'merge-base', '--is-ancestor', branch, 'HEAD').returncode != 0:
                merge_one(a, main_, branch)
    missing = [b for b in branches
               if run(main_, 'merge-base', '--is-ancestor', b, 'HEAD').returncode != 0]
    if missing:
        ad.die(f'not in main after merging: {", ".join(missing)}')
    if not install_changed(a, main_, pre_merge(main_, branches)):
        ad.die('install failed after the merge: fix it before gating (the merge commits stay)')
    print()
    evidence = []
    ok = gt.run_gates(main_, a, evidence)
    db_ok, db_tail = True, []
    if ok and a['db_test'] and not no_db:
        print()
        d = subprocess.run([sys.executable, os.path.join(HERE, 'db.py'), main_, '--wait'],
                           capture_output=True, text=True)
        print((d.stdout + d.stderr).rstrip())
        db_ok = d.returncode == 0
        db_tail = [l.split(' · log:')[0].strip() for l in d.stdout.splitlines()
                   if l.strip() and not l.startswith('before:')][-3:]
    head = ad.git(main_, 'rev-parse', '--short', 'HEAD')
    lf = ad.ledger_file(a, release)
    if ok is gt.VOID:
        print(f'\nMERGED TREE VOID at {head}: main moved while the gates ran. Do not report merged; '
              f'rerun with --after once nothing writes to main.')
        sys.exit(1)
    if not (ok and db_ok):
        print(f'\nMERGED TREE RED at {head}: do not report merged. Fix forward (coordinator rule: '
              f'<= 20 lines in a test or declaration) or send it back to the implementer.')
        if os.path.exists(lf):
            lg.add(lf, '+'.join(bundles), 'coordinator', f'GATES RED on merged main {head} after {names}')
        sys.exit(1)
    print(f'\nMERGED TREE GREEN at {head} ({names}).')
    if use_handoff:
        bullets = ['`merge.py`, exit 0: ' + '; '.join(evidence)
                   + (f'; DB tier: {" / ".join(db_tail)}' if db_tail else '')
                   + f'. `MERGED TREE GREEN at {head}`.',
                   f'Reviews: {reviews}' if reviews else None,
                   f'Next: {nxt}' if nxt else None]
        handoff_entry(a, main_, f'{ids} MERGED @ {head} (not pushed)', bullets, f'docs(handoff): {ids} merged')
    if os.path.exists(lf):
        five = five_hour(a)
        for task, branch in pairs:
            lg.add(lf, task, 'coordinator',
                   f'MERGED {branch} into main @ {head}; merged-tree gates green{"" if no_db or not a["db_test"] else ", db green"}')
            lg.add(lf, task, 'coordinator', lg.outcome(lf, task, five))
    for branch in branches:
        wt = trees.get(branch)
        if wt and wt != main_ and os.path.isdir(wt) and not ad.git(wt, 'status', '--porcelain', check=False):
            print(f'worktree done (frees inotify watches): git -C {main_} worktree remove {wt}')
    ewt = ad.worktree_path(a, f'eyeball-{release}')
    if os.path.isdir(ewt):
        print(f'eyeball tree done once its stack is merged: stop its servers, then '
              f'git -C {main_} worktree remove {ewt} && git -C {main_} branch -D eyeball/{release}')


if __name__ == '__main__':
    main()
