"""Run the DB-test tier in a worktree, one run at a time across all worktrees, with a leak check.

  db.py <worktree> [--wait] [--reviewed] [--recheck] [--trust-snapshot] [test-file...]

1. Takes an exclusive lock: the DB tier shares one database, so only one run at a time. Exit 6
   when another run holds it; `--wait` queues behind it instead.
2. Guard: every DB test NEW on this branch (adapter `db_test.new_glob`, default `*.dbtest.*`) is
   scanned for writes that commit (a transaction never rolled back, a write with no transaction,
   an afterAll that deletes rows, a literal COMMIT) and for a `lock_timeout` with no longer test
   timeout. A hit refuses the run (exit 7): read each hit line, then rerun with --reviewed, or
   send the test back. A committing test leaves rows on the shared dev DB that may be immutable.
3. Snapshot before (adapter `db_snapshot`, a command that prints one JSON object; it gets the
   worktree path as its last argument). The first pilot's snapshot also lists migrations the dev DB lacks.
   The snapshot script is the coordinator's guard: the first run keeps a trusted copy in
   `<log_dir>/db-snapshot-trusted/`; when the script differs from it, the run stops with the diff
   (exit 8) until the coordinator reads it and reruns with `--trust-snapshot`.
4. Stops if the snapshot reports `pending_migrations`: check what they would write on dev, migrate
   dev from that worktree, then rerun (a pending migration fails every reader).
5. Runs `db_test` (plus any test files, relative to `db_test.dir`; a leading `<dir>/` is
   stripped), then snapshots again and prints what changed. When the DB changed, it reruns once:
   changed again is a leak (exit 4); unchanged the second time means another writer (the owner's dev
   UI shares the DB) wrote during the first run, and the result is the tests' own.
6. Stamps the result (`<log_dir>/db-stamps.jsonl`: worktree, commit, files, exit) when the tree
   has no uncommitted changes. A RED-check run (fix neutered, tree dirty) is never stamped.
7. `--recheck` (the coordinator's rerun of an implementer's tests): compares with the
   implementer's stamps for the same files (by basename) at the same commit and writes a
   DBRECHECK ledger row: `agree`, `DISAGREE`, `stale` (the implementer ran it only at an older
   commit), `unrun` (never on this worktree) or `guard` (the guard refused the implementer and the
   coordinator ran it `--reviewed`), with `run=` naming the implementer run compared. The
   close-out counts them once per run: the owner's test of whether the rerun earns its cost
   (2026-10-14).
Exit: 0 green and unchanged; 1 tests red; 4 the DB changed (a leak; wins over 1); 5 pending migrations;
6 another run holds the lock; 7 the guard refused; 8 the snapshot script changed.
"""
import difflib, fcntl, fnmatch, json, os, re, shlex, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import ledger as lg
import testlock

WRITE = re.compile(r'\.(create|bulkCreate|update|destroy|upsert|save|increment|decrement)\(')
LOCK_TIMEOUT = re.compile(r"lock_timeout\s*(?:=|TO)?\s*'?(\d+)\s*(ms|s)?", re.I)
TEST_TIMEOUT = re.compile(r'(?:testTimeout|timeout)\s*:\s*([\d_]+)|\}\s*,\s*([\d_]{4,9})\s*\)\s*;?\s*$', re.M)


def strip_dir(f, d):
    d = (d or '.').strip('/')
    return f[len(d) + 1:] if d not in ('', '.') and f.startswith(d + '/') else f


def call_args(text, i):
    """The text of the call whose `(` is at i, up to its matching `)`."""
    depth = 0
    for j in range(i, min(len(text), i + 4000)):
        depth += {'(': 1, ')': -1}.get(text[j], 0)
        if depth == 0:
            return text[i:j + 1]
    return text[i:i + 4000]


def scan(text, default_timeout_ms=5000):
    """Lines a human must read before this DB test runs on the shared database."""
    hits, lines = [], text.splitlines()
    if re.search(r'\.transaction\(', text) and not re.search(r'rollback', text, re.I):
        hits.append((0, 'a transaction is opened but nothing rolls back'))
    for m in WRITE.finditer(text):
        n = text[:m.start()].count('\n') + 1
        line = lines[n - 1].strip()
        if line.startswith(('//', '*')) or 'transaction' in call_args(text, m.end() - 1):
            continue
        hits.append((n, f'write with no transaction in the call: {line[:100]}'))
    for n, l in enumerate(lines, 1):
        if re.search(r'\bCOMMIT\b', l):
            hits.append((n, f'literal COMMIT: {l.strip()[:100]}'))
    for m in re.finditer(r'after(All|Each)\s*\(', text):
        if re.search(r'destroy\(|TRUNCATE|DELETE\s+FROM', call_args(text, m.end() - 1), re.I):
            hits.append((text[:m.start()].count('\n') + 1, f'after{m.group(1)} deletes rows: something was committed'))
    locks = [int(v) * (1 if u and u.lower() == 'ms' else 1000) for v, u in LOCK_TIMEOUT.findall(text)]
    if locks:
        outs = [int((a or b).replace('_', '')) for a, b in TEST_TIMEOUT.findall(text)] or [default_timeout_ms]
        if max(outs) <= max(locks):
            hits.append((0, f'lock_timeout {max(locks)} ms but no test timeout longer than it '
                            f'(longest seen or default: {max(outs)} ms)'))
    return hits


def new_db_tests(a, wt):
    """DB tests this branch adds (committed or untracked), by adapter `db_test.new_glob`."""
    glob = a['db_test'].get('new_glob', '*.dbtest.*')
    new = ad.git(wt, 'diff', '--name-only', '--diff-filter=A', f'{a["main_branch"]}...HEAD', check=False).split()
    new += [l[3:] for l in ad.git(wt, 'status', '--porcelain', check=False).splitlines() if l.startswith('??')]
    return sorted({f for f in new if fnmatch.fnmatch(os.path.basename(f), glob)})


# A relative import or require; a vi.mock()/jest.mock() of a file does not run it, so it is not one.
IMPORT = re.compile(r'''(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"](\.\.?/[^'"]+)['"]''')
CODE_EXT = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')


def touched_db_tests(a, wt):
    """DB tests already on main that import a file this branch changed (gates.py names them).
    Brief rule 3 runs only NEW DB tests: in pilot 2.11.0, task 497 changed an upload path and
    a DB test went red unseen until a stacked branch's Devin ran it."""
    glob = a['db_test'].get('new_glob', '*.dbtest.*')
    stem = lambda f: f[:-len(os.path.splitext(f)[1])] if f.endswith(CODE_EXT) else f
    changed = ad.git(wt, 'diff', '--name-only', f'{a["main_branch"]}...HEAD', check=False).split()
    changed += [l[3:] for l in ad.git(wt, 'status', '--porcelain', check=False).splitlines()]
    changed = {stem(f) for f in changed}
    new = set(new_db_tests(a, wt))
    out = []
    for f in ad.git(wt, 'ls-files', check=False).splitlines():
        if f in new or not fnmatch.fnmatch(os.path.basename(f), glob):
            continue
        try:
            text = open(os.path.join(wt, f)).read()
        except OSError:
            continue
        deps = {stem(os.path.normpath(os.path.join(os.path.dirname(f), m))) for m in IMPORT.findall(text)}
        if deps & changed or {d + '/index' for d in deps} & changed:
            out.append(f)
    return out


def stamp_check(a, wt):
    """The stamp check (the owner's rule met at 2.11.0, DISAGREE 0): every new DB test needs a green
    db.py run at HEAD, or the task goes back. -> [(test, why)] for those without one. The latest
    run at HEAD that covered the test decides; a coordinator's `--reviewed` run after the guard
    refused counts. Uncommitted changes count as no run: db.py never stamps a dirty tree."""
    head = ad.git(wt, 'rev-parse', 'HEAD')
    runs = [r for r in all_stamps(a, wt) if r['head'] == head]
    out = []
    for f in new_db_tests(a, wt):
        hit = [r for r in runs if covers(r, f)]
        if not hit:
            out.append((f, 'no db.py run at HEAD'))
        elif hit[-1]['code'] == 7:
            out.append((f, 'the guard refused it at HEAD (exit 7)'))
        elif hit[-1]['code']:
            out.append((f, f'red at HEAD (exit {hit[-1]["code"]})'))
    if out and ad.git(wt, 'status', '--porcelain', '--untracked-files=no'):
        out.append(('(tree)', 'uncommitted changes: commit, then run db.py again'))
    return out


def snapshot_script(a):
    """The script the db_snapshot command runs: its first argument that is a file under 1 MB
    (an interpreter binary is larger), or None."""
    for tok in shlex.split(a['db_snapshot'] or ''):
        p = os.path.expanduser(tok)
        if os.path.isfile(p) and os.path.getsize(p) < 1_000_000:
            return p
    return None


def check_snapshot_script(a, trust):
    """The leak check is the coordinator's guard: refuse when its script changed since the
    coordinator trusted it (2.10.0: an implementer edited dbcheck.js after it refused its run).
    The first run trusts it. Returns False when it changed."""
    src = snapshot_script(a)
    if not src:
        return True
    kept = os.path.join(ad.log_dir(a), 'db-snapshot-trusted', os.path.basename(src))
    now = open(src, 'rb').read()
    if trust or not os.path.exists(kept):
        os.makedirs(os.path.dirname(kept), exist_ok=True)
        open(kept, 'wb').write(now)
        print(f'snapshot script trusted: {src} (copy in {kept})')
        return True
    old = open(kept, 'rb').read()
    if old == now:
        return True
    print(f'SNAPSHOT SCRIPT CHANGED since the coordinator trusted it: {src}')
    text = lambda b: b.decode('utf-8', 'replace').splitlines()
    diff = list(difflib.unified_diff(text(old), text(now), 'trusted', 'now', lineterm=''))
    print('\n'.join(diff[:40]) + ('\n...' if len(diff) > 40 else ''))
    print('Coordinator: read the diff; if it is right, rerun with --trust-snapshot. Implementers never do.')
    return False


def guard(a, wt, files):
    t = a['db_test']
    refused = False
    for f in new_db_tests(a, wt):
        try:
            hits = scan(open(os.path.join(wt, f)).read(), t.get('default_timeout_ms', 5000))
        except OSError:
            continue
        if hits:
            refused = True
            print(f'GUARD {f}: read these before it runs on the shared DB')
            for n, why in hits:
                print(f'    {f}:{n}  {why}' if n else f'    {f}  {why}')
    return refused


def snapshot(a, wt):
    if not a['db_snapshot']:
        return None
    r = subprocess.run(f'{a["db_snapshot"]} {shlex.quote(wt)}', shell=True, env=ad.env(a),
                       capture_output=True, text=True)
    if r.returncode != 0:
        ad.die(f'db_snapshot failed: {r.stderr.strip()[:400]}')
    return json.loads(r.stdout.strip().splitlines()[-1])


def stamps_file(a):
    return os.path.join(ad.log_dir(a), 'db-stamps.jsonl')


def tree_state(wt):
    """(commit, clean): clean = no uncommitted changes to tracked files."""
    head = ad.git(wt, 'rev-parse', 'HEAD')
    return head, not ad.git(wt, 'status', '--porcelain', '--untracked-files=no')


def stamp(a, wt, files, code, recheck, reviewed):
    head, clean = tree_state(wt)
    if not clean:
        return
    with open(stamps_file(a), 'a') as f:
        f.write(json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M'), 'wt': os.path.basename(wt),
                            'head': head, 'files': sorted(files), 'code': code,
                            'recheck': recheck, 'reviewed': reviewed}) + '\n')


def all_stamps(a, wt):
    """Every stamp for this worktree, the coordinator's rechecks included, oldest first."""
    try:
        rows = [json.loads(l) for l in open(stamps_file(a)) if l.strip()]
    except OSError:
        rows = []
    return [r for r in rows if r['wt'] == os.path.basename(wt)]


def impl_stamps(a, wt):
    """The implementer's stamps (not the coordinator's rechecks) for this worktree, oldest first."""
    return [r for r in all_stamps(a, wt) if not r['recheck']]


def covers(r, f):
    """Did stamp r run test f? By basename: implementers pass `x.dbtest.ts`, the coordinator
    `src/tests/db/x.dbtest.ts` (2.10.0 counted 6 matching runs as `unrun`). No files = whole tier."""
    return not r['files'] or os.path.basename(f) in {os.path.basename(x) for x in r['files']}


def compare(a, wt, files, code):
    """The coordinator's result against the implementer's stamps at this commit -> (class, impl,
    runs): runs names the implementer runs compared, so the close-out counts each run once.
    unrun: no implementer run of a test on this worktree; stale: only at an older commit."""
    head, clean = tree_state(wt)
    if not clean:
        return 'dirty', None, []
    mine = impl_stamps(a, wt)
    codes, runs, stale = [], set(), False
    for f in files or ['*']:
        # The implementer's latest run at this commit that covered this file.
        hit = [r for r in mine if r['head'] == head and covers(r, f)]
        if hit:
            codes.append(hit[-1]['code'])
            runs.add(hit[-1]['ts'].replace(' ', 'T'))
        elif any(covers(r, f) for r in mine):
            stale = True
        else:
            return 'unrun', None, []
    if stale:
        return 'stale', None, []
    impl = max(codes)
    if impl == 7:
        return 'guard', impl, sorted(runs)
    return ('agree' if impl == code else 'DISAGREE'), impl, sorted(runs)


def record_recheck(a, wt, files, code):
    cls, impl, runs = compare(a, wt, files, code)
    head = tree_state(wt)[0][:8]
    task = os.path.basename(wt)[len(os.path.basename(a['_main'])) + 1:] or os.path.basename(wt)
    ev = (f'DBRECHECK {cls} impl={"-" if impl is None else impl} coord={code} @ {head}'
          + (f' run={",".join(runs)}' if runs else '') + f'; {" ".join(files) or "all"}')
    print(ev)
    release = ad.newest_ledger(a)
    if release:
        lg.add(ad.ledger_file(a, release), task, 'coordinator', ev)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    flags = ('--reviewed', '--recheck', '--wait', '--trust-snapshot')
    reviewed, recheck, wait, trust = (f in args for f in flags)
    args = [x for x in args if x not in flags]
    if not args:
        sys.exit(__doc__)
    wt = os.path.abspath(args[0])
    a, _ = ad.load(wt)
    t = a['db_test']
    if not t:
        ad.die('adapter has no db_test')
    files = [strip_dir(f, t.get('dir')) for f in args[1:]]
    if not reviewed and guard(a, wt, files):
        print('DB GUARD REFUSED: a DB test commits nothing. Read every hit; rerun with --reviewed only '
              'when each is inside a rolled-back transaction, else send the test back.')
        if not recheck:
            stamp(a, wt, files, 7, recheck, reviewed)
        sys.exit(7)
    # 'a+', not 'w': opening must not wipe the holder line of the run that has the lock.
    lock = open(testlock.db_lock_path(a), 'a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if not wait:
            ad.die('another db.py run holds the lock: wait for it, or pass --wait', 6)
        print('another db.py run holds the lock; waiting (--wait)', flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
    # The holder line status.py and the coordinator pane show, as a test slot's.
    lock.seek(0)
    lock.truncate()
    lock.write(f'{os.getpid()} {time.strftime("%H:%M:%S")} db {os.path.basename(wt)}'
               + (f' ({len(files)} files)' if files else '') + '\n')
    lock.flush()
    if not check_snapshot_script(a, trust):
        sys.exit(8)
    before = snapshot(a, wt)
    if before is not None:
        pending = before.pop('pending_migrations', [])
        if pending:
            print('PENDING MIGRATIONS on the dev DB:', ', '.join(pending))
            sys.exit(5)
        print('before:', json.dumps(before))
    code, diff = run_tier(a, wt, files, before, 'db')
    if diff:
        # The owner's dev UI writes to the same DB (2.10.0: a login and a delete during a list run
        # read as a leak). A leak comes back on a rerun; a concurrent writer almost never does
        # in the same seconds. The coordinator's recheck already ran every test twice.
        print('DB CHANGED: rerunning once to tell a leak from a concurrent writer')
        code2, diff2 = run_tier(a, wt, files, snapshot(a, wt), 'db-confirm')
        code = max(code, code2)
        if diff2:
            print('DB CHANGED AGAIN (leak):', json.dumps(diff2))
            code = 4  # over a red test too: the leaked rows stay, a fixed test does not remove them
        else:
            print('CONCURRENT WRITER, not a leak: the DB changed during the first run only '
                  f'({json.dumps(diff)}); the confirming run left it unchanged')
    stamp(a, wt, files, code, recheck, reviewed)
    if recheck:
        record_recheck(a, wt, files, code)
    sys.exit(code)


def run_tier(a, wt, files, before, tag):
    """One run of the DB tier -> (0 green | 1 red, {key: (before, after)} of what changed)."""
    t = a['db_test']
    cmd = t['cmd'] + (' -- ' + ' '.join(shlex.quote(f) for f in files) if files else '')
    r = subprocess.run(cmd, shell=True, cwd=os.path.join(wt, t.get('dir', '.')), env=ad.env(a),
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    log = os.path.join(ad.log_dir(a), f'{tag}-{os.path.basename(wt)}.log')
    open(log, 'w').write(out)
    keep = [l for l in out.splitlines() if any(s in l for s in ('Test Files', 'Tests ', 'FAIL', '×'))]
    print('\n'.join(keep[-12:]))
    if 'No test files found' in out:
        print('NO TEST FILES FOUND: check the paths (relative to ' + t.get('dir', '.') + '/)')
    print(f'db tests exit {r.returncode} · log: {log}')
    code = 0 if r.returncode == 0 else 1
    if before is None:
        return code, {}
    before = {k: v for k, v in before.items() if k != 'pending_migrations'}
    after = snapshot(a, wt)
    after.pop('pending_migrations', None)
    diff = {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}
    if not diff:
        print('DB unchanged')
    return code, diff


if __name__ == '__main__':
    main()
