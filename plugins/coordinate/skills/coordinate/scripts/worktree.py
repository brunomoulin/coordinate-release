"""Prepare a task's worktree: create it, copy the env files, run setup.

  worktree.py <repo> --task ID --branch B [--base REF] [--no-setup | --setup]

Creates `<worktree_parent>/<repo>-<ID>` on branch B (from REF, default main; an existing branch is
checked out as is), copies the adapter's `env_files` from the main checkout (never overwriting),
and runs `worktree_setup` (e.g. `npm ci`) when it created the worktree. An existing worktree gets
no setup unless `--setup` (a folder recreated by hand): `eyeball.py` reruns this on every fix
round, and `npm ci` there reinstalled everything under a running server. Prints the path.
"""
import os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    repo = args.pop(0)
    task, branch, base = ad.opt(args, '--task'), ad.opt(args, '--branch'), ad.opt(args, '--base')
    if not (task and branch):
        sys.exit(__doc__)
    a, main_ = ad.load(repo)
    base = base or a['main_branch']
    wt = ad.worktree_path(a, task)
    created = not os.path.isdir(wt)
    if created:
        exists = subprocess.run(['git', '-C', main_, 'rev-parse', '-q', '--verify', f'refs/heads/{branch}'],
                                capture_output=True).returncode == 0
        cmd = ['worktree', 'add', wt, branch] if exists else ['worktree', 'add', '-b', branch, wt, base]
        ad.git(main_, *cmd)
        print(f'worktree {wt} on {branch}' + ('' if exists else f' (new, from {base})'))
    else:
        cur = ad.git(wt, 'rev-parse', '--abbrev-ref', 'HEAD')
        print(f'worktree {wt} exists, on {cur}')
        if cur != branch:
            ad.die(f'it is on {cur}, not {branch}: pick another task id or fix by hand')
    for f in a['env_files']:
        src, dst = os.path.join(main_, f), os.path.join(wt, f)
        if os.path.exists(dst):
            continue
        if not os.path.exists(src):
            print(f'WARNING: {src} missing; not copied')
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f'copied {f}')
    if '--no-setup' not in args and (created or '--setup' in args):
        for c in a['worktree_setup']:
            r = subprocess.run(c, shell=True, cwd=wt, env=ad.env(a), capture_output=True, text=True)
            tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
            print(f'setup `{c}` -> exit {r.returncode}: {" / ".join(tail)}')
            if r.returncode != 0:
                ad.die('setup failed; fix before dispatching')
    print(wt)


if __name__ == '__main__':
    main()
