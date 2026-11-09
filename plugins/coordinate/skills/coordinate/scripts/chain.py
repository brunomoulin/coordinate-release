"""Chain Devin runs so they start without a coordinator turn each. Run it in the background.

  chain.py <repo> --release R [--after MARKER] [--fusion] <worktree>=<brief>[:<session>] ...

<worktree> is a task id (worktree `<parent>/<repo>-<id>`) or a path; <brief> is a file name in
`<briefs_dir>/<release>/` or a path; <session> resumes that Devin session (`devin list --format
json` in the worktree). Items run one after another. Before each launch the queue waits until
fewer than `concurrency.devin` Devins run; several chains in parallel share those slots.

Markers: when an item exits, the line `end <brief-stem>` (e.g. `end 380-r2`) is appended to
`<briefs_dir>/<release>/queue.log`. `--after end 380-r2` waits until that exact line is there:
a whole-line match, never a substring (`queue done` once matched `r1 queue done` and two Devins
ran at once). Each item's log is `<brief-stem>.log` beside the brief. A paid run (Fusion, or a
devin.model the Devin catalog does not list as Free) whose log says the quota ran out records it
(budget.py) and stops the chain; for a build model the stop line names the free models now
(`Free now: ...`) and the settings.py line that switches the release to the first.
Ledger rows: LAUNCHED per item, then EXITED with the exit code; the coordinator still verifies.

Detached: the items are checked here, then a worker runs them outside the Claude session, so a
`/exit` (or a closed terminal) leaves the chain and its Devins running. This process stays as a
follower: it relays the worker's output and ends with it, so a live session still gets its
notification and exit code (1 when the queue stopped or the worker died). The output is kept in
`chain-<first brief stem>.out` beside the briefs: the only place a stop message lands once the
follower is gone. Internal: --worker <fd>, --follow <out> <fd>.
"""
import os, select, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import budget
import ledger as lg
import status


def wait_for(path, marker):
    said = False
    while True:
        try:
            if any(l.strip() == marker for l in open(path)):
                return
        except OSError:
            pass
        if not said:
            print(f'waiting for the line "{marker}" in {path}', flush=True)
            said = True
        time.sleep(15)


def wait_for_slot(a):
    said = False
    while len(status.devin_procs()) >= a['concurrency']['devin']:
        if not said:
            print(f"all {a['concurrency']['devin']} Devin slots busy; waiting", flush=True)
            said = True
        time.sleep(20)


def quota_out(log, model, repo, release, run=subprocess.run):
    """When a paid build model's log says the Devin quota ran out: record it, refresh the catalog
    and name the free models to switch to. None when the log says nothing of the kind."""
    if not budget.scan_devin_log(log):
        return None
    free = ad.free_devin_models(ad.devin_catalog(refresh=True, run=run))
    msg = f'Devin quota ran out on {model}. Free now: {", ".join(free) or "none listed"}.'
    if free:
        msg += f' Switch: settings.py set {repo} --release {release} devin.model={free[0]}'
    return msg


def detach(argv, out):
    """Hand the chain to a worker the session cannot kill, and become its follower. `setsid -f`,
    not Popen(start_new_session=True): `/exit` kills the shell's children by parent, not by
    session, so the worker must not stay a child of this process. It never returns."""
    r, w = os.pipe()
    with open(out, 'w') as o:
        subprocess.run(['setsid', '-f', sys.executable, os.path.abspath(__file__), *argv, '--worker', str(w)],
                       stdin=subprocess.DEVNULL, stdout=o, stderr=o, pass_fds=[w], check=True)
    os.close(w)
    os.set_inheritable(r, True)
    # A new command line: wake.py tells the follower, which dies with the session, from an old
    # attached chain.
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), '--follow', out, str(r)])


def follow(out, fd):
    """Relay the worker's output. The pipe's end says it stopped: a byte first means it finished."""
    with open(out) as f:
        while True:
            print(f.read(), end='', flush=True)
            if select.select([fd], [], [], 5)[0]:
                finished = os.read(fd, 1)
                print(f.read(), end='', flush=True)
                return 0 if finished else 1


def main():
    args = sys.argv[1:]
    if args[:1] == ['--follow']:
        sys.exit(follow(args[1], int(args[2])))
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    worker = ad.opt(args, '--worker')
    release = ad.opt(args, '--release')
    after = ad.opt(args, '--after')
    fusion = '--fusion' in args
    items = [x for x in args if not x.startswith('--')]
    a, _, release = ad.load_release(repo, release)
    bdir = ad.briefs_path(a, release)
    qlog = os.path.join(bdir, 'queue.log')
    lf = ad.ledger_file(a, release)
    model = ad.devin_model(a, fusion)
    paid = not fusion and ad.devin_cost(model) == 'paid'
    plan = []
    for it in items:
        if '=' not in it:
            sys.exit(f'bad item {it!r}: want <worktree>=<brief>[:<session>]\n\n' + __doc__)
        wt, rest = it.split('=', 1)
        brief, _, session = rest.partition(':')
        wt = wt if os.sep in wt else ad.worktree_path(a, wt)
        brief = brief if os.sep in brief else os.path.join(bdir, brief)
        if not os.path.isdir(wt):
            sys.exit(f'no worktree {wt}: worktree.py first')
        if not os.path.isfile(brief):
            sys.exit(f'no brief {brief}')
        plan.append((wt, brief, session))
    if not plan:
        sys.exit(__doc__)
    if worker is None:
        first = os.path.splitext(os.path.basename(plan[0][1]))[0]
        detach(sys.argv[1:], os.path.join(bdir, f'chain-{first}.out'))
    if after:
        wait_for(qlog, after)
    for wt, brief, session in plan:
        stem = os.path.splitext(os.path.basename(brief))[0]
        task = os.path.basename(wt)[len(os.path.basename(a['_main'])) + 1:] or stem
        if status.is_review_brief(brief):
            task = stem  # a review runs in a build's worktree but is its own route, not a build round
        missing = [f for f in a['env_files'] if not os.path.exists(os.path.join(wt, f))]
        if missing:
            sys.exit(f'{wt} lacks {", ".join(missing)}: queue stopped before {stem}')
        wait_for_slot(a)
        log = os.path.splitext(brief)[0] + '.log'
        cmd = ['devin', '-p', '--respect-workspace-trust', 'false', '--permission-mode', 'dangerous',
               '--model', model] + (['-r', session] if session else []) + ['--prompt-file', brief]
        if os.path.exists(lf):
            lg.add(lf, task, 'devin-fusion' if fusion else 'devin-swe2',
                   f'LAUNCHED {stem} (queue{", resume " + session if session else ""}); log {log}')
        with open(log, 'a') as L:
            r = subprocess.run(cmd, cwd=wt, stdout=L, stderr=subprocess.STDOUT)
        if fusion:
            stop = budget.scan_devin_log(log) and \
                f'Devin paid quota ran out during {stem} (log says so): recorded; queue stopped'
        elif paid:
            stop = (msg := quota_out(log, model, a['_main'], release)) and f'{msg}\nQueue stopped at {stem}.'
        else:
            stop = None
        with open(qlog, 'a') as Q:
            Q.write(f'# {time.strftime("%m-%d %H:%M")} {stem} exit {r.returncode}\nend {stem}\n')
        if os.path.exists(lf):
            lg.add(lf, task, 'coordinator', f'EXITED {stem} exit {r.returncode} (queue): verify')
        print(f'end {stem} exit {r.returncode}', flush=True)
        if stop:
            sys.exit(stop)
    try:
        os.write(int(worker), b'\0')
    except BrokenPipeError:  # the follower went with its session
        pass


if __name__ == '__main__':
    main()
