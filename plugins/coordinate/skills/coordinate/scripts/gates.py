"""Run the adapter's gates in one or more worktrees, sequentially. A claim is not evidence: this is.

  gates.py <worktree>...

Each worktree gets a full log in the adapter's log_dir (gates-<name>.log). Each gate runs holding
one test slot (testlock.py, adapter `test_slots`), so parallel implementers' test runs queue
instead of timing each other out. Prints, per gate, the exit code and the matching tail lines,
then GATES GREEN or GATES RED. Exit 1 if any gate failed. Every step's own exit code is checked:
no pipes.

A tree that moves under the gates proves nothing (2.10.0: 2 of 6 gate reds were a Devin's `git
merge main` landing mid-run). So a worktree where a Devin build or fix round is running is not
gated (GATES NOT RUN; a review Devin only reads, so it does not count), and when HEAD, the
uncommitted files or a merge in progress changed during the run, the verdict is GATES VOID, not
RED: rerun once the tree is still. Exit 3 for both.
The stamp check (2.16.0, replacing the coordinator's rerun of new DB tests): a new DB test with
no green `db.py` run at HEAD (brief rule 3) makes the gates RED (`db stamp`), so the task goes
back. Also notes the DB tests already on main that import a file the branch changed: the DB tier
is not a gate, so rerun those with `db.py` yourself.
"""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import status
import testlock

VOID = None  # run_gates' return when the run proves nothing (falsy, so merge.py treats it as red)


def tree_state(wt):
    merging = subprocess.run(['git', '-C', wt, 'rev-parse', '-q', '--verify', 'MERGE_HEAD'],
                             capture_output=True).returncode == 0
    return (ad.git(wt, 'rev-parse', 'HEAD'), ad.git(wt, 'status', '--porcelain', check=False), merging)


def moved(before, after):
    what = []
    if before[0] != after[0]:
        what.append(f'HEAD {before[0][:8]} -> {after[0][:8]}')
    if before[1] != after[1]:
        what.append('uncommitted files changed')
    if before[2] != after[2]:
        what.append('a merge started or ended')
    return what


def db_notes(wt, a):
    """-> (stamp check misses, note lines). A miss reddens the gates: the task goes back."""
    if not a['db_test'] or os.path.realpath(wt) == os.path.realpath(a['_main']):
        return [], []
    import db
    missing, touched = db.stamp_check(a, wt), db.touched_db_tests(a, wt)
    lines = [f'DB STAMP {f}: {why}' for f, why in missing]
    if touched:
        lines.append(f'NOTE: DB tests that import a file this branch changed (rerun with db.py): {", ".join(touched)}')
    return missing, lines


def run_gates(wt, a, evidence=None):
    """Run every gate; print the summary. `evidence`, if a list, gets one short line per gate.
    True green, False red, VOID when nothing was proved."""
    name = os.path.basename(os.path.abspath(wt))
    builders = [(pid, pf) for pid, pf in status.devin_in(wt) if not status.is_review_brief(pf)]
    if builders:
        print(f'GATES NOT RUN ({name}): Devin pid {builders[0][0]} is working in it '
              f'({os.path.basename(builders[0][1]) or "no prompt file"}). Gate it after the run exits.')
        return VOID
    log = os.path.join(ad.log_dir(a), f'gates-{name}.log')
    pat = re.compile(a['gate_grep'])
    head = ad.git(wt, 'rev-parse', '--short', 'HEAD')
    branch = ad.git(wt, 'rev-parse', '--abbrev-ref', 'HEAD')
    before = tree_state(wt)
    failed = []
    summary = [f'== {name} {branch} @ {head}']
    with open(log, 'w') as L:
        L.write(summary[0] + '\n')
        for g in a['gates']:
            cwd = os.path.join(wt, g.get('dir', '.'))
            with testlock.slot(a, f'gate {g["name"]} in {name}'):
                r = subprocess.run(g['cmd'], shell=True, cwd=cwd, env=ad.env(a),
                                   capture_output=True, text=True)
            out = r.stdout + r.stderr
            L.write(f'\n--- {g["name"]}: {g["cmd"]} -> exit {r.returncode}\n{out}\n')
            hits = [l for l in out.splitlines() if pat.search(l)][-6:]
            summary.append(f'--- {g["name"]} -> exit {r.returncode}')
            summary += ['    ' + l.strip()[:160] for l in hits]
            if evidence is not None:
                evidence.append(f'{g["name"]} exit {r.returncode}: '
                                + ' / '.join(l.strip()[:100] for l in hits[-2:]))
            if r.returncode != 0:
                failed.append(g['name'])
                summary += ['    ' + l.strip()[:160] for l in out.splitlines()[-4:]]
    changed = moved(before, tree_state(wt))
    missing, notes = db_notes(wt, a)
    if missing:
        failed.append('db stamp')
        if evidence is not None:
            evidence.append(f'db stamp: {len(missing)} new DB test(s) with no green db.py run at HEAD')
    if changed:
        verdict = (f'GATES VOID ({name} @ {head}): the tree moved during the run ({"; ".join(changed)}). '
                   f'Not a result: rerun once it is still.')
    elif failed:
        verdict = f'GATES RED ({name} @ {head}): {", ".join(failed)}'
    else:
        verdict = f'GATES GREEN ({name} @ {head})'
    summary += notes + [verdict, f'log: {log}']
    print('\n'.join(summary))
    return VOID if changed else not failed


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    results = []
    for wt in sys.argv[1:]:
        a, _ = ad.load(wt)
        if not a['gates']:
            ad.die(f'adapter {a["_path"]} lists no gates')
        results.append(run_gates(wt, a))
    sys.exit(1 if False in results else 3 if VOID in results else 0)
