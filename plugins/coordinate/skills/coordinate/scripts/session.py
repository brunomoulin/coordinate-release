"""The coordinator's own budget: context size against limits that follow the budget posture.

  session.py [<repo-or-worktree>] [--release R|auto]

Limits (adapter `session_limits`):
  soft  450k: start no new wave. Merges in flight, started reviews and the close-out continue.
  hard  650k: park after the current merge. TIGHT posture lowers it to 400k (`tight_tokens`);
              CRITICAL parks after the current merge whatever the context.
  merges: a warning at `merges_warn`, never a stop.
Close-out in this session when `closeout_tokens` (60k) still fit under the hard limit.

Exit 0 = keep going; 4 = soft limit (no new wave); 3 = park: finish the current merge, gate main,
park with `ledger.py park` (now.md and a PARKED row), then end the session.
"""
import calendar, glob, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import budget


def transcript():
    sid = os.environ.get('CLAUDE_CODE_SESSION_ID')
    if sid:
        hits = glob.glob(os.path.expanduser(f'~/.claude/projects/*/{sid}.jsonl'))
        if hits:
            return hits[0]
    files = glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl'))
    return max(files, key=os.path.getmtime) if files else None


def context_and_start(path):
    ctx, start = 0, None
    for line in open(path):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if start is None and o.get('timestamp'):
            start = o['timestamp']
        u = (o.get('message') or {}).get('usage') if o.get('type') == 'assistant' else None
        if u:
            ctx = u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + \
                u.get('cache_creation_input_tokens', 0)
    return ctx, start


def limits(a, posture):
    """(soft, hard, park_now) for this posture."""
    lim = a['session_limits']
    soft, hard = lim['soft_tokens'], lim['hard_tokens']
    if posture == 'TIGHT':
        hard = min(hard, lim['tight_tokens'])
        soft = min(soft, int(hard * 0.85))
    return soft, hard, posture == 'CRITICAL'


def merges_since(a, release, start):
    if not (release and start):
        return None
    lf = ad.ledger_file(a, release)
    if not os.path.exists(lf):
        return None
    # transcript timestamps are UTC ISO; ledger rows are local "MM-DD HH:MM"
    st = time.localtime(calendar.timegm(time.strptime(start[:19], '%Y-%m-%dT%H:%M:%S')))
    since = time.strftime('%m-%d %H:%M', st)
    import ledger
    return sum(1 for r, _, _, ev in ledger.rows(lf) if r >= since and ev.strip().startswith('MERGED'))


def main():
    args = sys.argv[1:]
    release = ad.opt(args, '--release')
    a, _, release = ad.load_release(args[0] if args else '.', release)
    t = transcript()
    if not t:
        ad.die('no transcript found')
    ctx, start = context_and_start(t)
    merges = merges_since(a, release, start)
    b = budget.summary(a)
    soft, hard, park_now = limits(a, b['posture'])
    lim = a['session_limits']
    print(f"context {ctx // 1000}k · soft {soft // 1000}k · hard {hard // 1000}k"
          f" · merges this session {'?' if merges is None else merges}")
    print(b['line'])
    if merges is not None and merges >= lim['merges_warn']:
        print(f'note: {merges} merges this session (warning only; context decides)')
    fits = ctx + lim['closeout_tokens'] <= hard
    print(f"close-out fits in this session: {'yes' if fits else 'no: close out in a fresh session'}")
    if park_now or ctx >= hard:
        why = 'CRITICAL posture' if park_now else f'context {ctx // 1000}k >= hard {hard // 1000}k'
        print(f'PARK ({why}): finish the current merge, gate main, `ledger.py park` (questions as'
              f' Q:/Options:/Rec:), end the session')
        sys.exit(3)
    if ctx >= soft:
        print(f'SOFT LIMIT ({ctx // 1000}k >= {soft // 1000}k): start no new wave; finish merges, '
              f'started reviews and the close-out')
        sys.exit(4)


if __name__ == '__main__':
    main()
