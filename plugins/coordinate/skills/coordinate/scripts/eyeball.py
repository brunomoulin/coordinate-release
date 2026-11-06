"""Fold an unmerged stack into one throwaway branch, so one server shows every branch together.

  eyeball.py <repo> --release R [--dry-run] <branch>...
  eyeball.py checks add|list|ok|feedback|fixed|import|waiting ...   The owner's list of things to look at (checks.py)
  eyeball.py verify <repo> --release R [--url U] [<id>...]   the machine eyeball brief (2.18.0): an
                    agent with a browser checks the open checks (or the ids) and writes a report;
                    `checks import` reads its verdicts. The owner still confirms every check.

1. Preview: `git merge-tree --write-tree` folds each branch, in order, onto main in memory. A
   conflict outside the adapter's `append_only` files stops here (exit 2): nothing is created.
2. Worktree `<repo>-eyeball-<R>` on branch `eyeball/<R>` from main (env files copied, setup run).
3. Each branch merged in order (append-only conflicts resolved keep-both, as merge.py does).
4. An EYEBALL ledger row with the head; the removal commands for after the real merge.

Run it again after a fix round: it merges the branches' new commits into the same worktree.
Restart the eyeball servers after that: they run without file watching. Never merge
`eyeball/<R>` itself: merge.py merges the task branches, and refuses this one.
"""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import ledger as lg
from merge import install_changed, merge_one, pre_merge

HERE = os.path.dirname(os.path.abspath(__file__))


def build(a, wt):
    """Adapter `eyeball_build` (a shell command) in the eyeball tree: the fold changes sources, not
    build output (v1: a stale `.output` until `gates.py` ran there). True when unset or it passes."""
    cmd = a['eyeball_build']
    if not cmd:
        return True
    r = subprocess.run(cmd, shell=True, cwd=wt, env=ad.env(a), capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
    print(f'eyeball_build `{cmd}` in {wt} -> exit {r.returncode}: {" / ".join(tail)}')
    return r.returncode == 0


def howto(a, release):
    """Adapter `eyeball_howto` with {worktree} and {release} filled, or None."""
    t = a['eyeball_howto']
    return t.format(worktree=ad.worktree_path(a, f'eyeball-{release}'), release=release) if t else None


def preview(a, main_, branches):
    """Fold the branches onto main without touching any checkout. Returns {branch: [conflicted]}."""
    head = ad.git(main_, 'rev-parse', a['main_branch'])
    bad = {}
    for b in branches:
        r = subprocess.run(['git', '-C', main_, 'merge-tree', '--write-tree', '--name-only', head, b],
                           capture_output=True, text=True)
        if r.returncode not in (0, 1):
            ad.die(f'merge-tree {b} failed:\n{r.stderr.strip()}')
        lines = r.stdout.splitlines()
        tree, files = lines[0], []
        for l in lines[1:]:
            if not l.strip():
                break
            files.append(l.strip())
        if r.returncode == 1:
            bad[b] = files
        head = ad.git(main_, 'commit-tree', tree, '-p', head, '-p', b, '-m', f'eyeball preview {b}')
    return bad


TEMPLATE = os.path.join(HERE, '..', 'references', 'eyeball-brief-template.md')


def verify(args):
    """The machine eyeball brief from the open checks (or the ids given): an agent with a browser
    checks what it can; `checks import` reads its report; the owner still confirms every check."""
    import checks as ck
    if not args or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release, url = ad.opt(args, '--release'), ad.opt(args, '--url')
    a, main_ = ad.load(repo)
    release = ad.resolve_release(a, release)
    ev = a['eyeball_verify']
    url = url or ev.get('url')
    if not url:
        ad.die('no eyeball stack URL: pass --url, or set adapter eyeball_verify.url')
    f = ck.path(a, release)
    cs = ck.load(f)
    ids = [int(x.lstrip('#')) for x in args if x.lstrip('#').isdigit()] or \
        [i for i, c in cs.items() if c['state'] == 'open']
    bad = [i for i in ids if i not in cs]
    if bad:
        ad.die(f'not checks in {f}: {", ".join(map(str, bad))}')
    if not ids:
        ad.die(f'no open checks without a verdict in {f}: name the ids to re-verify')
    briefs = ad.briefs_path(a, release)
    os.makedirs(briefs, exist_ok=True)
    n = 1 + sum(1 for x in os.listdir(briefs) if x.startswith('eyeball-verify-') and x.endswith('.md'))
    here = os.path.dirname(f)
    wt = ad.worktree_path(a, f'eyeball-{release}')
    wt = wt if os.path.isdir(wt) else main_
    accounts = (f'The dev logins you may use are in `{ev["accounts_file"]}`. Copy a password nowhere but '
                'your own session; logins you create yourself go in the report.') if ev.get('accounts_file') else \
        'No accounts file (adapter `eyeball_verify.accounts_file`): a check that needs a login is `NEEDS OWNER`.'
    rules = ''.join(f'{9 + k}. {r}\n' for k, r in enumerate(ev.get('rules') or []))
    lines = []
    for i in ids:
        c = cs[i]
        lines.append(f'- **#{i}** ({c["task"]}, at {c["where"]}): {c["what"]}'
                     + (f' The owner\'s feedback after their look: "{c["note"]}"; check the fix.' if c['state'] == 'feedback' else ''))
    fill = {'release': release, 'ids': ', '.join(f'#{i}' for i in ids), 'repo_name': os.path.basename(main_),
            'url': url, 'worktree': wt, 'scratch': f'/tmp/{os.path.basename(main_)}-eyeball-{release}-{n}',
            'repo_rules': rules, 'accounts': accounts, 'checks': '\n'.join(lines),
            'shots': os.path.join(here, 'eyeball-shots'), 'report': os.path.join(here, f'eyeball-report-{n}.md')}
    text = re.sub(r'<!--.*?-->\n*', '', open(TEMPLATE).read(), flags=re.S)
    for k, v in fill.items():
        text = text.replace('{{' + k + '}}', v)
    brief = os.path.join(briefs, f'eyeball-verify-{n}.md')
    open(brief, 'w').write(text)
    task = f'eyeball-verify-{n}'
    print(f'brief: {brief}\nreport (the agent writes it): {fill["report"]}\nchecks: {fill["ids"]}')
    print(f'Route: `budget.py route ... {task} devin_eyeball` (sonnet_eyeball only under SURPLUS). Launch it as '
          f'any Devin run (SKILL.md §3), task `{task}`, read-only in {wt}.')
    print(f'When it replies: eyeball.py checks import {repo} --release {release} {fill["report"]}; '
          'then the owner reads the report and confirms (`checks ok --agent-pass`, or per id).')
    return brief


def main():
    args = sys.argv[1:]
    if args and args[0] == 'checks':
        import checks
        return checks.run(args[1:])
    if args and args[0] == 'verify':
        return verify(args[1:])
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    dry = '--dry-run' in args
    branches = [x for x in args if not x.startswith('--')]
    a, main_ = ad.load(repo)
    release = ad.resolve_release(a, release)
    bad = preview(a, main_, branches)
    hard = {b: [f for f in fs if f not in a['append_only']] for b, fs in bad.items()}
    hard = {b: fs for b, fs in hard.items() if fs}
    for b, fs in bad.items():
        print(f'preview {b}: conflicts in {", ".join(fs)}' + ('' if b in hard else ' (append-only: keep-both)'))
    if hard:
        print('Stack does not fold cleanly: nothing created. Merge order, or a rebase round, first.')
        sys.exit(2)
    print(f'preview: {" + ".join(branches)} fold onto {a["main_branch"]}' + (' cleanly' if not bad else ''))
    if dry:
        return
    task, branch = f'eyeball-{release}', f'eyeball/{release}'
    w = subprocess.run([sys.executable, os.path.join(HERE, 'worktree.py'), main_, '--task', task,
                        '--branch', branch], capture_output=True, text=True)
    print(w.stdout.strip())
    if w.returncode != 0:
        ad.die(w.stderr.strip())
    wt = ad.worktree_path(a, task)
    if ad.git(wt, 'status', '--porcelain'):
        ad.die(f'{wt} is not clean: an eyeball tree holds merges only')
    for b in branches:
        merge_one(a, wt, b)
    if not install_changed(a, wt, pre_merge(wt, branches)):
        ad.die('install failed in the eyeball tree: fix it before starting servers')
    if not build(a, wt):
        ad.die('eyeball_build failed in the eyeball tree: fix it before looking')
    head = ad.git(wt, 'rev-parse', '--short', 'HEAD')
    lf = ad.ledger_file(a, release)
    if os.path.exists(lf):
        lg.add(lf, 'eyeball', 'coordinator', f'EYEBALL {branch} = {" + ".join(branches)} @ {head}; {wt}')
    print(f'\nEYEBALL TREE at {head}: {wt}')
    if h := howto(a, release):
        print(f'How to look: {h}')
    else:
        print(f'Start the servers there without file watching (ports {a["dev_ports"] or "from the adapter"}).')
    print('After the real merge (merge.py, the task branches), stop the servers, then:')
    print(f'  git -C {main_} worktree remove {wt}')
    print(f'  git -C {main_} branch -D {branch}')


if __name__ == '__main__':
    main()
