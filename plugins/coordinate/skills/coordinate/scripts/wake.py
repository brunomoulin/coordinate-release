"""Wake a parked coordinator after the 5-hour window resets.

  wake.py <repo> --release R --session <id> [--fresh | --fork-session] [--after-reset]
          [--after-work] [--max-tries 8] [--retry-minutes 15] [--dry-run] [--foreground]

Arming refuses (exit 2) while a `devin -p` or `chain.py` of this repo runs under a Claude session:
the `/exit` the wake needs kills those. A chain detaches itself, so it and its Devins keep running
and do not refuse; a bare `devin -p` does. Otherwise it detaches into its own session (survives the
`/exit`), prints its pid and log, and exits 0; --foreground runs the tries in this process instead.

With --after-work, first wait until this repo's Devin runs and chains have ended (a look every
minute, giving up after 12 h), so a park with queued rounds wakes on their end. Armed, it writes
`<log_dir>/wake-<release>.pid`, which `status.py` prints as WAKE ARMED; a woken session shows there
as WAKE SESSION RUNNING while it works.

With --after-reset, sleep until `five_hour_resets_at` (usage.json) plus 2 minutes; without it, try
now. Each try runs, from the repo,
  claude --bg -n "wake <R>" "resume coordinator on <R>. Woken by wake.py ..." -r <id> --permission-mode auto
(the prompt says to leave what needs the owner, eyeball checks included, and work on the rest, and to
end with a park that opens "For you", `now.md` sent by SendUserFile, and a PushNotification:
the last park is the summary, one file, the owner, 2026-10-26) or, with
--fresh, the same without `-r <id>`: a new session that starts at 0 context and reads the
release's now.md and decisions.md (a one-file ledger: its Parked and Decisions sections), as a
`/clear` resume does (resuming a coordinator parked at 280k wakes it at 280k). A background
session, not `claude -p`: it connects to Remote Control, so the owner sees it in the Claude app and its
push reaches their phone (the 2026-10-26 `-p` wake ran unseen). `claude --bg` returns at once, so
the try watches it (`claude agents --json`): busy after a minute, or a turn ended with no limit
message, is awake; a limit message on an idle session is a refusal (`claude stop`, then sleep
`--retry-minutes` and try again, up to `--max-tries`). Logs go to `<log_dir>/wake-<release>.log`.
Exit 0 when a try wakes, 1 when the cap is hit.

If a `claude` process still has session <id> open, the try is skipped (a second writer would fork
the transcript; with --fresh, two coordinators would run the release) unless --fork-session says
to resume a copy.
"""
import argparse, atexit, datetime as dt, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import budget
import status

GRACE = 120  # seconds after the reset before the first try
# Read only from an idle session's screen: a working one may print these words in its own work.
LIMIT = re.compile(r'hit your limit|usage limit|rate limit|limit reached|out of (extra )?usage', re.I)
ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][A-Z0-9]')
WATCH_POLL = 30   # seconds between looks at the woken session
WATCH_MIN = 60    # a refusal shows within the first request; before this, idle may mean "starting"
WORK_POLL = 60    # seconds between looks at the repo's Devin work (--after-work)
WORK_MAX = 12 * 3600  # give up waiting for the work after this
WATCH_MAX = 600   # past this with no verdict, call it awake (it is listed in the app either way)


def log(f, msg):
    line = f'{dt.datetime.now().isoformat(timespec="seconds")} {msg}'
    print(line, flush=True)
    f.write(line + '\n')
    f.flush()


def reset_epoch():
    """The raw window end: budget.signals() drops it once it is past, which is the case we want."""
    return budget._epoch(budget._load(budget.USAGE).get('five_hour_resets_at'))


def open_session(sid):
    """Command lines of other claude processes holding this session."""
    r = subprocess.run(['pgrep', '-af', f'claude.*{re.escape(sid)}'], capture_output=True, text=True)
    mine = {str(os.getpid()), str(os.getppid())}
    return [l for l in r.stdout.splitlines()
            if l.split(None, 1)[0] not in mine and 'wake.py' not in l]


def chain_procs():
    """[(pid, repo path)] of running chain.py processes; a detached chain's follower is not one."""
    r = subprocess.run(['pgrep', '-f', 'chain.py'], capture_output=True, text=True)
    out = []
    for pid in r.stdout.split():
        try:
            argv = open(f'/proc/{pid}/cmdline').read().split('\0')
            cwd = os.readlink(f'/proc/{pid}/cwd')
        except OSError:
            continue
        i = next((i for i, x in enumerate(argv) if x.endswith('chain.py')), None)
        if i is not None and i + 1 < len(argv) and argv[i + 1] != '--follow':
            out.append((pid, os.path.normpath(os.path.join(cwd, argv[i + 1]))))
    return out


def parent(pid):
    """(parent pid, process name) from /proc, or None when the process is gone."""
    try:
        stat = open(f'/proc/{pid}/stat').read()
    except OSError:
        return None
    name, rest = stat[stat.index('(') + 1:].rsplit(')', 1)
    return int(rest.split()[1]), name


def attached(pid):
    """True when a claude process is among <pid>'s ancestors: its `/exit` kills the run."""
    while pid > 1 and (p := parent(pid)):
        pid, name = p
        if name == 'claude':
            return True
    return False


def live_runs(a):
    """The Devin runs and chains of this repo (main checkout or a task worktree) still running
    under a Claude session; a detached chain and its Devins are not."""
    main_, wt = a['_main'], ad.worktree_path(a, '')
    mine = lambda p: p == main_ or p.startswith(wt)
    return ([f'devin pid {pid} in {os.path.basename(cwd)} (log {log})'
             for pid, cwd, log, _ in status.devin_procs() if mine(cwd) and attached(int(pid))] +
            [f'chain.py pid {pid}' for pid, repo in chain_procs() if mine(repo) and attached(int(pid))])


def repo_work(a):
    """The Devin runs and chains of this repo still running, attached to a session or detached."""
    main_, wt = a['_main'], ad.worktree_path(a, '')
    mine = lambda p: p == main_ or p.startswith(wt)
    return ([f'devin pid {pid}' for pid, cwd, _, _ in status.devin_procs() if mine(cwd)] +
            [f'chain.py pid {pid}' for pid, repo in chain_procs() if mine(repo)])


def wait_for_work(f, a, cap=WORK_MAX):
    """Sleep until this repo's Devin work has ended, plus a short grace so its markers land.
    False when it still runs after `cap` seconds. A park with queued rounds wakes on their end, not
    at the 5-hour reset (second pilot v1: two rounds finished at 03:27 and sat unread)."""
    start, seen = time.time(), False
    while work := repo_work(a):
        seen = True
        if time.time() - start >= cap:
            log(f, f'{work[0]} (and {len(work) - 1} more) still running after {cap // 3600} h: not waking')
            return False
        time.sleep(WORK_POLL)
    if seen:
        log(f, f'Devin work ended after {int(time.time() - start) // 60} min')
        time.sleep(GRACE)
    return True


def park_file(a, release):
    """The release's `now.md`, or None for a one-file ledger (its park is a section, not a file)."""
    import ledger as lg
    f = ad.ledger_file(a, release)
    return lg.sibling(f, 'now') if lg.folder(f) else None


def prompt(release, park):
    # Armed even with eyeball checks open (the owner, 2026-10-24): the woken session works around the owner.
    # The last park is the summary: one file, not a second one beside now.md (the owner, 2026-10-26).
    send = f'send {park} with SendUserFile' if park else 'send the file you gave `ledger.py park` with SendUserFile'
    return (f'resume coordinator on {release}. Woken by wake.py while the owner is away: leave the '
            'eyeball checks and anything else that needs the owner in your report, and work on the rest. '
            'When you stop (done, parked, or waiting on the owner), park as usual with `ledger.py park`, '
            'the park opening with "For you" in under 10 lines: what waits on the owner, what merged, '
            f'what still runs. Then {send} (status proactive), and a PushNotification that leads '
            'with what waits on the owner.')


def command(release, session, fresh, fork, park):
    cmd = ['claude', '--bg', '-n', f'wake {release}', prompt(release, park), '--permission-mode', 'auto']
    if not fresh:
        cmd[5:5] = ['-r', session]
    if fork:
        cmd.append('--fork-session')
    return cmd


def bg_id(out):
    """The short id `claude --bg` prints ("backgrounded · da1c7991 · <name>"), or None."""
    m = re.search(r'backgrounded\s*·\s*(\w+)', ANSI.sub('', out))
    return m.group(1) if m else None


def agent_state(bid):
    """The background session's state from `claude agents --json --all` (busy, idle, done,
    stopped, ...), or None when it is not listed."""
    for x in status.agent_rows() or []:
        if x.get('id') == bid or str(x.get('sessionId', '')).startswith(bid):
            return x.get('state') or x.get('status')
    return None


def session_logs(bid):
    r = subprocess.run(['claude', 'logs', bid], capture_output=True, text=True)
    return ANSI.sub('', r.stdout)[-3000:]


def watch(f, bid):
    """'woke', 'limit' (refused; the session is stopped) or 'gone' (it ended or was never listed)."""
    start = time.time()
    while time.time() - start < WATCH_MAX:
        time.sleep(WATCH_POLL)
        state = agent_state(bid)
        if state in (None, 'stopped'):
            return 'gone'
        if time.time() - start < WATCH_MIN:
            continue
        if state == 'busy':
            return 'woke'
        if LIMIT.search(session_logs(bid)):
            subprocess.run(['claude', 'stop', bid], capture_output=True, text=True)
            return 'limit'
        return 'woke'
    log(f, f'{bid}: no verdict in {WATCH_MAX // 60} min; taken as awake')
    return 'woke'


def sleep_until(f, t, why):
    wait = t - time.time()
    if wait > 0:
        log(f, f'sleeping {int(wait // 60)} min: {why}')
        time.sleep(wait)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('repo')
    p.add_argument('--release', required=True)
    p.add_argument('--session', required=True)
    p.add_argument('--fresh', action='store_true', help='start a new session instead of -r <session>')
    p.add_argument('--after-reset', action='store_true')
    p.add_argument('--after-work', action='store_true',
                   help='first wait until this repo\'s Devin runs and chains have ended')
    p.add_argument('--fork-session', action='store_true')
    p.add_argument('--max-tries', type=int, default=8)
    p.add_argument('--retry-minutes', type=float, default=15)
    p.add_argument('--dry-run', action='store_true', help='print the command and stop')
    p.add_argument('--foreground', action='store_true', help='run the tries here (the armed copy does)')
    args = p.parse_args()
    if args.fresh and args.fork_session:
        p.error('--fresh starts a new session; --fork-session copies the old one: pick one')

    a, main_dir = ad.load(args.repo)
    cmd = command(args.release, args.session, args.fresh, args.fork_session, park_file(a, args.release))
    if args.dry_run:
        print(' '.join(repr(c) if ' ' in c else c for c in cmd))
        return 0

    path = os.path.join(ad.log_dir(a), f'wake-{args.release}.log')
    if not args.foreground:
        if live := live_runs(a):
            print('not armed: ' + '; '.join(live) + '. /exit would kill them (children of this '
                  'session). Wait for each to reply, then arm again.')
            return 2
        child = subprocess.Popen([sys.executable, os.path.abspath(__file__), *sys.argv[1:], '--foreground'],
                                 cwd=main_dir, start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        open(status.wake_pidfile(a, args.release), 'w').write(str(child.pid))
        print(f'armed: pid {child.pid}, {"fresh session" if args.fresh else "resume " + args.session}; '
              f'log {path}. Now /exit this session; if it asks, "Exit and stop tasks": a chain it '
              'lists keeps running, only its follower stops.')
        return 0

    f = open(path, 'a')
    pf = status.wake_pidfile(a, args.release)
    atexit.register(lambda: os.path.exists(pf) and os.unlink(pf))
    if args.after_reset:
        r = reset_epoch()
        if r:
            sleep_until(f, r + GRACE, 'until the 5-hour window resets')
        else:
            log(f, 'no five_hour_resets_at in usage.json; trying now')

    if args.after_work and not wait_for_work(f, a):
        return 1

    for n in range(1, args.max_tries + 1):
        if not args.fork_session and (held := open_session(args.session)):
            log(f, f'try {n}: session still open, skipped ({held[0][:80]})')
        else:
            log(f, f'try {n}: claude --bg "resume coordinator on {args.release}"{"" if args.fresh else " -r"} ...')
            r = subprocess.run(cmd, cwd=main_dir, env=ad.env(a), capture_output=True, text=True)
            out = ANSI.sub('', r.stdout + r.stderr).strip()
            f.write(out + '\n')
            bid = bg_id(out)
            if r.returncode != 0 or not bid:
                log(f, f'try {n}: did not start (exit {r.returncode}): {out[-160:]!r}')
            else:
                got = watch(f, bid)
                if got == 'woke':
                    log(f, f'try {n}: woke, background session {bid} ("wake {args.release}" in the app)')
                    return 0
                log(f, f'try {n}: {bid} ' + ('refused at the limit, stopped' if got == 'limit' else 'ended'))
        if n < args.max_tries:
            sleep_until(f, time.time() + args.retry_minutes * 60, f'retry {n + 1} of {args.max_tries}')
    log(f, f'gave up after {args.max_tries} tries')
    return 1


if __name__ == '__main__':
    sys.exit(main())
