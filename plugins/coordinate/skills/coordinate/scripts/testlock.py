"""A counting semaphore around test runs: implementers code in parallel, test runs queue.

  testlock.py [--repo <path>] -- <command...>     run the command holding one test slot
  testlock.py [--repo <path>] --status            who holds which slot

Two full test runs at once on one machine time out real-timer tests (pilot 2.7.0: rateLimiter,
People.*). The adapter's `test_slots` (default 1) sets how many runs may go at once; every slot is
a file `<log_dir>/test-slot-<n>.lock` held with flock, so a crashed run frees its slot. The repo is
found from --repo or the current directory (any worktree). Exits with the command's exit code.
`gates.py` takes a slot per gate; briefs tell implementers to run tests through this script.
"""
import contextlib, fcntl, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad


def _slot_path(a, n):
    return os.path.join(ad.log_dir(a), f'test-slot-{n}.lock')


@contextlib.contextmanager
def slot(a, label=''):
    """Hold one of the adapter's `test_slots` for the duration of the block."""
    n_slots = max(1, int(a['test_slots']))
    waited = False
    while True:
        for n in range(n_slots):
            f = open(_slot_path(a, n), 'a+')
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            f.seek(0)
            f.truncate()
            f.write(f'{os.getpid()} {time.strftime("%H:%M:%S")} {label}\n')
            f.flush()
            try:
                yield n
            finally:
                f.seek(0)
                f.truncate()
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()
            return
        if not waited:
            print(f'testlock: all {n_slots} test slot(s) busy; waiting', file=sys.stderr, flush=True)
            waited = True
        time.sleep(2)


def held(p):
    """The 'pid time label' line of a held lock file, or None when nobody holds it."""
    try:
        with open(p, 'a+') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
            except BlockingIOError:
                f.seek(0)
                return f.read().strip() or '?'
    except OSError:
        pass
    return None


def db_lock_path(a):
    """db.py's lock: the DB tier shares one database, so one run at a time, apart from the slots."""
    return os.path.join(ad.log_dir(a), 'db.lock')


def holders(a):
    """[(slot, 'pid time label') or (slot, None)] for every slot."""
    return [(n, held(_slot_path(a, n))) for n in range(max(1, int(a['test_slots'])))]


def main():
    args = sys.argv[1:]
    repo = ad.opt(args, '--repo', '.')
    a, _ = ad.load(repo)
    if args == ['--status']:
        for n, h in holders(a):
            print(f'slot {n}: {h or "free"}')
        return
    if not args or args[0] != '--' or len(args) < 2:
        sys.exit(__doc__)
    cmd = args[1:]
    with slot(a, ' '.join(cmd)[:80] + f' in {os.path.basename(os.getcwd())}'):
        r = subprocess.run(cmd)
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
