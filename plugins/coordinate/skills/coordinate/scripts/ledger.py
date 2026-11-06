"""The release ledger: one folder per release (2.12.0 on), live state apart from its history.

  ledger.py init      <ledger> <release>              create it (no-op if it exists)
  ledger.py add       <ledger> <task> <who> <event>   append a time-stamped row (task `-` = session-level)
  ledger.py park      <ledger> <file|-> "<summary>"   replace now.md with the file's text; the old
                                                      park goes to history.md; a PARKED row
  ledger.py decide    <ledger> [--task T] [--by owner] [--auto] --alt "<the other options>"
                      --revert "<what undoing it costs>" "<the decision>"
                      (--auto: a pick made without the owner, id A<n>, listed until they review it)
  ledger.py decide    <ledger> --waits [--task T] --options "a | b" --rec "<pick> (why)"
                      --hold schema|deploy|security|product|prod|cost "<the question>"
                      (held for the owner, id W<n>; it is a parked question until they answer)
  ledger.py auto      <ledger> on|off                 the owner's auto mode (/coordinate auto R)
  ledger.py review    <ledger> A<n> ok | A<n> override --revert "<cost>" "<their decision>"
                      | W<n> --revert "<cost>" "<their choice>"
  ledger.py decisions <ledger> [--auto|--waits] [--unreviewed]   the A/W lines
  ledger.py state     <ledger>                        the latest row per task (what is open now)
  ledger.py merges    <ledger> --since "MM-DD HH:MM"  count MERGED rows since a time
  ledger.py questions <ledger>                        the parked questions as JSON, ready for
                                                      AskUserQuestion
  ledger.py outcomes  <ledger>...                     one TSV row per merged task: route, signals
                                                      at the route, rounds, bugs, wall time

<ledger> is the release folder (`<release_dir>/<R>`, adapter default `.coordinate/releases`), or a
one-file ledger begun before 2.12.0 (`<ledger_dir>/<R>.md`; every command still reads it). In the
folder, by lifecycle (the owner, 2026-10-26: what is decided and done does not belong in what a
session reads):

  now.md        the current park: what is open, what runs, what the next session does first, the
                questions. Replaced at each park. A resume reads it and decisions.md, nothing else.
  decisions.md  the decisions in force, each dated with its alternatives and revert cost. One
                tagged [task] moves to history.md when that task merges.
  eyeball.md    open eyeball checks (`eyeball.py checks`); a passed one moves to history.md.
  timeline.md   the rows, append only: scripts parse it, nobody reads it whole.
  history.md    superseded parks, decisions done, checks passed, the close-out report. Grep it.
  briefs/       the release's briefs and review files.

A one-file ledger keeps its Decisions, Parked and Timeline sections; `park` replaces its Parked
section and moves the old text to `<R>.history.md` beside it.

Event text starting with a capitalised keyword is the convention: PLANNED, ROUTE, LAUNCHED, DONE,
GATES, DBTEST, DBRECHECK, REVIEW, FIXES, MERGED, OUTCOME, PARKED, BLOCKED. ROUTE rows come from
`budget.py route` (key=value, machine-readable); a LAUNCHED row for a task with none writes one
first, inferred from <who> (devin-swe2, devin-fusion, sonnet, opus, haiku; a task named
review-*/critique-* is a review). A review's DONE row carries `bugs=N`. `merge.py` writes an
OUTCOME row after each MERGED one, the loop closed for the v3 router.

Parked questions are written as items, one per question:

  - Q: Ship 377 before 351?
    Options: yes, 377 first | no, 351 first | both in one wave
    Rec: yes, 377 first (351 waits on the owner's census answers)
"""
import json, os, re, sys, time

HEAD = '| Time | Task | Who | Event |\n|---|---|---|---|\n'
ROW = re.compile(r'^\| (\d\d-\d\d \d\d:\d\d) \| ([^|]*) \| ([^|]*) \| (.*) \|$')
QUESTIONS = 'Open questions as items: `- Q: ...` / `  Options: a | b | c` / `  Rec: a (why)`.'
NOW_TITLE = re.compile(r'^# .*: now(?: \(park of (.*)\))?$')


def resolve(p):
    """A release folder means its timeline.md."""
    return os.path.join(p, 'timeline.md') if not p.endswith('.md') else p


def folder(f):
    return os.path.basename(f) == 'timeline.md'


def release_of(f):
    return os.path.basename(os.path.dirname(f)) if folder(f) else os.path.basename(f)[:-3]


def sibling(f, name):
    if folder(f):
        return os.path.join(os.path.dirname(f), name + '.md')
    return f[:-3] + f'.{name}.md'  # a one-file ledger has only a history beside it


def init(f, release):
    if not f.endswith('.md'):
        return init_folder(f, release)
    if os.path.exists(f):
        print('exists', f)
        return
    os.makedirs(os.path.dirname(f) or '.', exist_ok=True)
    open(f, 'w').write(
        f'# {release}: coordinator ledger\n\n'
        f'Started {time.strftime("%Y-%m-%d %H:%M")}. Written by `ledger.py`; append only.\n\n'
        '## Decisions\n\n(the owner\'s answers, dated, one bullet each.)\n\n'
        '## Parked\n\n(Written at each pause: what is open, what runs, what the next session does first.\n'
        f'{QUESTIONS})\n\n'
        '## Timeline\n\n' + HEAD)
    print('created', f)


def init_folder(d, release):
    t = os.path.join(d, 'timeline.md')
    if os.path.exists(t):
        print('exists', d)
        return
    os.makedirs(d, exist_ok=True)
    started = time.strftime('%Y-%m-%d %H:%M')
    open(os.path.join(d, 'now.md'), 'w').write(
        f'# {release}: now\n\n(Nothing parked yet. `ledger.py park` replaces this file at each pause: what is\n'
        f'open, what runs, what the next session does first. {QUESTIONS})\n')
    open(os.path.join(d, 'decisions.md'), 'w').write(
        f'# {release}: decisions in force\n\n(`ledger.py decide`: one bullet each, dated, with its alternatives and\n'
        'revert cost. One tagged [task] moves to history.md when that task merges.)\n\n')
    open(t, 'w').write(
        f'# {release}: timeline\n\nStarted {started}. Written by `ledger.py`; append only. Read it with '
        '`ledger.py state`, not whole.\n\n## Timeline\n\n' + HEAD)
    print('created', d)


def rows(f):
    out = []
    for line in open(f):
        m = ROW.match(line.rstrip('\n'))
        if m:
            out.append(m.groups())
    return out


def routed(f, task):
    return any(t.strip() == task.strip() and ev.startswith('ROUTE ->') for _, t, _, ev in rows(f))


def auto_route(f, task, who):
    """A LAUNCHED row for a task with no ROUTE row gets one, inferred from `who`."""
    if routed(f, task):
        return
    import adapter as ad, budget
    route = budget.infer_route(who, task)
    if not route:
        print(f'WARNING: no ROUTE row for {task} and `{who}` names no route: '
              f'budget.py route <repo> --release R {task} <route>')
        return
    a, _ = ad.load(os.path.dirname(os.path.abspath(f)))
    budget.route_row(a, release_of(f), task, route, f'auto from who={who.strip()}', strict=False)


def add(f, task, who, event):
    if not os.path.exists(f):
        sys.exit(f'no ledger {f}: run init first')
    s = open(f).read()
    if '## Timeline' not in s:
        sys.exit(f'{f} has no "## Timeline" section (older ledger format): init a new file')
    if event.startswith('LAUNCHED') and task.strip() not in ('-', ''):
        auto_route(f, task, who)
        s = open(f).read()
    event = event.replace('|', '/').replace('\n', ' ')
    line = f'| {time.strftime("%m-%d %H:%M")} | {task} | {who} | {event} |\n'
    if not s.endswith('\n'):
        s += '\n'
    open(f, 'w').write(s + line)
    print(line, end='')
    if folder(f) and event.startswith('MERGED'):
        retire(f, task.strip())


def state(f):
    last = {}
    for t, task, who, ev in rows(f):
        last[task.strip()] = (t, who.strip(), ev.strip())
    for task, (t, who, ev) in sorted(last.items(), key=lambda x: x[1][0]):
        print(f'{t}  {task:<14} {who:<12} {ev[:150]}')


def merges(f, since):
    n = sum(1 for t, _, _, ev in rows(f) if t >= since and ev.strip().startswith('MERGED'))
    print(n)


def section(text, name):
    m = re.search(rf'^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)', text, re.M | re.S)
    return m.group(1) if m else ''


def history(f, block):
    """Append a dated block to the release's history file."""
    h = sibling(f, 'history')
    if not os.path.exists(h):
        open(h, 'w').write(f'# {release_of(f)}: history\n\nDone and superseded: parks, decisions, eyeball '
                           'checks, the close-out report. Grep it; a resume does not read it.\n')
    with open(h, 'a') as fh:
        fh.write('\n' + block.rstrip('\n') + '\n')
    return h


def parked_text(f):
    if folder(f):
        n = sibling(f, 'now')
        return open(n).read() if os.path.exists(n) else ''
    return section(open(f).read(), 'Parked')


def park(f, text, summary):
    stamp = time.strftime('%Y-%m-%d %H:%M')
    if folder(f):
        n = sibling(f, 'now')
        old = open(n).read() if os.path.exists(n) else ''
        title, _, body = old.partition('\n')
        m = NOW_TITLE.match(title)
        body = NOW_AUTO.sub('', body)  # the auto lists are rebuilt from decisions.md, not kept
        if m and m.group(1) and body.strip():  # the init placeholder has no "(park of ...)"
            history(f, f'## Park of {m.group(1)} (superseded {stamp})\n\n{body.strip()}\n')
        open(n, 'w').write(f'# {release_of(f)}: now (park of {stamp})\n\n{text.strip()}\n')
        refresh_now(f)
    else:
        s = open(f).read()
        m = re.search(r'^## Parked\s*\n(.*?)(?=^## |\Z)', s, re.M | re.S)
        if not m:
            sys.exit(f'{f} has no "## Parked" section')
        body = m.group(1)
        blurb = re.match(r'\s*(\(.*?\))\s*\n', body, re.S)
        keep = blurb.group(1) + '\n\n' if blurb else ''
        old = body[blurb.end():] if blurb else body
        if old.strip():
            history(f, f'## Parked text superseded {stamp}\n\n{old.strip()}\n')
        s = s[:m.start(1)] + '\n' + keep + text.strip() + '\n\n' + s[m.end(1):]
        open(f, 'w').write(s)
    add(f, '-', 'coordinator', f'PARKED {summary}')


def decide(f, text, alt, revert, task=None, by='coordinator', auto=False):
    """Item 8 (2026-10-26): every decision, overnight or not, at the moment it is taken, with the
    options it beat and what undoing it costs. A review file's "decision" footer is not enough.
    `auto`: a pick made without the owner, with an id (A<n>) they review."""
    if auto:
        need_folder(f)
    line = (f'- {time.strftime("%Y-%m-%d %H:%M")} · {by}' + (f' · auto {next_id(f, "A")}' if auto else '')
            + (f' · [{task}]' if task else '')
            + f' · {text.strip()} · alternatives: {alt.strip()} · revert: {revert.strip()}')
    if folder(f):
        with open(sibling(f, 'decisions'), 'a') as fh:
            fh.write(line + '\n')
    else:
        s = open(f).read()
        m = re.search(r'^## Decisions\s*\n(.*?)(?=^## |\Z)', s, re.M | re.S)
        if not m:
            sys.exit(f'{f} has no "## Decisions" section')
        s = s[:m.end(1)].rstrip('\n') + '\n' + line + '\n\n' + s[m.end(1):]
        open(f, 'w').write(s)
    print(line)
    if auto:
        refresh_now(f)


def retire(f, task):
    """A merged task's decisions are done: they move from decisions.md to history.md. An auto pick
    the owner has not reviewed, or a hold they have not answered, stays until they have."""
    d = sibling(f, 'decisions')
    if not os.path.exists(d):
        return
    tag = f' · [{task}] · '
    lines = open(d).read().splitlines(keepends=True)
    done = [l for l in lines if tag in l and not (ITEM.search(l) and not REVIEWED.search(l))]
    if done:
        open(d, 'w').write(''.join(l for l in lines if l not in done))
        history(f, f'## Decisions done: {task} merged {time.strftime("%Y-%m-%d %H:%M")}\n\n' + ''.join(done))
        print(f'{len(done)} decision{"s" * (len(done) != 1)} on {task} moved to history.md')


# Auto mode (the owner, 2026-10-26 00:38, asleep: "pick your recommendation, record why and the
# alternatives, keep going; wait for me where undoing it later costs too much"). That night's 6
# picks were sound; the gap was finding them in a 118 KB ledger. So each pick (A<n>) and each hold
# (W<n>) is a decisions.md line with an id, and now.md opens with both lists until they review them.
HOLDS = {
    'schema': 'schema or migrations',
    'deploy': 'CI or deploy',
    'security': 'security policy',
    'product': 'product direction (a feature-sized choice)',
    'prod': 'reaches prod or real people',
    'cost': 'undoing it later costs too much',
}
ITEM = re.compile(r' · (auto A|waits W)(\d+) · ')
REVIEWED = re.compile(r' · (?:ok|overridden|answered) \d\d-\d\d \d\d:\d\d')
AUTO_LINE = re.compile(r'^- \S+ \S+ · [^·]+? · auto (?P<id>A\d+) · (?:\[(?P<task>[^\]]+)\] · )?(?P<text>.*?)'
                       r' · alternatives: (?P<alt>.*?) · revert: (?P<revert>.*?)(?: · (?:ok|overridden) \d.*)?$')
WAIT_LINE = re.compile(r'^- \S+ \S+ · [^·]+? · waits (?P<id>W\d+) · (?:\[(?P<task>[^\]]+)\] · )?(?P<q>.*?)'
                       r' · options: (?P<options>.*?) · rec: (?P<rec>.*?) · held: (?P<held>.*?)(?: · answered \d.*)?$')
NOW_AUTO = re.compile(r'<!-- auto -->.*?<!-- /auto -->\n*', re.S)


def need_folder(f):
    if not folder(f):
        sys.exit('auto mode needs a release folder (2.12.0 on): ledger.py init .coordinate/releases/<R> <R>')


def auto_on(f):
    """(on, since) from the latest AUTO row."""
    on, since = False, None
    for t, _, _, ev in rows(f):
        m = re.match(r'AUTO (on|off)\b', ev.strip())
        if m:
            on, since = m.group(1) == 'on', t
    return on, since


def set_auto(f, on):
    """The owner's `/coordinate auto R`: the rule written once, kept in now.md so a resumed or woken
    session stays in auto mode."""
    need_folder(f)
    add(f, '-', 'owner', f'AUTO {"on" if on else "off"}')
    if on:
        decide(f, 'auto mode on: the coordinator picks its recommendation where undoing it later is '
                  'cheap and records each pick (decide --auto); what the hold rule names waits for '
                  'The owner (decide --waits, SKILL.md §Auto mode)',
               'a watched session: every choice waits for the owner', 'ledger.py auto <ledger> off', by='owner')
    refresh_now(f)


def next_id(f, letter):
    text = ''.join(open(p).read() for p in (sibling(f, 'decisions'), sibling(f, 'history')) if os.path.exists(p))
    return f'{letter}{max((int(n) for k, n in ITEM.findall(text) if k.endswith(letter)), default=0) + 1}'


def items(f, kind=None, unreviewed=False):
    """decisions.md lines with an id -> [(id, line)]; kind 'auto' or 'waits'."""
    d = sibling(f, 'decisions')
    out = []
    for l in (open(d).read().splitlines() if os.path.exists(d) else []):
        m = ITEM.search(l)
        if m and (kind is None or m.group(1).startswith(kind)) and not (unreviewed and REVIEWED.search(l)):
            out.append((m.group(1)[-1] + m.group(2), l))
    return out


def wait(f, question, options, rec, hold, task=None):
    """A choice held for the owner (W<n>): the options and the coordinator's recommendation."""
    need_folder(f)
    if hold not in HOLDS:
        sys.exit(f'--hold is one of: {", ".join(f"{k} ({v})" for k, v in HOLDS.items())}')
    line = (f'- {time.strftime("%Y-%m-%d %H:%M")} · coordinator · waits {next_id(f, "W")}'
            + (f' · [{task}]' if task else '')
            + f' · {question.strip()} · options: {options.strip()} · rec: {rec.strip()} · held: {HOLDS[hold]}')
    with open(sibling(f, 'decisions'), 'a') as fh:
        fh.write(line + '\n')
    print(line)
    refresh_now(f)


def auto_block(f):
    """The top of now.md while auto mode is on or anything waits on the owner's review."""
    on, since = auto_on(f)
    picks, waits = items(f, 'auto', True), items(f, 'waits', True)
    if not (on or picks or waits):
        return ''
    out = ['<!-- auto -->']
    if on:
        out.append(f'**Auto mode is on** (since {since}): pick and record; hold what SKILL.md §Auto mode '
                   'holds. A resumed or woken session stays in it.\n')
    if picks:
        out.append(f'## Decided for you ({len(picks)})\n')
        for i, l in picks:
            m = AUTO_LINE.match(l)
            out.append(f'- {i}' + (f' [{m["task"]}]' if m["task"] else '') + f' {m["text"]} · revert: {m["revert"]}'
                       if m else l)
        out.append('\nYou: ok or override each (`ledger.py review <ledger> A<n> ok`).\n')
    if waits:
        out.append(f'## Waiting for you ({len(waits)})\n')
        for i, l in waits:
            m = WAIT_LINE.match(l)
            out += ([f'- Q: [{i}]' + (f' [{m["task"]}]' if m["task"] else '') + f' {m["q"]} (held: {m["held"]})',
                     f'  Options: {m["options"]}', f'  Rec: {m["rec"]}'] if m else [l])
        out.append('')
    return '\n'.join(out + ['<!-- /auto -->']) + '\n\n'


def refresh_now(f):
    """Rebuild the auto lists at the top of now.md, under its title."""
    n = sibling(f, 'now')
    if not folder(f) or not os.path.exists(n):
        return
    title, _, body = NOW_AUTO.sub('', open(n).read()).partition('\n')
    open(n, 'w').write(f'{title}\n\n{auto_block(f)}{body.lstrip(chr(10))}')


def review(f, ident, verdict, text=None, revert=None):
    """The owner's review: `A<n> ok`, `A<n> override` (their decision replaces the pick) or `W<n>` with their
    choice. An override or an answer is their own decision row; the reviewed line it replaces moves
    to history.md."""
    need_folder(f)
    hit = [l for i, l in items(f) if i == ident]
    if not hit:
        sys.exit(f'no {ident} in {sibling(f, "decisions")}')
    line = hit[0]
    if REVIEWED.search(line):
        sys.exit(f'{ident} is already reviewed: {line}')
    when = time.strftime('%m-%d %H:%M')
    if ident[0] == 'A' and verdict == 'ok':
        mark(f, line, f'{line} · ok {when}')
        m = AUTO_LINE.match(line)
        task = m['task'] if m else None
        if task and any(t.strip() == task and ev.strip().startswith('MERGED') for _, t, _, ev in rows(f)):
            retire(f, task)
    elif ident[0] == 'A' and verdict == 'override':
        m = AUTO_LINE.match(line)
        if not (text and revert):
            sys.exit('override needs --revert "<what undoing it costs>" and the owner\'s decision')
        mark(f, line, None, f'## {ident} overridden {when}\n\n{line} · overridden {when}\n')
        decide(f, text, f'{ident}: {m["text"] if m else line}', revert, m['task'] if m else None, by='owner')
    elif ident[0] == 'W':
        m = WAIT_LINE.match(line)
        if not revert:
            sys.exit('an answer needs --revert "<what undoing it costs>" and the owner\'s choice')
        others = [o.strip() for o in (m['options'] if m else '').split('|') if o.strip() and o.strip() != verdict]
        mark(f, line, None, f'## {ident} answered {when}\n\n{line} · answered {when}: {verdict}\n')
        decide(f, f'{m["q"] if m else ident}: {verdict}', ' | '.join(others) or '-', revert,
               m['task'] if m else None, by='owner')
    else:
        sys.exit('review <ledger> A<n> ok | A<n> override --revert "<cost>" "<decision>" | W<n> --revert "<cost>" "<choice>"')
    refresh_now(f)


def mark(f, line, new, moved=None):
    """Replace a decisions.md line (new None: drop it, `moved` going to history.md)."""
    d = sibling(f, 'decisions')
    lines = open(d).read().splitlines(keepends=True)
    open(d, 'w').write(''.join((new + '\n' if new else '') if l.rstrip('\n') == line else l for l in lines))
    if moved:
        history(f, moved)


def questions(f):
    """[{question, options, recommended}] from the park's Q:/Options:/Rec: items."""
    out, cur = [], None
    for line in parked_text(f).splitlines():
        s = line.strip().lstrip('-* ').strip()
        if s.startswith('Q:'):
            cur = {'question': s[2:].strip(), 'options': [], 'recommended': None}
            out.append(cur)
        elif cur and s.startswith('Options:'):
            cur['options'] = [o.strip() for o in s[8:].split('|') if o.strip()]
        elif cur and s.startswith('Rec:'):
            cur['recommended'] = s[4:].strip()
    return out


def stamp(t):
    """A row's "MM-DD HH:MM" as epoch seconds, in this year (a release does not span New Year's)."""
    return time.mktime(time.strptime(f'{time.strftime("%Y")}-{t}', '%Y-%m-%d %H:%M'))


def kvs(ev):
    return {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|\S+)', ev)}


def is_review_of(name, task):
    m = re.match(r'^(?:code-)?(?:review|rereview|critique)-(.+)$', name)
    return bool(m) and task in re.split(r'[-+]', m.group(1))


AGENTS_DIR = os.path.expanduser('~/.claude/coordinate/agents')


def claude_cost(f, task, agents_dir=None):
    """Claude tokens and ≈$ for <task>: the coordinator-status mod's closed subagent rows
    (agents/<session>.json) whose description starts with the task id or a review of it, from a
    session in this repo, ended between the task's first row and its merge; plus the EXITED rows
    claude_review.py writes (a `claude -p` reviewer is no subagent). '?' with neither."""
    d = agents_dir or AGENTS_DIR
    mine = [(t, ev.strip()) for t, k, _, ev in rows(f) if k.strip() == task or is_review_of(k.strip(), task)]
    ran = [ev for _, ev in mine if ev.startswith('EXITED') and 'claude_tokens=' in ev]
    tokens = sum(int(n) for ev in ran for n in re.findall(r'\bclaude_tokens=(\d+)', ev))
    usd = sum(float(n) for ev in ran for n in re.findall(r'\bclaude_usd=(\d+(?:\.\d+)?)', ev))
    if not os.path.isdir(d):
        return (tokens, f'{usd:.2f}') if ran else ('?', '?')
    repo = os.path.realpath(f).split(os.sep + '.coordinate' + os.sep)[0]
    stamps = [stamp(t) for t, _ in mine]
    lo, hi = (min(stamps) - 120, max(stamps) + 120) if stamps else (0, float('inf'))
    for name in os.listdir(d):
        try:
            s = json.load(open(os.path.join(d, name)))
        except (OSError, ValueError):
            continue
        cwd = os.path.realpath(s.get('cwd') or '')
        if cwd != repo and not cwd.startswith(repo + os.sep):
            continue
        for a in s.get('agents', []):
            first = (a.get('description') or '').split(' ', 1)[0]
            if (first == task or is_review_of(first, task)) and lo <= a.get('ended', 0) <= hi:
                tokens += a.get('tokens', 0)
                usd += a.get('usd', 0)
    return tokens, f'{usd:.2f}'


def outcome(f, task, five_hour=None, agents_dir=None):
    """ROADMAP item 6: one row per merged task with what a router needs to learn from. Claude
    tokens and ≈$ come from the mod (claude_cost); Devin's runs are free or paid quota, not here."""
    rs = [(t, k.strip(), ev.strip()) for t, k, _, ev in rows(f)]
    mine = [(t, ev) for t, k, ev in rs if k == task]
    routes = [ev.split()[2] for _, ev in mine if ev.startswith('ROUTE ->')]
    first = next((kvs(ev) for _, ev in mine if ev.startswith('ROUTE ->')), {})
    launched = [t for t, ev in mine if ev.startswith('LAUNCHED')]
    merged = [t for t, ev in mine if ev.startswith('MERGED')]
    bugs = sum(int(b) for _, k, ev in rs if is_review_of(k, task) for b in re.findall(r'\bbugs=(\d+)', ev))
    reds = sum(1 for _, ev in mine if re.match(r'GATES (red|RED)', ev))
    wall = '?'
    if launched:
        end = stamp(merged[-1]) if merged else time.time()
        mins = max(0, int(end - stamp(launched[0])) // 60)
        wall = f'{mins // 60}h{mins % 60:02d}'
    now = '?' if five_hour is None else round(five_hour)
    tokens, usd = claude_cost(f, task, agents_dir)
    return (f'OUTCOME routes={">".join(routes) or "?"} rounds={len(launched)} bugs={bugs} gate_reds={reds} '
            f'wall={wall} 5h_at_route={first.get("5h", "?")} 5h_now={now} claude_tokens={tokens} claude_usd={usd}')


OUTCOME_COLS = ('release', 'task', 'routes', 'posture', '7d', 'week', '5h_at_route', 'devin_paid',
                'offposture', 'rounds', 'bugs', 'gate_reds', 'wall', '5h_now', 'claude_tokens', 'claude_usd')


def outcomes(files):
    """Every merged task as one row: its OUTCOME row, or one computed from the rows for ledgers
    written before OUTCOME rows existed."""
    print('\t'.join(OUTCOME_COLS))
    for f in files:
        rs = [(k.strip(), ev.strip()) for _, k, _, ev in rows(f)]
        for task in dict.fromkeys(k for k, ev in rs if ev.startswith('MERGED')):
            got = [ev for k, ev in rs if k == task and ev.startswith('OUTCOME')]
            o = kvs(got[-1] if got else outcome(f, task))
            r = next((kvs(ev) for k, ev in rs if k == task and ev.startswith('ROUTE ->')), {})
            row = {'release': release_of(f), 'task': task,
                   **{k: r.get(k, '') for k in ('posture', '7d', 'week', 'devin_paid', 'offposture')}, **o}
            print('\t'.join(str(row.get(c, '')) for c in OUTCOME_COLS))


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == 'init' and len(a) == 3:
        init(a[1], a[2])
        sys.exit()
    if cmd == 'outcomes' and len(a) >= 2:
        outcomes([resolve(x) for x in a[1:]])
        sys.exit()
    if len(a) < 2:
        sys.exit(__doc__)
    f = resolve(a[1])
    if cmd == 'add' and len(a) >= 5:
        add(f, a[2], a[3], ' '.join(a[4:]))
    elif cmd == 'park' and len(a) == 4:
        park(f, sys.stdin.read() if a[2] == '-' else open(a[2]).read(), a[3])
    elif cmd == 'decide' and '--waits' in a:
        rest = [x for x in a[2:] if x != '--waits']
        task, options, rec, hold = opt(rest, '--task'), opt(rest, '--options'), opt(rest, '--rec'), opt(rest, '--hold')
        if not (options and rec and hold and rest):
            sys.exit('decide --waits needs --options "a | b", --rec "<pick> (why)", --hold <kind> and the question')
        wait(f, ' '.join(rest), options, rec, hold, task)
    elif cmd == 'decide':
        rest = [x for x in a[2:] if x != '--auto']
        task, by = opt(rest, '--task'), opt(rest, '--by', 'coordinator')
        alt, revert = opt(rest, '--alt'), opt(rest, '--revert')
        if not (alt and revert and rest):
            sys.exit('decide needs --alt "<the other options>", --revert "<what undoing it costs>" and the decision')
        decide(f, ' '.join(rest), alt, revert, task, by, auto='--auto' in a)
    elif cmd == 'auto' and len(a) == 3 and a[2] in ('on', 'off'):
        set_auto(f, a[2] == 'on')
    elif cmd == 'review' and len(a) >= 4:
        rest = a[2:]
        revert = opt(rest, '--revert')
        ident = rest.pop(0)
        if ident.startswith('A') and rest[:1] == ['override']:
            review(f, ident, 'override', ' '.join(rest[1:]), revert)
        else:
            review(f, ident, ' '.join(rest), revert=revert)
    elif cmd == 'decisions':
        flags = a[2:]
        kind = 'auto' if '--auto' in flags else 'waits' if '--waits' in flags else None
        for _, l in items(f, kind, '--unreviewed' in flags):
            print(l)
    elif cmd == 'state' and len(a) == 2:
        state(f)
    elif cmd == 'merges' and len(a) == 4 and a[2] == '--since':
        merges(f, a[3])
    elif cmd == 'questions' and len(a) == 2:
        print(json.dumps(questions(f), indent=1))
    else:
        sys.exit(__doc__)
