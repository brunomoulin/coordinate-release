"""/coordinate settings: show, set and preset the coordinator's knobs, for one release or the repo.

  settings.py show   [<repo>] [--release R|auto] [--json]
  settings.py set    [<repo>] (--release R | --repo) <key>=<value> ...
  settings.py preset [<repo>] (--release R | --repo) <balanced|frugal|all-out>

Release scope writes `SET <key>=<json>` rows in the release's timeline (latest row wins,
`<key>=default` clears it). Repo scope edits the adapter file; a committed
`.claude/coordinate.json` is changed on a `chore/settings-<date>` branch merged into main with
--no-ff (main must be clean), and the push stays the owner's.
A value is JSON when it parses (true, 60, "off"), else a bare string. Exit 0 ok, 2 bad input,
1 refused. Presets live in adapter.PRESETS; knob metadata only here (KNOBS).
"""
import io, json, os, subprocess, sys, time
from contextlib import redirect_stdout
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import budget
import ledger as lg

WHO, SPEND, HANDOFF = 'WHO DOES THE WORK', 'HOW HARD TO SPEND', 'WHEN TO HAND OFF'
GROUPS = (WHO, SPEND, HANDOFF)
LIMITS_WHY = ('turns cost more as context grows; a resume costs ~100k and 10 min; '
              'the hard limit leaves room to park before auto-compact')
# The routes the picker toggles, with their labels. park_review is a posture fallback, not a choice.
ROUTE_LABELS = {
    'devin_swe2': 'Devin builds', 'devin_fusion': 'Devin Fusion builds',
    'haiku_implement': 'Claude Haiku builds', 'sonnet_implement': 'Claude Sonnet builds',
    'opus_implement': 'Claude Opus builds', 'opus_review': 'Opus reviews', 'fusion_review': 'Fusion reviews',
    'sonnet_review': 'Sonnet re-reviews', 'sonnet_critique': 'Sonnet critiques',
    'sonnet_eyeball': 'Sonnet eyeball checks', 'swe2_review': 'SWE-2 critiques',
    'devin_eyeball': 'Devin eyeball checks'}
ROUTE_WHY = 'unset: the budget posture decides; on: allowed whatever the posture; off: never'
KNOBS = {
    'routing.default_builder': {'group': WHO, 'label': 'Who builds first', 'choices': ['devin', 'sonnet', 'haiku', 'opus'],
                                'why': 'Devin SWE-2 is free with a Devin subscription; without one, Sonnet'},
    'devin.model': {'group': WHO, 'label': 'Devin build model', 'kind': 'model',
                    'why': 'a free model keeps builds off the Devin quota; a paid one spends it'},
    'devin.fusion_model': {'group': WHO, 'label': 'Devin Fusion model', 'kind': 'model',
                           'why': 'for builds too hard for SWE-2 and for reviews; spends the Devin quota'},
    **{f'budget.overrides.{r}': {'group': WHO, 'label': lbl, 'kind': 'bool', 'why': ROUTE_WHY}
       for r, lbl in ROUTE_LABELS.items()},
    'budget.mode': {'group': SPEND, 'label': 'Budget', 'choices': ['auto', 'off'],
                    'why': 'auto: routes follow the 7-day pace; off: every route, no fit check, no park'},
    'budget.five_hour_fit_pct': {'group': SPEND, 'label': 'Claude build cutoff (5h %)', 'kind': 'int', 'range': (1, 100),
                                 'why': 'a Claude build waits when the 5h window plus its cost would pass it: '
                                        'the coordinator shares that window'},
    'session_limits.soft_tokens': {'group': HANDOFF, 'label': 'Soft context limit', 'kind': 'int',
                                   'range': (1, 999999), 'why': 'no new wave past it; ' + LIMITS_WHY},
    'session_limits.hard_tokens': {'group': HANDOFF, 'label': 'Hard context limit', 'kind': 'int',
                                   'range': (1, 999999), 'why': 'park after the current merge; ' + LIMITS_WHY},
}


def get(d, key):
    for k in key.split('.'):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def fmt(key, v):
    if key.startswith('budget.overrides.'):
        return {True: 'on', False: 'off'}.get(v, 'posture decides')
    return 'unset' if v is None else str(v)


def valid(key, v):
    """None when v suits the knob, else what is wrong."""
    k = KNOBS.get(key)
    if v == 'default':
        return None
    if 'choices' in k:
        return None if v in k['choices'] else f'{key} takes {" | ".join(k["choices"])}'
    kind = k.get('kind')
    if kind == 'bool':
        return None if isinstance(v, bool) else f'{key} takes true | false | default'
    if kind == 'int':
        lo, hi = k['range']
        ok = isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi
        return None if ok else f'{key} takes a whole number {lo}-{hi}'
    return None if isinstance(v, str) and v.strip() else f'{key} takes a model id (devin models list)'


def parse(pairs):
    out = []
    for p in pairs:
        key, sep, raw = p.partition('=')
        if not sep:
            fail(f'not <key>=<value>: {p!r}')
        if key not in KNOBS:
            fail(f'unknown setting {key!r}. Settings:\n  ' + '\n  '.join(KNOBS))
        try:
            v = json.loads(raw)
        except ValueError:
            v = raw
        if (why := valid(key, v)):
            fail(why)
        out.append((key, v))
    return out


def fail(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def check_limits(a):
    lim = a['session_limits']
    if not lim['soft_tokens'] < lim['hard_tokens'] < 1000000:
        fail(f"soft {lim['soft_tokens']} must be below hard {lim['hard_tokens']}, and hard below 1000000")


# Who builds first and the Devin models depend on the owner's subscriptions, not on how hard to
# spend: presets never set or reset them, and a preset matches whatever they are.
PERSONAL = ('routing.default_builder', 'devin.model', 'devin.fusion_model')
PRESET_KEYS = tuple(k for k in KNOBS if k not in PERSONAL)


def default_of(key):
    return None if key.startswith('budget.overrides.') else get(ad.DEFAULTS, key)


def preset_values(name):
    """Every preset knob under a preset: DEFAULTS (overrides unset), then the preset's overlay."""
    vals = {k: default_of(k) for k in PRESET_KEYS}
    vals.update(ad.PRESETS[name])
    return vals


def matching_preset(a):
    eff = {k: get(a, k) for k in PRESET_KEYS}
    for name in ad.PRESETS:
        if preset_values(name) == eff:
            return name
    return 'custom'


def model_choices():
    cat = ad.devin_catalog()
    free = ad.free_devin_models(cat)
    paid = sorted(m for m in cat if m not in free)
    return [{'value': m, 'cost': 'free', 'summary': (cat[m] or {}).get('summary')} for m in free] + \
           [{'value': m, 'cost': 'paid', 'summary': (cat[m] or {}).get('summary')} for m in paid]


def show(repo, release, as_json):
    a, _, release = ad.load_release(repo, release)
    groups = []
    for g in GROUPS:
        knobs = []
        for key, k in KNOBS.items():
            if k['group'] != g:
                continue
            choices = model_choices() if k.get('kind') == 'model' else \
                [{'value': c} for c in k['choices']] if 'choices' in k else \
                [{'value': True}, {'value': False}] if k.get('kind') == 'bool' else []
            knobs.append({'key': key, 'label': k['label'], 'value': get(a, key),
                          'source': a['_sources'].get(key, 'default'), 'why': k['why'], 'choices': choices})
        groups.append({'name': g, 'knobs': knobs})
    if as_json:
        print(json.dumps({'release': release, 'groups': groups, 'presets': ad.PRESETS, 'preset': matching_preset(a)}))
        return
    print(f"settings for {'release ' + release if release else 'the repo'} (preset: {matching_preset(a)})")
    for g in groups:
        print(f"\n{g['name']}")
        for k in g['knobs']:
            print(f"  {k['label']}  {fmt(k['key'], k['value'])}  ({k['source']})  {k['why']}")


def notes(key, v, repo_a):
    """Extra lines a change owes the owner."""
    out = []
    if key.startswith('budget.overrides.') and v is True and get(repo_a, key) is False:
        out.append(' (the repo has it off)')
    if key == 'budget.mode' and v == 'off':
        out.append('\n  budget off: the coordinator may use up your 5-hour and 7-day windows; '
                   'spend is still recorded on ROUTE rows')
    if key == 'devin.model' and isinstance(v, str) and v != 'default' and ad.devin_cost(v) == 'paid':
        cat = ad.devin_catalog()
        summary = (cat.get(v) or {}).get('summary') or 'not in the Devin catalog'
        out.append(f'\n  note: {v} is paid ({summary}): it spends the Devin quota. '
                   f'free: {", ".join(ad.free_devin_models(cat)) or "none listed"}')
    return ''.join(out)


def confirm(changes, before, after, scope, repo_a):
    for key, v in changes:
        print(f"{KNOBS[key]['label']}: {fmt(key, get(before, key))} -> {fmt(key, get(after, key))} "
              f"({scope}){notes(key, v, repo_a)}")


def write_release(repo, release, changes):
    a0, _ = ad.load(repo)
    lf = ad.ledger_file(a0, release)
    if not os.path.exists(lf):
        fail(f'no release folder for {release}: ledger.py init {ad.release_path(a0, release)} {release}', 1)
    before, _ = ad.load(repo, release)
    trial = json.loads(json.dumps({k: v for k, v in before.items() if not k.startswith('_')}))
    for key, v in changes:
        if v == 'default':
            ad.set_dotted(trial, key, get(a0, key))
        else:
            ad.set_dotted(trial, key, v)
    check_limits(trial)
    with redirect_stdout(io.StringIO()):
        for key, v in changes:
            lg.add(lf, '-', 'owner', f'SET {key}=' + ('default' if v == 'default' else json.dumps(v)))
    after, _ = ad.load(repo, release)
    confirm(changes, before, after, f'release {release}', a0)


def git(cwd, *args):
    return subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True)


def edit_file(path, changes):
    d = json.load(open(path), object_pairs_hook=dict) if os.path.exists(path) else {}
    for key, v in changes:
        if v == 'default':
            ad.del_dotted(d, key)
        else:
            ad.set_dotted(d, key, v)
    with open(path, 'w') as fh:
        json.dump(d, fh, indent=2)
        fh.write('\n')


def write_repo(repo, changes):
    before, main = ad.load(repo)
    trial = json.loads(json.dumps({k: v for k, v in before.items() if not k.startswith('_')}))
    for key, v in changes:
        ad.set_dotted(trial, key, get(ad.DEFAULTS, key) if v == 'default' else v)
    check_limits(trial)
    path = ad.adapter_path(main)
    rel = os.path.relpath(path, main)
    tracked = not rel.startswith('..') and git(main, 'ls-files', '--error-unmatch', rel).returncode == 0
    if not tracked:
        edit_file(path, changes)
    else:
        branch = git(main, 'rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()
        if branch != before['main_branch']:
            fail(f'{main} is on {branch}, not {before["main_branch"]}: settings.py merges into the main branch', 1)
        if git(main, 'status', '--porcelain').stdout.strip():
            fail(f'main is dirty ({main}): commit or stash first; {rel} is committed, so the change '
                 f'goes through a chore/settings branch merged with --no-ff', 1)
        stamp = time.strftime('%Y%m%d-%H%M')
        new = f'chore/settings-{stamp}'
        wt = ad.worktree_path(before, f'settings-{stamp}')
        r = git(main, 'worktree', 'add', wt, '-b', new)
        if r.returncode:
            fail(f'git worktree add failed: {r.stderr.strip()}', 1)
        edit_file(os.path.join(wt, rel), changes)
        what = ', '.join(f'{k}={json.dumps(v) if v != "default" else "default"}' for k, v in changes)
        steps = [(wt, ('commit', '-qam', f'chore(settings): {what}')),
                 (main, ('merge', '--no-ff', '-q', new, '-m', f'Merge {new}: {what}')),
                 (main, ('worktree', 'remove', wt))]
        for cwd, args in steps:
            r = git(cwd, *args)
            if r.returncode:
                fail(f'git {args[0]} failed in {cwd}: {r.stderr.strip()}\n(worktree {wt}, branch {new})', 1)
        print(f'{rel} changed on {new}, merged into {before["main_branch"]} (--no-ff)')
    after, _ = ad.load(repo)
    confirm(changes, before, after, 'repo', before)
    if tracked:
        print('pushed? no: git push when ready')


def preset_changes(repo, release, name):
    """The writes that make every preset knob equal the preset (DEFAULTS plus its overlay). Where
    the scope's base already gives the preset value (release: the repo; repo: DEFAULTS), the
    scope's own value is dropped (`=default`); elsewhere the preset value is written."""
    if name not in ad.PRESETS:
        fail(f'unknown preset {name!r}: {" | ".join(ad.PRESETS)}')
    a = ad.load(repo, release)[0] if release else ad.load(repo)[0]
    base = ad.load(repo)[0] if release else None
    own = 'release' if release else 'repo'
    changes = []
    for k, want in preset_values(name).items():
        base_v = get(base, k) if release else default_of(k)
        if want == base_v:
            if a['_sources'].get(k) == own:
                changes.append((k, 'default'))
        elif get(a, k) != want:
            changes.append((k, want))
    return changes


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ('show', 'set', 'preset'):
        fail(__doc__)
    cmd = args.pop(0)
    release = ad.opt(args, '--release')
    to_repo = '--repo' in args
    as_json = '--json' in args
    args = [x for x in args if x not in ('--repo', '--json')]
    repo = args.pop(0) if args and '=' not in args[0] and (cmd != 'preset' or len(args) > 1) else '.'
    if cmd == 'show':
        return show(repo, release, as_json)
    if bool(release) == to_repo:
        fail(f'{cmd}: pick one scope, --release R or --repo')
    if release:
        release = ad.resolve_release(ad.load(repo)[0], release)
    if cmd == 'preset':
        if len(args) != 1:
            fail(__doc__)
        changes = preset_changes(repo, release, args[0])
        if not changes:
            print(f'preset {args[0]}: nothing to change')
            return
    else:
        if not args:
            fail(__doc__)
        changes = parse(args)
    if release:
        write_release(repo, release, changes)
    else:
        write_repo(repo, changes)


if __name__ == '__main__':
    main()
