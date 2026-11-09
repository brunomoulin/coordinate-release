"""Budget posture: how hard to spend the Claude and Devin weekly subscriptions right now.

  budget.py [<repo>] [--release R|auto] [--json]    posture, pace, routes allowed, open questions
                                                    (with a release: its /coordinate settings too)
  budget.py devin <pct|exhausted> [--resets DATE]   record the Devin paid (Fusion) quota you saw
  budget.py answer <signal> "<answer>"              record the owner's answer to a budget question
  budget.py route <repo> --release R <task> <route> [--why TEXT] [--override REASON]
                                                    write a ROUTE ledger row; a route the posture
                                                    does not allow is refused without --override

Signals: Claude's 5-hour and 7-day windows and their reset times from
`~/.claude/coordinate/usage.json` (the coordinator-status mod writes it); the Devin paid quota from `devin-budget.json` (`budget.py devin`, or set to exhausted
when a Devin log says it ran out). SWE-2 is free: it is bounded by `concurrency.devin`, not quota.

pace = 7-day % used / % of the week elapsed (1.0 spends exactly 100% by the reset), the elapsed %
floored at `pace_floor_pct` (25) so a fresh week's first spend does not read as overspending.
Postures, from the weekly window only (thresholds in adapter `budget`): CRITICAL 7d >= 90%;
TIGHT pace > 1.1; SURPLUS pace < 0.7, or reset < 24 h with 7d < 70%; else ON PACE. The 5-hour
window never sets the posture: it gates each Claude build through the fit check below and, near
its cap, drives the park-and-wake of SKILL.md §8. A Claude build launches only
when it fits: the 5h window plus its estimate (`build_cost_5h`) stays under `five_hour_fit_pct`
(85), whatever the posture, since the coordinator shares that window; TIGHT also allows ON PACE's
Claude builds when what the week has left after the build (`build_cost_7d`) still covers
`tight_headroom` (0.75) of an on-pace share of the rest of the week. A missing signal prints a
QUESTION for the wave's batch, once per week per signal; `budget.py answer` records the answer
until the next reset. Exit 0 always (it informs; session.py enforces).
"""
import datetime as dt, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad

USAGE = os.path.join(ad.USER_STATE, 'usage.json')
DEVIN = os.path.join(ad.USER_STATE, 'devin-budget.json')
ANSWERS = os.path.join(ad.USER_STATE, 'budget-answers.json')
# One file per session with the mod loaded: {session, cwd, samples: [[unix s, usd so far, 5h %]]}.
SESSIONS = os.path.join(ad.USER_STATE, 'sessions')
HOUR = 3600
FIVE_HOUR_FRESH = 15 * 60
SEVEN_DAY_FRESH = 6 * 3600
WEEK = 7 * 24 * 3600
# A Devin log line saying the paid quota ran out.
DEVIN_OUT = re.compile(r'out of (quota|credits|usage)|quota (exceeded|exhausted|has been exhausted)|insufficient (quota|credits)'
                       r'|usage limit (reached|exceeded)|no (remaining )?(ACUs|credits)', re.I)

# Routes per posture: builds, reviews, critiques. Names match adapter `budget.overrides` keys.
# devin_fusion (a build too hard for SWE-2) and fusion_review spend the paid Devin quota, not
# Claude's: any posture.
# sonnet_review: a narrow re-review of work Claude did not build (the owner's Mix, pilot 2.11.0).
# swe2_review: SWE-2 critiques and re-reviews Claude-built work; free, so every posture (it found
# 466's one real UI defect in pilot 2.11.0). Never the review before merge: that stays Opus or Fusion.
ROUTES = {
    'SURPLUS': {'build': ['devin_swe2', 'devin_fusion', 'haiku_implement', 'sonnet_implement', 'opus_implement'],
                'review': ['opus_review', 'fusion_review', 'sonnet_review', 'swe2_review'],
                'critique': ['sonnet_critique', 'swe2_review'], 'eyeball': ['devin_eyeball', 'sonnet_eyeball'],
                'note': 'Devin slots full first, then Claude implementers by task: Haiku mechanical, '
                        'Sonnet UI/medium, Opus hard/security. Re-review when round 1 found 3+.'},
    'ON PACE': {'build': ['devin_swe2', 'devin_fusion', 'sonnet_implement'], 'review': ['opus_review', 'fusion_review', 'sonnet_review', 'swe2_review'],
                'critique': ['sonnet_critique', 'swe2_review'], 'eyeball': ['devin_eyeball'],
                'note': 'Devin (all slots); Sonnet for UI.'},
    'TIGHT': {'build': ['devin_swe2', 'devin_fusion'], 'review': ['fusion_review', 'sonnet_review', 'swe2_review'], 'critique': ['sonnet_critique', 'swe2_review'],
              'eyeball': ['devin_eyeball'], 'note': 'Devin; a Sonnet build only when it fits the week; reviews on Fusion (paid Devin quota).'},
    'CRITICAL': {'build': ['devin_swe2', 'devin_fusion'], 'review': ['fusion_review', 'park_review', 'swe2_review'], 'critique': ['swe2_review'],
                 'eyeball': ['devin_eyeball'], 'note': 'Devin only, chained with chain.py so they run without Claude turns; '
                         'Fusion review, else park it. Park the session after the current merge.'},
}
# budget.mode "off" (/coordinate settings): every route, no fit check, no park; spend still recorded.
ROUTES['OFF'] = {**ROUTES['SURPLUS'], 'note': 'Budget off: every route allowed; spend is still recorded on ROUTE rows.'}
KINDS = ('build', 'review', 'critique', 'eyeball')
# Every route a kind can take, in the order the postures list them: where a ticked route joins.
KIND_ROUTES = {k: list(dict.fromkeys(x for v in ROUTES.values() for x in v[k])) for k in KINDS}
# routing.default_builder -> its build route.
DEFAULT_ROUTE = {'devin': 'devin_swe2', 'sonnet': 'sonnet_implement', 'haiku': 'haiku_implement',
                 'opus': 'opus_implement'}
CLAUDE_BUILDS = ('haiku_implement', 'sonnet_implement', 'opus_implement')

ALL_ROUTES = {'devin_swe2', 'devin_fusion', 'haiku_implement', 'sonnet_implement', 'opus_implement',
              'opus_review', 'fusion_review', 'sonnet_review', 'swe2_review', 'sonnet_critique', 'park_review',
              'devin_eyeball', 'sonnet_eyeball'}
# The machine eyeball (eyeball.py verify): Devin SWE-2 by default, it is free; Sonnet only under
# SURPLUS. The 2.11.0 trial ran on SWE-2.


def infer_route(who, task):
    """A launch with no ROUTE row: its route from the ledger's `who` (2.8.0-2.9.1 left 14 launches
    and 10 review bugs 'unrouted' in the close-out report). None when `who` names no implementer."""
    who, task = who.strip().lower(), task.strip().lower()
    review = task.startswith(('review', 'critique', 'rereview', 're-review'))
    if task.startswith('eyeball') and who.startswith(('devin', 'sonnet')):
        return 'sonnet_eyeball' if who.startswith('sonnet') else 'devin_eyeball'
    if who.startswith(('devin-fusion', 'fusion')):
        return 'fusion_review' if review else 'devin_fusion'
    if who.startswith('devin'):
        return 'swe2_review' if review else 'devin_swe2'
    if who.startswith('sonnet'):
        if task.startswith('critique'):
            return 'sonnet_critique'
        return 'sonnet_review' if review else 'sonnet_implement'
    if who.startswith('opus'):
        return 'opus_review' if review else 'opus_implement'
    if who.startswith('haiku'):
        return 'haiku_implement'
    return None


def _load(p):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return {}


def _save(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    json.dump(d, open(tmp, 'w'), indent=1)
    os.replace(tmp, p)


def _epoch(iso):
    if not iso:
        return None
    try:
        return dt.datetime.fromisoformat(str(iso).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def signals():
    """Every budget signal, None where unknown."""
    u, now = _load(USAGE), time.time()
    age = now - u.get('ts', 0)
    five = u.get('five_hour_pct') if age < FIVE_HOUR_FRESH else None
    five_resets = _epoch(u.get('five_hour_resets_at'))
    if five_resets and five_resets < now:  # that window is over; the next starts at the next message
        five, five_resets = None, None
    seven = u.get('seven_day_pct') if age < SEVEN_DAY_FRESH else None
    resets = _epoch(u.get('seven_day_resets_at'))
    week_pct = None
    if resets:
        if resets < now:  # the window rolled over since the status line last wrote
            seven, resets = None, None
        else:
            week_pct = max(0.0, min(100.0, 100 * (1 - (resets - now) / WEEK)))
    d = _load(DEVIN)
    devin_paid = d.get('pct')
    d_resets = _epoch(d.get('resets'))
    if d_resets and d_resets < now:
        devin_paid = None
    return {'five_hour_pct': five, 'five_hour_resets_at': five_resets,
            'seven_day_pct': seven, 'seven_day_resets_at': resets,
            'week_elapsed_pct': week_pct, 'devin_paid': devin_paid, 'context_tokens': u.get('context_tokens')}


def spend(s, me=None, now=None):
    """The last hour's 5h climb split by session, or None when no other session spent anything.
    The windows are the account's: a climb faster than the coordinator's own work explains may be
    another session's (ROADMAP fix 5). Each session's $ is its cost now minus its newest sample at
    or before the hour; the climb is the 5h % now minus the lowest sample this hour, since the
    window last reset; others get the climb's share their $ are of all $ (models cost the window
    roughly as they cost dollars). `me` is this session (CLAUDE_CODE_SESSION_ID). A file not
    written for a day is removed."""
    now = now or time.time()
    me = me or os.environ.get('CLAUDE_CODE_SESSION_ID')
    try:
        names = [n for n in os.listdir(SESSIONS) if n.endswith('.json')]
    except OSError:
        return None
    resets = s.get('five_hour_resets_at')
    since = max(now - HOUR, resets - 5 * HOUR if resets else 0)
    mine, others, pcts = 0.0, {}, []
    for n in names:
        p = os.path.join(SESSIONS, n)
        d = _load(p)
        smp = d.get('samples') or []
        if not smp or smp[-1][0] < now - 24 * HOUR:
            try:
                os.remove(p)
            except OSError:
                pass
            continue
        if smp[-1][0] < now - HOUR:
            continue
        base = [x for x in smp if x[0] <= now - HOUR]
        usd = smp[-1][1] - (base[-1] if base else smp[0])[1]
        pcts += [x[2] for x in smp if x[0] >= since and x[2] is not None]
        if d.get('session') == me:
            mine += usd
        else:
            label = os.path.basename(d.get('cwd', '').rstrip('/')) or n[:8]
            others[label] = others.get(label, 0.0) + usd
    theirs = sum(others.values())
    if theirs < 0.01:
        return None
    five = s.get('five_hour_pct')
    climb = max(0, five - min(pcts + [five])) if five is not None else None
    share = lambda usd: round(climb * usd / (mine + theirs)) if climb is not None else None
    who = ', '.join(f'{k} ${v:.2f}' for k, v in sorted(others.items(), key=lambda kv: -kv[1]))
    me_txt = f'this one (${mine:.2f})' if me else 'this one (unknown: no CLAUDE_CODE_SESSION_ID)'
    if climb is None:
        line = f'this hour: other sessions ${theirs:.2f} ({who}), {me_txt}'
    else:
        line = (f'this hour 5h +{round(climb)}%: ~{share(theirs)}% by other sessions ({who}), '
                f'~{share(mine)}% by {me_txt}')
    return {'climb': climb, 'mine_usd': mine, 'others': sorted(others.items(), key=lambda kv: -kv[1]),
            'others_pct': share(theirs), 'line': line}


def week_key(s):
    """The current Claude week, named by its reset date; falls back to the ISO week."""
    if s['seven_day_resets_at']:
        return time.strftime('%Y-%m-%d', time.localtime(s['seven_day_resets_at']))
    y, w, _ = dt.date.today().isocalendar()
    return f'{y}-W{w:02d}'


def posture(a, s=None):
    s = s or signals()
    t = a['budget']
    pace = None
    if s['seven_day_pct'] is not None and s['week_elapsed_pct'] is not None:
        # Floored: early in the week a small elapsed % turns any spend into "overspending"
        # (pilot 2.11.0: 7d 10% at 7% elapsed read 1.4, TIGHT, with 90% of the week left).
        pace = s['seven_day_pct'] / max(s['week_elapsed_pct'], t['pace_floor_pct'], 1.0)
    reset_h = (s['seven_day_resets_at'] - time.time()) / 3600 if s['seven_day_resets_at'] else None
    seven = s['seven_day_pct']
    if seven is not None and seven >= t['critical_pct']:
        p = 'CRITICAL'
    elif pace is not None and pace > t['tight_pace']:
        p = 'TIGHT'
    elif (pace is not None and pace < t['surplus_pace']) or \
            (reset_h is not None and seven is not None and reset_h < t['surplus_reset_hours']
             and seven < t['surplus_reset_pct']):
        p = 'SURPLUS'
    else:
        p = 'ON PACE'
    known = seven is not None
    if t.get('mode') == 'off':  # /coordinate settings: budget off
        p = 'OFF'
    return p, pace, known


def misfit(a, p, s, route):
    """Why a Claude build does not fit the windows now, or None when it does.
    5h: the window plus the build's estimate must stay under `five_hour_fit_pct`, or the build runs
    into the cap and stalls the coordinator, who shares the window (2.10.0: Opus builds launched at
    72-75% took it to 99%). A fixed 50% gate made a Sonnet build wait at 59% (pilot 2.11.0).
    7d, TIGHT only: what is left after the build must cover `tight_headroom` of an on-pace share
    of the rest of the week (pilot 2.11.0: 7d 36% at 30.5% refused a Sonnet build worth 1-3%)."""
    if p == 'OFF':
        return None
    t, m = a['budget'], route.split('_')[0]
    five = s['five_hour_pct']
    if five is not None and five + t['build_cost_5h'][m] >= t['five_hour_fit_pct']:
        return (f"5h {round(five)}% + {m} ~{t['build_cost_5h'][m]} >= {t['five_hour_fit_pct']}% "
                f"({reset_text(s)})")
    if p == 'TIGHT':
        seven, week = s['seven_day_pct'], s['week_elapsed_pct']
        if seven is None or week is None:
            return '7d window unknown'
        head = (100 - seven - t['build_cost_7d'][m]) / max(100 - week, 1.0)
        if head < t['tight_headroom']:
            return f"7d headroom {head:.2f} < {t['tight_headroom']} after {m} (~{t['build_cost_7d'][m]}%)"
    return None


def claude_candidates(p):
    """The Claude builds the posture considers: its own, or ON PACE's under TIGHT (by fit)."""
    src = ROUTES['ON PACE'] if p == 'TIGHT' else ROUTES[p]
    return [x for x in src['build'] if x in CLAUDE_BUILDS]


def reset_text(s):
    r = s.get('five_hour_resets_at')
    if not r:
        return 'reset time unknown (no five_hour_resets_at in usage.json)'
    return f'resets {time.strftime("%H:%M", time.localtime(r))}, in {max(0, round((r - time.time()) / 60))} min'


def allowed(a, p, s=None):
    """The posture's routes plus the Claude builds that fit (`misfit`). Adapter `budget.overrides`
    set to true joins a route whatever the posture (a Claude build still has to fit); false removes
    it. `routing.default_builder` leads the build list whenever the posture or a tick allows it
    (spec: the posture's list is the fallback, so it never overrides CRITICAL). Fusion
    goes when the Devin quota is exhausted, and so does SWE-2 when `devin.model` is a paid model."""
    s = s or signals()
    ov = a['budget'].get('overrides') or {}
    off = {k for k, v in ov.items() if v is False}
    on = {k for k, v in ov.items() if v is True}
    first = DEFAULT_ROUTE.get((a.get('routing') or {}).get('default_builder'))
    if _load(DEVIN).get('pct') == 'exhausted':
        off |= {'fusion_review', 'devin_fusion'}
        if a.get('devin') and ad.devin_cost(a['devin']['model']) == 'paid':
            off.add('devin_swe2')
    r = {k: [x for x in ROUTES[p][k] if x not in CLAUDE_BUILDS] for k in KINDS}
    for k in KINDS:
        r[k] += [x for x in KIND_ROUTES[k] if x in on and x not in CLAUDE_BUILDS and x not in r[k]]
    cands = claude_candidates(p)
    cands += [x for x in CLAUDE_BUILDS if x in on and x not in cands]
    r['build'] += [x for x in cands if not misfit(a, p, s, x)]
    if first in r['build']:
        r['build'].remove(first)
        r['build'].insert(0, first)
    return {k: [x for x in v if x not in off] for k, v in r.items()}


def questions(s):
    """Budget questions not yet answered this week."""
    y, w, _ = dt.date.today().isocalendar()
    all_ans = _load(ANSWERS)
    # An answer given before the 7-day reset time was known sits under the ISO week.
    ans = {**all_ans.get(f'{y}-W{w:02d}', {}), **all_ans.get(week_key(s), {})}
    q = []
    if s['seven_day_pct'] is None and 'claude' not in ans:
        q.append(('claude', 'The Claude 7-day window is unknown (no fresh usage.json from the status mod). '
                            'Spend Claude at ON PACE this week, or hold Opus to reviews only?'))
    if s['devin_paid'] is None and 'devin' not in ans:
        day = time.strftime('%A')
        q.append(('devin', f'It is {day}; the Devin paid quota is at an unknown %. OK to send reviews '
                           f'and hard tasks to Fusion this week? (or run `budget.py devin <pct>`)'))
    return q


def week_text(s, t):
    """'at 7% of week (floor 25%)': pace divides by the floor early in the week, so say so."""
    w = s['week_elapsed_pct']
    if w is None:
        return 'at unknown of week'
    floor = f" (floor {round(t['pace_floor_pct'])}%)" if w < t['pace_floor_pct'] else ''
    return f'at {round(w)}% of week{floor}'


def summary(a):
    s = signals()
    p, pace, known = posture(a, s)
    fmt = lambda v, suf='%': 'unknown' if v is None else f'{round(v)}{suf}'
    five = fmt(s['five_hour_pct']) + (f" ({reset_text(s)})" if s['five_hour_pct'] is not None else '')
    state = ' (budget off)' if p == 'OFF' else '' if known else ' (7d unknown: treated as ON PACE)'
    line = (f"posture {p}{state} · "
            f"Claude 7d {fmt(s['seven_day_pct'])} {week_text(s, a['budget'])}"
            f" (pace {'?' if pace is None else f'{pace:.2f}'}) · 5h {five} · "
            f"Devin paid {s['devin_paid'] if isinstance(s['devin_paid'], str) else fmt(s['devin_paid'])}")
    note = ROUTES[p]['note']
    wait = [f'{x.split("_")[0]} ({why})' for x in claude_candidates(p) if (why := misfit(a, p, s, x))]
    if wait:
        note += (f" DOES NOT FIT: {'; '.join(wait)}. Give the slot to Devin, or launch the Claude build "
                 f"once it fits.")
    return {'posture': p, 'pace': pace, 'signals': s, 'line': line, 'routes': allowed(a, p, s), 'spend': spend(s),
            'note': note, 'questions': questions(s), 'week': week_key(s)}


def scan_devin_log(path):
    """If a Devin log says the paid quota ran out, record it. Returns True when it did."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 20000))
            text = f.read().decode('utf-8', 'replace')
    except OSError:
        return False
    if DEVIN_OUT.search(text):
        d = _load(DEVIN)
        if d.get('pct') != 'exhausted':
            _save(DEVIN, {**d, 'pct': 'exhausted', 'source': path, 'ts': time.time()})
        return True
    return False


def route_row(a, release, task, route, why='', override=None, strict=True):
    """Write the machine-readable ROUTE row the v3 router will learn from. A route the posture does
    not allow is refused unless `override` gives the reason (2.10.0: 3 Claude builds were routed
    "SURPLUS" while the posture said TIGHT on a 72-75% 5h window). strict=False (a launch already
    made, routed by ledger.py) writes the row with offposture=1 and a warning instead."""
    import ledger as lg
    if route not in ALL_ROUTES:
        ad.die(f'unknown route {route!r}: one of {", ".join(sorted(ALL_ROUTES))}')
    b = summary(a)
    s = b['signals']
    ok = {x for k in KINDS for x in b['routes'][k]}
    off = route not in ok
    if off and not override:
        fit = route in claude_candidates(b['posture']) and misfit(a, b['posture'], s, route)
        why_not = f'it does not fit: {fit}' if fit else \
            f'posture {b["posture"]} allows {", ".join(sorted(ok)) or "nothing"}'
        msg = f'route {route} refused for {task}: {why_not}.'
        if strict:
            ad.die(msg + ' Pick an allowed route, or pass --override "<reason>" (it is written in the row).')
        print('WARNING: ' + msg + ' Written with offposture=1.')
    kv = lambda k, v: f'{k}={"?" if v is None else (round(v) if isinstance(v, float) else v)}'
    ev = ' '.join([f'ROUTE -> {route}', kv('posture', b['posture'].replace(' ', '_')),
                   kv('7d', s['seven_day_pct']), kv('week', s['week_elapsed_pct']),
                   kv('5h', s['five_hour_pct']), kv('devin_paid', s['devin_paid'])])
    if off:
        ev += f' offposture=1' + (f' override="{override}"' if override else '')
    if why:
        ev += f' why="{why}"'
    lf = ad.ledger_file(a, release)
    lg.add(lf, task, 'coordinator', ev)


def main():
    args = sys.argv[1:]
    if args and args[0] == 'devin':
        if len(args) < 2:
            sys.exit(__doc__)
        v = args[1]
        resets = ad.opt(args, '--resets')
        d = {'pct': 'exhausted' if v == 'exhausted' else float(v.rstrip('%')), 'ts': time.time(), 'source': 'manual'}
        if resets:
            d['resets'] = resets
        _save(DEVIN, d)
        print(f'Devin paid quota recorded: {d["pct"]}' + (f', resets {resets}' if resets else ''))
        return
    if args and args[0] == 'answer':
        if len(args) != 3 or args[1] not in ('claude', 'devin'):
            sys.exit(__doc__)
        s = signals()
        ans = _load(ANSWERS)
        ans.setdefault(week_key(s), {})[args[1]] = {'answer': args[2], 'at': time.strftime('%Y-%m-%d %H:%M')}
        _save(ANSWERS, ans)
        print(f'recorded for week {week_key(s)}: {args[1]} = {args[2]}  (also write it in the ledger Decisions)')
        return
    if args and args[0] == 'route':
        rest = args[1:]
        release = ad.opt(rest, '--release')
        why = ad.opt(rest, '--why', '')
        override = ad.opt(rest, '--override')
        if len(rest) != 3 or not release:
            sys.exit(__doc__)
        a, _, release = ad.load_release(rest[0], release)
        route_row(a, release, rest[1], rest[2], why, override)
        return
    as_json = '--json' in args
    release = ad.opt(args, '--release')
    args = [x for x in args if x != '--json']
    a, _, _ = ad.load_release(args[0] if args else '.', release)
    b = summary(a)
    if as_json:
        print(json.dumps(b))
        return
    print(b['line'])
    r = b['routes']
    print(f"routes: build {', '.join(r['build']) or '-'} · review {', '.join(r['review']) or '-'}"
          f" · critique {', '.join(r['critique']) or '-'} · eyeball {', '.join(r['eyeball']) or '-'}")
    print(f"  {b['note']}")
    if b['spend']:
        print(f"  {b['spend']['line']}")
    for sig, q in b['questions']:
        print(f'QUESTION ({sig}, once this week): {q}')


if __name__ == '__main__':
    main()
