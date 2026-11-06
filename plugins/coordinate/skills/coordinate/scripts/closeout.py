"""The coordinator's part of a release close-out (the repo's close-out skill does the rest).

  closeout.py <repo> --release R [--into <worktree>]

1. Report: Claude 7-day used vs week elapsed, the Devin paid quota, and per route (from ROUTE
   rows): tasks, launches (rounds), gate reds, DB-test reds, review bugs (`bugs=N` in a row); and
   per review route, how many findings the coordinator overruled ("Not doing" in the review
   files' Disposition column, `<briefs_dir>/<release>/*-{code-review,rereview,critique}.md`).
   Printed, and written as `## Close-out report` into the release's history.md (a one-file
   ledger: above its Timeline). The
   overrules and the DB recheck count (DBRECHECK rows from `db.py --recheck`) also go into the
   lessons file, once per release, with the owner's rule for when to drop the coordinator's rerun.
   Then the dispositions still owed: blank Disposition cells, and "Not doing" reasons that defer.
   Then every tracked doc line (outside `.coordinate/`, in --into) saying R ships something, beside
   the merged tasks: each claim needs a merge behind it.
2. Archive: with adapter `ledger_archive` (e.g. `documentation/releases/{release}-ledger.md`), copies
   the ledger (a release folder's decisions, now, eyeball, history and timeline, in one file) into
   --into (default: the main checkout) for the close-out commit. A release folder also gets its
   line in `<release_dir>/index.md`: one line per closed release.
3. Cleanup for the owner: merged worktrees (`git worktree remove`) and merged branches (`git branch -d`).
4. Lessons: the lessons file to append to; skill amendments are proposals for the owner to approve.
   The promotion pass (ICM's "edit the source, not the output"): a lesson that a SKILL.md rule, a
   script check or a tooling-facts line now carries moves to `lessons-history.md` beside it, with
   that pointer, so the lessons file holds only what is not in the skill yet.
"""
import collections, os, re, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import budget
import findings as fd
import ledger as lg
import status


def per_route(lf):
    route, stats = {}, collections.defaultdict(lambda: collections.Counter())
    for _, task, who, ev in lg.rows(lf):
        task, ev = task.strip(), ev.strip()
        m = re.match(r'ROUTE -> (\S+)', ev)
        if m:
            route[task] = {'devin': 'devin_swe2'}.get(m.group(1), m.group(1))  # 2.9.0 wrote `devin`
    for _, task, who, ev in lg.rows(lf):
        task, ev = task.strip(), ev.strip()
        if task == '-':
            continue
        s = stats[route.get(task, 'unrouted')]
        if ev.startswith('LAUNCHED'):
            s['launches'] += 1
        if re.match(r'GATES (red|RED)', ev):
            s['gate reds'] += 1
        if ev.startswith('DBTEST') and re.search(r'\bRED\b|FAIL', ev):
            s['db reds'] += 1
        b = re.search(r'\bbugs=(\d+)', ev)
        if b:
            s['review bugs'] += int(b.group(1))
    for task, r in route.items():
        stats[r]['tasks'] += 1
    return stats


def rechecks(lf):
    """DBRECHECK rows (db.py --recheck) by class, one per implementer run compared (`run=`): the
    coordinator rechecks file by file, so one 2-file run used to count twice (2.10.0's DISAGREE 2
    was one run). Rows without `run=` (stale, unrun, older ledgers) count one each."""
    c, seen = collections.Counter(), set()
    for _, task, who, ev in lg.rows(lf):
        m = re.match(r'DBRECHECK (\S+)', ev.strip())
        if not m:
            continue
        run = re.search(r'\brun=(\S+?);?(?:\s|$)', ev)
        if run:
            key = (task.strip(), m.group(1), run.group(1))
            if key in seen:
                continue
            seen.add(key)
        c[m.group(1)] += 1
    return c


# The owner, 2026-10-14: implementers run their DB tests, the coordinator reruns them. Keep the rerun
# while it finds disagreements; after a release with none, replace it with a stamp check. 2.11.0
# had none (agree 18, stale 18, unrun 38): 2.16.0's gates.py and merge.py send back a new DB test
# with no green db.py run at HEAD. DBRECHECK rows now come only from spot checks.
RECHECK_RULE = ('Rule (the owner, 2026-10-14, met at 2.11.0): the stamp check replaced the coordinator\'s '
                'rerun of new DB tests. A spot-check DISAGREE (`db.py --recheck`) brings the rerun '
                'back: propose it to the owner. unrun = the implementer never ran db.py on that test; '
                'stale = it did, at an older commit.')


# The owner, 2026-10-22: how often the coordinator overrules each review route ("Not doing" in the
# Disposition column), compared release to release in the lessons file.
OVERRULE_RULE = ('Overrule = a finding the coordinator disposed "Not doing". Compare per route across '
                 'releases; a route whose overrules are mostly the reviewer being wrong (not just '
                 'low value) is a routing signal.')
REVIEW_WHO = {'opus': 'opus_review', 'devin-fusion': 'fusion_review', 'sonnet': 'sonnet_review',
              'devin-swe2': 'swe2_review', 'devin': 'swe2_review'}


def review_files(a, release):
    d = ad.briefs_path(a, release)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d)
                  if f.endswith('.md') and re.search(r'(code-review|rereview|critique)\.md$', f))


def review_route(lf, release, path):
    """The route of the review that wrote <path>: a ledger row naming the file, else the review
    task named after it (review-<x>, critique-<x>); its ROUTE row, else inferred from <who>."""
    rows = lg.rows(lf)
    route = {t.strip(): m.group(1) for _, t, _, ev in rows
             for m in [re.match(r'ROUTE -> (\S+)', ev.strip())] if m}
    who = {}
    for _, t, w, _ in rows:
        who.setdefault(t.strip(), w.strip())
    base = os.path.basename(path)
    x = re.sub(r'-(code-review|rereview|critique)\.md$', '', base[len(release) + 1:]
               if base.startswith(release + '-') else base)
    # Named tasks first: a build's LAUNCHED row also names the review its round answers.
    kinds = ('critique', 'review') if base.endswith('critique.md') else ('review', 'critique')
    xs = (x, re.sub(r'-(r\d+)', r'\1', x))  # the ledger may say review-T64r3 for T64-r3
    tasks = [c for y in xs for c in (f'{kinds[0]}-{y}', f'{kinds[1]}-{y}', y) if c in who]
    tasks += [t.strip() for _, t, _, ev in rows if base in ev
              and re.match(r'(review|critique)-', t.strip())]
    for t in tasks:
        if t in route:
            return route[t]
        if who.get(t) in REVIEW_WHO:
            r = REVIEW_WHO[who[t]]
            return 'sonnet_critique' if r == 'sonnet_review' and base.endswith('critique.md') else r
    return 'unmatched'


def overrules(a, lf, release):
    """Findings per review route, by the Disposition column (the last cell of a findings row)."""
    stats = collections.defaultdict(collections.Counter)
    for p in review_files(a, release):
        s = stats[review_route(lf, release, p)]
        seen = set()
        for _, _, _, c in fd.rows(p):
            k = fd.classify(c[-1], a.get('owner_name'))
            # One decision typed into several rows of a review (v1 T51-r2: 7 times) counts once.
            if k == 'overruled' and c[-1].strip() in seen:
                k = 'repeat'
            elif k == 'overruled':
                seen.add(c[-1].strip())
            s[k] += 1
    return stats


def unmatched_files(a, lf, release):
    return [os.path.basename(p) for p in review_files(a, release) if review_route(lf, release, p) == 'unmatched']


def owed(a, release):
    """Dispositions still owed: blank cells (2.10.0's critiques left 21), and declines whose
    reason defers (all 4 the 2.10.0 audit overturned). Printed, not written to the ledger."""
    out = []
    for p in review_files(a, release):
        rows = fd.rows(p)
        blank = [n for _, n, _, c in rows if fd.classify(c[-1]) == 'blank']
        if blank:
            out.append(f'{os.path.basename(p)}: {len(blank)} blank (#{", #".join(blank)}): `dispose.py`')
        for _, n, sev, c in rows:
            if fd.defers(c[-1]):
                out.append(f'{os.path.basename(p)} #{n} ({sev}): a decline that defers needs a Task N: '
                           f'{c[-1][:120]}')
    return out


def overrule_lines(stats):
    if not stats:
        return ['- Review overrules: no review files with a findings table.']
    out = []
    for r, s in sorted(stats.items()):
        if not sum(s.values()):
            continue
        filled = sum(v for k, v in s.items() if k not in ('blank', 'noted', 'repeat'))
        pct = f' ({100 * s["overruled"] // filled}%)' if filled else ''
        rest = ', '.join(f'{k} {s[k]}' for k in ('fixed', 'filed', 'to owner', 'noted', 'repeat', 'blank') if s[k])
        out.append(f'- Review overrules `{r}`: {s["overruled"]} of {filled} disposed{pct}'
                   + (f'; {rest}' if rest else ''))
    return out or ['- Review overrules: no findings rows in the review files.']


def recheck_line(c):
    if not c:
        return '- DB recheck: no DBRECHECK rows (the stamp check replaced the rerun in 2.16.0).'
    order = ['agree', 'DISAGREE', 'stale', 'unrun', 'guard', 'dirty']
    parts = [f'{k} {c[k]}' for k in order if c[k]] + [f'{k} {v}' for k, v in c.items() if k not in order]
    return '- DB recheck (one per implementer run): ' + ', '.join(parts)


def append_lessons(a, release, title, lines, rule):
    """Write a count into the lessons file, one block per release and title (a rerun replaces it),
    so the next skill review sees it."""
    p = a['lessons_file']
    head = f'## {release} {title} (closeout.py)'
    block = f'\n{head}\n' + '\n'.join(lines) + f'\n- {rule}\n'
    try:
        s = open(p).read()
    except OSError:
        s = ''
    s = re.sub(r'(?:^|\n)' + re.escape(head) + r'\n.*?(?=\n## |\Z)', '', s, flags=re.S)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write(s.rstrip('\n') + '\n' + block if s.strip() else block.lstrip('\n'))
    return True


def postures(lf):
    """The posture each ROUTE row recorded: the budget over the release, not at its end."""
    c = collections.Counter()
    for _, _, _, ev in lg.rows(lf):
        m = re.match(r'ROUTE -> \S+ posture=(\S+)', ev.strip())
        if m:
            c[m.group(1).replace('_', ' ')] += 1
    return c


def report(a, lf, release):
    b = budget.summary(a)
    p = postures(lf)
    # 2.10.0's close-out line read "7d 0% at 2% of week": sampled just after the weekly reset.
    lines = ['- Budget over the release (posture at each ROUTE row): '
             + (', '.join(f'{k} {v}' for k, v in p.most_common()) or 'no ROUTE rows'),
             f'- Budget now (close-out time; after a weekly reset it says nothing about the release): {b["line"]}']
    for r, s in sorted(per_route(lf).items()):
        parts = [f'{k} {v}' for k, v in s.items() if v]
        if parts:
            lines.append(f'- `{r}`: ' + ', '.join(parts))
    if len(lines) == 2:
        lines.append('- No ROUTE rows: write them with `budget.py route` next release.')
    lines += overrule_lines(overrules(a, lf, release))
    lines.append(recheck_line(rechecks(lf)))
    return lines


def write_report(lf, lines):
    """Into history.md for a release folder (a rerun replaces the block), else above the Timeline."""
    block = '## Close-out report\n\n' + '\n'.join(lines) + '\n\n'
    if lg.folder(lf):
        h = lg.sibling(lf, 'history')
        if os.path.exists(h):
            s = re.sub(r'\n## Close-out report\n.*?(?=^## |\Z)', '\n', open(h).read(), flags=re.S | re.M)
            open(h, 'w').write(s.rstrip('\n') + '\n')
        return lg.history(lf, block)
    s = open(lf).read()
    s = re.sub(r'## Close-out report\n.*?(?=^## )', '', s, flags=re.S | re.M)
    s = s.replace('## Timeline', block + '## Timeline', 1)
    open(lf, 'w').write(s)
    return lf


KEY_PATTERNS = (r'sk-[A-Za-z0-9_-]{20,}', r'AKIA[0-9A-Z]{16}', r'gh[pousr]_[A-Za-z0-9]{36,}',
                r'AIza[0-9A-Za-z_-]{35}', r'xox[abprs]-[A-Za-z0-9-]{10,}', r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
                r'(?i)\b[A-Z_]*(?:API|SECRET|TOKEN|PASSWORD)[A-Z_]*\s*[=:]\s*[\'"]?[A-Za-z0-9+/_-]{20,}')


class KeyFound(Exception):
    pass


def key_hits(text):
    """Key-shaped strings in text, as `line N: <pattern hit trimmed>`; the archive goes into git."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for pat in KEY_PATTERNS:
            m = re.search(pat, line)
            if m:
                hits.append(f'line {n}: {m.group(0)[:12]}...')
                break
    return hits


def archive(lf, dst):
    if not lg.folder(lf):
        text = open(lf).read()
    else:
        parts = [open(p).read().strip() for p in (lg.sibling(lf, n) for n in ARCHIVED) if os.path.exists(p)]
        text = '\n\n---\n\n'.join(parts) + '\n'
    hits = key_hits(text)
    if hits:
        raise KeyFound('; '.join(hits[:5]))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w').write(text)


ARCHIVED = ('decisions', 'now', 'eyeball', 'history', 'timeline')


def index_line(a, lf, release):
    """One line per closed release in `<release_dir>/index.md`; a rerun replaces it."""
    p = os.path.join(a['release_dir'], 'index.md')
    merged = len({t.strip() for _, t, _, ev in lg.rows(lf) if ev.strip().startswith('MERGED')})
    line = (f'- {release} (closed {time.strftime("%Y-%m-%d")}): {merged} tasks merged; report and history '
            f'in `{release}/history.md`\n')
    old = open(p).read().splitlines(keepends=True) if os.path.exists(p) else \
        ['# Releases\n', '\n', 'One line per closed release (closeout.py). The detail is in each folder.\n', '\n']
    old = [l for l in old if not l.startswith(f'- {release} (')]
    open(p, 'w').write(''.join(old) + line)
    return p


# Pilot 2.11.0: "2.11.0 ships only the optional MFA", written at decision time, had no commit behind
# it; only the close-out brief's cross-check against git log caught it.
SHIPS = re.compile(r'\bship(s|ped|ping)?\b', re.I)


def ships_claims(repo, release, cap=30):
    """Tracked docs' lines that say release R ships something ('file:line: text'), outside
    .coordinate/ (ledgers), for the coordinator to check against the release's merges."""
    tok = re.compile(r'(?<![\d.])' + re.escape(release) + r'(?![\d])')
    out = ad.git(repo, 'grep', '-n', '-I', '-F', release, '--', '*.md', ':!.coordinate', check=False)
    hits = [l for l in out.splitlines() if tok.search(l) and SHIPS.search(l.split(':', 2)[-1])]
    return [l[:220] for l in hits[:cap]] + ([f'... {len(hits) - cap} more'] if len(hits) > cap else [])


def main():
    args = sys.argv[1:]
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    a, main_ = ad.load(repo)
    release = ad.resolve_release(a, release)
    into = os.path.abspath(ad.opt(args, '--into', main_))
    lf = ad.ledger_file(a, release)
    if not os.path.exists(lf):
        ad.die(f'no ledger {lf}')
    print('## Report')
    lines = report(a, lf, release)
    print('\n'.join(lines))
    print(f'(written into {write_report(lf, lines)})')
    if lg.folder(lf):
        print(f'(index line in {index_line(a, lf, release)})')
    lost = unmatched_files(a, lf, release)
    if lost:
        print(f'\nReviews with no route ({len(lost)}; rename the ledger task `review-<task>` or add a ROUTE row): '
              + ', '.join(lost))
    append_lessons(a, release, 'review overrules', [l for l in lines if l.startswith('- Review overrules')],
                   OVERRULE_RULE)
    if append_lessons(a, release, 'DB recheck', [lines[-1]], RECHECK_RULE):
        print(f'(review overrules and DB recheck count appended to {a["lessons_file"]}: '
              'weigh them in the skill review)')
    debts = owed(a, release)
    if debts:
        print('\n## Dispositions owed (fill them, then rerun closeout.py so the counts are true)')
        print('\n'.join(debts))
    claims = ships_claims(into, release)
    if claims:
        merged = sorted({t.strip() for _, t, _, ev in lg.rows(lf) if ev.strip().startswith('MERGED')})
        print(f'\n## "Ships in {release}" claims (each needs a merge behind it; fix any that has none '
              f'before the push)\nMerged tasks: {", ".join(merged) or "none"}')
        print('\n'.join(claims))
    failed = None
    if a['ledger_archive']:
        dst = os.path.join(into, ad.archive_path(a, release))
        try:
            archive(lf, dst)
            print(f'\n## Archive\ncopied to {dst}: commit it with the close-out commit')
        except KeyFound as e:
            failed = (f'ARCHIVE REFUSED: key-shaped strings in the ledger ({e}). Redact them from the '
                      f'ledger files, then rerun closeout.py; nothing was written.')
        except OSError as e:
            failed = f'ARCHIVE FAILED: {e}. Fix ledger_archive in the adapter and rerun.'
        if failed:
            print('\n## Archive\n' + failed)
    import tasks
    for l in tasks.closeout_lines(a, into, lg.rows(lf)):
        print(l)
    print('\n## Cleanup (the owner runs these)')
    running = {cwd for _, cwd, _, _ in status.devin_procs()}
    for t in status.worktrees(a, main_, running):
        if t['deletable']:
            print(f"git -C {main_} worktree remove {t['path']}")
    checked_out = {t['branch'] for t in status.worktrees(a, main_, running)}
    merged = [b.strip(' *+') for b in ad.git(main_, 'branch', '--merged', a['main_branch']).splitlines()]
    merged = [b for b in merged if b and b != a['main_branch'] and b not in checked_out]
    if merged:
        print(f'git -C {main_} branch -d ' + ' '.join(merged))
    print('\n## Next (SKILL.md §9)\nPush report: "push now", the close-out merge commit, the prod steps '
          'after the deploy. Wait for the owner to say it is live (fix forward if not).')
    print(f'Then wrap up: the live-record round (runbook to history); the disposition audit '
          f'(`audit.py {main_} --release {release}`, then an Opus agent with its brief); lessons into '
          f'{a["lessons_file"]} (dated, one bullet each) and skill amendments proposed (nothing changes '
          f'without their OK); the lessons promotion pass (what the skill now carries moves to '
          f'lessons-history.md); saves; the final report last.')
    n = len(open(a['lessons_file']).read().splitlines()) if os.path.exists(a['lessons_file']) else 0
    if n > a['live_caps']['lessons']:
        print(f'{a["lessons_file"]} is {n} lines (cap {a["live_caps"]["lessons"]}): the promotion pass is due.')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
