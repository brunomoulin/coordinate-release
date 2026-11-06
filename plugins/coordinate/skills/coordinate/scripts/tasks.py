"""The repo's task tracker, as the release's source of "what is left" (adapter `tracker`).

`tracker()` says which: `markdown` (adapter `tasks_file`, default `TASKS.md`), `taskmaster` (adapter
`taskmaster`, the register file; read-only here: the scripts never write it) or none. status.py and
closeout.py call `status_lines` / `closeout_lines`; a repo with no tracker prints nothing.

Markdown: a checklist of the repo's tasks.

Lines `- [ ] T64 — text` / `- [x] T22b — text` count; a line without a leading task id (`T<digits>[a-z]`)
is ignored. A range (`T15–T19`) is its first id. Used by status.py (open tasks the ledger has never
heard of) and closeout.py (ticks the tasks the ledger shows MERGED).
"""
import json, os, re

LINE = re.compile(r'^(\s*- \[)([ xX])(\]\s+)(T\d+[a-z]?)\b')
ID = re.compile(r'T\d+[a-z]?')


def parse(path):
    """[(id, done, line number)] in file order."""
    out = []
    for n, line in enumerate(open(path).read().splitlines(), 1):
        m = LINE.match(line)
        if m:
            out.append((m.group(4), m.group(2) in 'xX', n))
    return out


def ledger_ids(rows):
    """Every task id the ledger's Task column names (`review-T64r3`, `T15+T16` count)."""
    return {i for _, t, _, _ in rows for i in ID.findall(t)}


def untracked(path, rows):
    """[(id, line number)] of open tasks no ledger row names."""
    seen = ledger_ids(rows)
    return [(t, n) for t, done, n in parse(path) if not done and t not in seen]


def sync(path, rows):
    """Tick the open tasks with a MERGED ledger row; returns the ids ticked."""
    merged = {t.strip() for _, t, _, ev in rows if ev.strip().startswith('MERGED')}
    ticked, lines = [], open(path).read().split('\n')
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if m and m.group(2) == ' ' and m.group(4) in merged:
            lines[i] = m.group(1) + 'x' + line[m.end(1) + 1:]
            ticked.append(m.group(4))
    if ticked:
        open(path, 'w').write('\n'.join(lines))
    return ticked


TM_DEFAULT = '.taskmaster/tasks/tasks.json'
TM_ID = re.compile(r'(?<![\w.])(\d+)(?:r\d+)?(?![\w.])')


def tracker(a, main):
    """(kind, absolute path) of the repo's tracker: an explicit adapter `tracker` wins ("none" turns
    it off), else `tasks_file` means markdown, else an existing `taskmaster` register means taskmaster."""
    t = a.get('tracker')
    full = lambda p: os.path.join(main, p)
    if t == 'none':
        return None, None
    if t == 'markdown' or (t is None and a.get('tasks_file')):
        return 'markdown', full(a.get('tasks_file') or 'TASKS.md')
    if t == 'taskmaster' or (t is None and a.get('taskmaster') and os.path.exists(full(a['taskmaster']))):
        return 'taskmaster', full(a.get('taskmaster') or TM_DEFAULT)
    return None, None


def taskmaster(path):
    """{id: status} from a TaskMaster tasks.json (tagged or flat)."""
    d = json.load(open(path))
    tagged = [v['tasks'] for v in d.values() if isinstance(v, dict) and 'tasks' in v]
    return {str(t['id']): t.get('status', '') for ts in (tagged or [d.get('tasks', [])]) for t in ts}


def tm_ids(rows):
    """Plain task numbers the ledger's Task column names (`review-466`, `466r2`, `10+11`; not `T9`
    or a version like `2.12.0`)."""
    return {i for _, t, _, _ in rows for i in TM_ID.findall(t)}


def tm_drift(path, rows):
    """([ids MERGED in the ledger but not done in TaskMaster], [in-progress ids the ledger never names])."""
    st = taskmaster(path)
    merged = {i for _, t, _, ev in rows if ev.strip().startswith('MERGED') for i in TM_ID.findall(t)}
    seen = tm_ids(rows)
    return (sorted((i for i in merged if st.get(i) not in ('done', 'cancelled')), key=int),
            sorted((i for i, s in st.items() if s == 'in-progress' and i not in seen), key=int))


def status_lines(a, main, rows):
    kind, p = tracker(a, main)
    if not kind:
        return []
    if not os.path.exists(p):
        return [f'\n## Tasks: {os.path.relpath(p, main)} not found (init.py creates the default TASKS.md)']
    if kind == 'markdown':
        new = untracked(p, rows)
        return [f'\n## Tasks file {os.path.relpath(p, main)}: {len(new)} open task(s) the ledger has not started'
                + (': ' + ', '.join(t for t, _ in new[:15]) + (' ...' if len(new) > 15 else '') if new else '')]
    drift, idle = tm_drift(p, rows)
    st = taskmaster(p)
    out = [f'\n## TaskMaster: {sum(s == "pending" for s in st.values())} pending, '
           f'{sum(s == "in-progress" for s in st.values())} in progress']
    if drift:
        out.append(f'merged in the ledger but not done in TaskMaster: {", ".join(drift)} (set_task_status)')
    if idle:
        out.append(f'in progress with no ledger row: {", ".join(idle)}')
    return out


def closeout_lines(a, main, rows):
    kind, p = tracker(a, main)
    if not kind or not os.path.exists(p):
        return []
    if kind == 'markdown':
        ticked = sync(p, rows)
        return [f'\n## Tasks file\nticked {len(ticked)} merged task(s) in {p}'
                + (f' ({", ".join(ticked)}): commit it with the close-out commit' if ticked else '')]
    drift, _ = tm_drift(p, rows)
    if not drift:
        return ['\n## TaskMaster\nevery merged task is done there']
    return [f'\n## TaskMaster\nmerged but not done: {", ".join(drift)}. Set each with `set_task_status` '
            f'(the scripts never write the register).']
