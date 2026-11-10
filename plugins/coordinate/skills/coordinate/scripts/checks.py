"""The owner's eyeball checks, one list per release, so a report points at it instead of repeating it.

  eyeball.py checks add      <repo> --release R --task T --where server:port "<what to look at>"
  eyeball.py checks list     <repo> --release R [--all]   the open checks: waiting on them or mid fix round
  eyeball.py checks ok       <repo> --release R <id>... | --agent-pass   the owner looked; it is fine
  eyeball.py checks feedback <repo> --release R <id> "<what they said>"
  eyeball.py checks fixed    <repo> --release R <id> ["<what landed>"]   the fix round landed;
                                                the check waits on the owner again (state recheck)
  eyeball.py checks import   <repo> --release R <report>  the agent's verdicts (`eyeball.py verify`)
  eyeball.py checks waiting  <repo> --release R           one line for the end of a report

`<release_dir>/<R>/eyeball.md` holds an ADD line per check, then an OK or FEEDBACK line when the owner
answers. A check is open until one of those lands; an OK moves the check's lines to the release's
history.md, so the file holds only what still waits on them. Every coordinator report ends with
the `waiting` line instead of repeating the checks; the mod's 👁 marker reads the same file. A
release begun before 2.12.0 keeps `.coordinate/eyeball/<R>.md`, append only. The owner may append
`- OK <id> | <MM-DD HH:MM> | <note>` or `- FEEDBACK <id> | ...` by hand: the newest line decides.

Machine eyeball (2.18.0): an agent with a browser checks what it can and writes a report; `import`
reads its `## #<id> PASS|FAIL|PARTIAL|NEEDS OWNER` headings into AGENT lines, states `agent-pass`,
`agent-flag` (FAIL, PARTIAL) and `needs-human`. **An agent verdict never closes a check**: only
the owner's OK does. `ok --agent-pass` is their bulk confirm of every agent-pass check, after they have read
the report.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad

LINE = re.compile(r'^- (ADD|OK|FEEDBACK|FIXED|AGENT) (\d+) \| (.*)$')
# `NEEDS <anyone>`: reports written before 2.30.0 named the owner.
VERDICT = re.compile(r'^## #(\d+)\s+(PASS|FAIL|PARTIAL|NEEDS [A-Z]+)\b(.*)$')
AGENT_STATE = {'PASS': 'agent-pass', 'FAIL': 'agent-flag', 'PARTIAL': 'agent-flag'}
# Waiting on the owner vs on the coordinator: `feedback` is their words mid fix round; `fixed` moves
# the check to `recheck`, their to look at again. Every state but ok keeps a check in the file.
YOU = ('open', 'agent-pass', 'agent-flag', 'needs-human', 'recheck')
WAITING = YOU + ('feedback',)


def path(a, release):
    if ad.in_folder(a, release):
        return os.path.join(ad.release_path(a, release), 'eyeball.md')
    return os.path.join(os.path.dirname(a['ledger_dir']), 'eyeball', f'{release}.md')


def history_path(f):
    return os.path.join(os.path.dirname(f), 'history.md') if os.path.basename(f) == 'eyeball.md' else None


def passed(f, ids):
    """Move checks that came back OK out of eyeball.md, into history.md."""
    h = history_path(f)
    if not h:
        return
    lines = open(f).read().splitlines(keepends=True)
    gone = [l for l in lines if (m := LINE.match(l.rstrip('\n'))) and int(m.group(2)) in ids]
    open(f, 'w').write(''.join(l for l in lines if l not in gone))
    import ledger as lg
    lg.history(os.path.join(os.path.dirname(f), 'timeline.md'),
               f'## Eyeball checks passed {ad.now()}\n\n' + ''.join(gone))


def append(f, line):
    new = not os.path.exists(f)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'a') as fh:
        if new:
            fh.write('# Eyeball checks\n\nWritten by `eyeball.py checks`. A check is open until the owner answers.\n\n')
        fh.write(line + '\n')


def load(f):
    """{id: {task, where, what, state, note, at, report}} in id order. The latest line decides: an
    agent verdict after the owner's feedback is the re-check of a fix round."""
    checks = {}
    if os.path.exists(f):
        for l in open(f):
            m = LINE.match(l.rstrip('\n'))
            if not m:
                continue
            kind, i, rest = m.group(1), int(m.group(2)), m.group(3).split(' | ')
            if kind == 'ADD':
                checks[i] = {'at': rest[0], 'task': rest[1], 'where': rest[2], 'what': ' | '.join(rest[3:]),
                             'state': 'open', 'note': '', 'report': None}
            elif i in checks and kind == 'AGENT':
                checks[i].update(state=rest[1], note=rest[2] if len(rest) > 2 else '',
                                 report=rest[3] if len(rest) > 3 else None)
            elif i in checks:
                checks[i]['state'] = 'recheck' if kind == 'FIXED' else kind.lower()
                checks[i]['note'] = ' | '.join(rest[1:])
    return checks


def show(i, c):
    tail = f'  -> {c["note"]}' if c['note'] else ''
    return f'#{i} [{c["state"]}] {c["task"]} @ {c["where"]}: {c["what"]}{tail}'


def next_id(f, checks):
    """Ids stay unique after passed checks leave the file."""
    h = history_path(f)
    moved = load(h) if h and os.path.exists(h) else {}
    return max([*checks, *moved], default=0) + 1


def verdicts(report):
    """{id: (state, first evidence line)} from an agent report's headings."""
    out, cur = {}, None
    for l in open(report).read().splitlines():
        m = VERDICT.match(l.strip())
        if m:
            cur = int(m.group(1))
            out[cur] = [AGENT_STATE.get(m.group(2), 'needs-human'), m.group(3).strip(' -—:()')]
        elif l.startswith('## '):
            cur = None
        elif cur is not None and l.strip() and not out[cur][1] and not l.startswith('>'):
            out[cur][1] = l.strip()
    return {i: (s, re.sub(r'\s+', ' ', n).replace('|', '/')[:160]) for i, (s, n) in out.items()}


def waiting_line(f, checks):
    """One line for the end of a report: what waits on the owner vs what is mid fix round, then the
    file path (it is how they open the full checks in an editor)."""
    states = [c['state'] for c in checks.values()]
    you = [s for s in states if s in YOU]
    fix = [c['task'] for c in checks.values() if c['state'] == 'feedback']
    parts = []
    if you:
        detail = ', '.join(f'{you.count(s)} {s}' for s in YOU if s in you)
        parts.append(f'waiting on you: {detail}')
    if fix:
        parts.append(f'in a fix round: {len(fix)} ({", ".join(sorted(set(fix)))})')
    if not parts:
        return 'no eyeball checks waiting'
    return ' · '.join(parts) + f' · {f}'


def run(args):
    if not args:
        sys.exit(__doc__)
    cmd = args.pop(0)
    if cmd not in ('add', 'list', 'ok', 'feedback', 'fixed', 'import', 'waiting') or not args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    if not release:
        sys.exit(__doc__)
    a, _ = ad.load(repo)
    f = path(a, ad.resolve_release(a, release))
    checks = load(f)
    if cmd == 'add':
        task, where = ad.opt(args, '--task'), ad.opt(args, '--where')
        what = ' '.join(args)
        if not (task and where and what):
            ad.die('checks add needs --task, --where and the text of what to look at')
        i = next_id(f, checks)
        append(f, f'- ADD {i} | {ad.now()} | {task} | {where} | {what}')
        print(f'check #{i} added: {task} @ {where}')
        import eyeball
        if h := eyeball.howto(a, ad.resolve_release(a, release)):
            print(f'how to look: {h}')
    elif cmd == 'list':
        shown = [(i, c) for i, c in checks.items() if '--all' in args or c['state'] in WAITING]
        print('\n'.join(show(i, c) for i, c in shown) or 'no open checks')
    elif cmd == 'ok':
        ids = [str(i) for i, c in checks.items() if c['state'] == 'agent-pass'] if '--agent-pass' in args \
            else args
        for x in ids:
            if not x.isdigit() or int(x) not in checks:
                ad.die(f'no check #{x} in {f}')
            append(f, f'- OK {x} | {ad.now()}' + (' | agent-pass confirmed' if '--agent-pass' in args else ''))
            print(f'check #{x} ok')
        if not ids:
            print('no agent-pass checks to confirm')
        passed(f, {int(x) for x in ids})
    elif cmd == 'feedback':
        if len(args) < 2 or not args[0].isdigit() or int(args[0]) not in checks:
            ad.die('checks feedback <id> "<what they said>"')
        append(f, f'- FEEDBACK {args[0]} | {ad.now()} | {" ".join(args[1:])}')
        print(f'check #{args[0]} feedback recorded: act on it')
    elif cmd == 'fixed':
        if not args or not args[0].isdigit() or int(args[0]) not in checks:
            ad.die('checks fixed <id> ["<what landed>"]: the fix round landed, '
                   'the check waits on the owner again')
        append(f, f'- FIXED {args[0]} | {ad.now()}' + (f' | {" ".join(args[1:])}' if args[1:] else ''))
        print(f'check #{args[0]} fix landed: recheck waits on the owner')
    elif cmd == 'import':
        if len(args) != 1 or not os.path.exists(args[0]):
            ad.die('checks import <report>: the agent report from `eyeball.py verify`')
        report = os.path.abspath(args[0])
        found = verdicts(report)
        for i, (state, note) in sorted(found.items()):
            if i not in checks:
                print(f'#{i}: not an open check in {f}, skipped')
                continue
            append(f, f'- AGENT {i} | {ad.now()} | {state} | {note} | {report}')
            print(f'#{i} {state}: {note}')
        missing = [i for i, c in checks.items() if c['state'] == 'open' and i not in found]
        if missing:
            print('no verdict in the report for: ' + ', '.join(f'#{i}' for i in missing))
        print(waiting_line(f, load(f)))
    else:
        # An OK the owner wrote in the file by hand (SKILL.md §6): tidy it as `checks ok` would.
        by_hand = {i for i, c in checks.items() if c['state'] == 'ok'}
        if by_hand:
            passed(f, by_hand)
            for i in sorted(by_hand):
                print(f'#{i} ok in the file, moved to history')
            checks = load(f)
        print(waiting_line(f, checks))
