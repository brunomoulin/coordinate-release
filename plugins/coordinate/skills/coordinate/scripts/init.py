"""Set a repo up for coordination: draft `.claude/coordinate.json` and gitignore `.coordinate/`.

  init.py <repo> [--force]

Detects what it can and writes a DRAFT adapter (never over an existing one without --force), then
prints the seven questions for the coordinator to ask in ONE AskUserQuestion batch, each with the
detected answer as the recommended option. Edit the draft with the answers; preflight.py checks it.
On an existing adapter it prints only the keys the adapter lacks and asks only their questions; keys
set differently from the draft are the owner's choices, listed as kept and not re-asked.

  1. House rules: the repo's file, plus an optional shared rules path or git URL
  2. Gates (from package.json / pyproject.toml / Makefile), cheapest first: type check, lint,
     test, build. A script running tsc, vue-tsc, svelte-check or astro check is a type check by any name
  3. DB-test tier: command, or none
  4. Handoff file and append-only files, or none
  5. Close-out skill, or none
  6. Concurrency caps and test slots
  7. Task tracker: TaskMaster, a Markdown list (default TASKS.md, created when missing), or none
"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad


# Gate names in cheapest-first run order: a type check, then lint, test, build.
GATE_SCRIPTS = ('typecheck', 'check', 'lint', 'test', 'build')
RANK = {'typecheck': 0, 'check': 0, 'lint': 1, 'test': 2, 'build': 3}
# A script whose command runs one of these is a type-check gate whatever its name
# (`"compile": "tsc --noEmit"`). Only for names outside GATE_SCRIPTS: `"build": "tsc && vite build"`
# stays a build. Watch modes and npm's pre/post hooks are not gates.
TYPECHECK_CMD = re.compile(r'(?:^|[\s;&|(/])(?:tsc|vue-tsc|svelte-check|astro\s+check)(?=\s|$|[;&|)])')


def is_typecheck(name, cmd):
    return (name not in GATE_SCRIPTS and not name.startswith(('pre', 'post'))
            and bool(TYPECHECK_CMD.search(cmd)) and not re.search(r'(?:^|\s)(?:--watch|-w)(?:\s|$)', cmd))


def ordered(ranked):
    """Gates from (rank, gate) pairs, cheapest first; a stable sort keeps package order within a rank."""
    return [g for _, g in sorted(ranked, key=lambda r: r[0])]


def node_gates(main):
    """(rank, gate) pairs for each package.json's gate scripts, and the DB-test tier if one is named."""
    gates, db = [], None
    pkgs = [p for p in glob.glob(os.path.join(main, '*/package.json')) + [os.path.join(main, 'package.json')]
            if os.path.exists(p) and 'node_modules' not in p]
    for p in sorted(pkgs):
        d = os.path.relpath(os.path.dirname(p), main)
        try:
            scripts = json.load(open(p)).get('scripts', {})
        except ValueError:
            continue
        for s, cmd in scripts.items():
            if s in GATE_SCRIPTS:
                rank = RANK[s]
            elif is_typecheck(s, cmd):
                rank = 0
            else:
                continue
            run = 'npm test' if s == 'test' else f'npm run {s}'
            gates.append((rank, {'name': f'{"" if d == "." else d + " "}{s}', 'dir': d, 'cmd': run}))
        for s in scripts:
            if db is None and ('db' in s.split(':')[-1] or 'integration' in s) and s.startswith('test'):
                db = {'dir': d, 'cmd': f'npm run {s}'}
    return gates, db


# Generators `npm ci` does not run unless the package's own postinstall/prepare script does:
# (packages whose presence implies it, the command). v1 needed `wxt prepare` after `npm ci`.
GENERATORS = (({'wxt'}, 'wxt prepare'), ({'prisma', '@prisma/client'}, 'prisma generate'),
              ({'@sveltejs/kit'}, 'svelte-kit sync'), ({'nuxt'}, 'nuxi prepare'))


def generator_steps(main):
    """Setup commands for the generated-types step of each package.json, unless its postinstall or
    prepare script already runs it. Subfolder packages run as `(cd <dir> && ...)`."""
    pkgs = [p for p in glob.glob(os.path.join(main, '*/package.json')) + [os.path.join(main, 'package.json')]
            if os.path.exists(p) and 'node_modules' not in p]
    out = []
    for p in sorted(pkgs, key=lambda p: (os.path.dirname(p) != main, p)):
        d = os.path.relpath(os.path.dirname(p), main)
        try:
            pkg = json.load(open(p))
        except ValueError:
            continue
        deps = set(pkg.get('dependencies', {})) | set(pkg.get('devDependencies', {}))
        hooks = ' '.join(pkg.get('scripts', {}).get(s, '') for s in ('postinstall', 'prepare', 'postprepare'))
        for names, cmd in GENERATORS:
            if deps & names and cmd not in hooks:
                out.append(f'npx {cmd}' if d == '.' else f'(cd {d} && npx {cmd})')
    return out


TASKS_TEMPLATE = (
    '# Tasks\n\nOne line per task, the id first: the coordinator ticks a task when its branch merges.\n\n'
    '## Now\n\n- [ ] T1 \u2014 the first task\n')


def detect_tracker(main):
    """Adapter keys for the repo's task tracker: TaskMaster when `.taskmaster/` holds a register, an
    existing Markdown task file, else the default `TASKS.md` (needs no dependency)."""
    if os.path.exists(os.path.join(main, '.taskmaster', 'tasks', 'tasks.json')):
        return {'tracker': 'taskmaster', 'taskmaster': '.taskmaster/tasks/tasks.json'}
    found = find_first(main, ('TASKS.md', 'documentation/TASKS.md', 'docs/TASKS.md', 'TODO.md'))
    return {'tracker': 'markdown', 'tasks_file': found or 'TASKS.md'}


def ensure_tasks_file(main, rel):
    """Create the default task file when it is missing; True when it did."""
    p = os.path.join(main, rel)
    if os.path.exists(p):
        return False
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write(TASKS_TEMPLATE)
    return True


def other_gates(main):
    """(rank, gate) pairs for pytest and the Makefile's gate targets."""
    gates = []
    if os.path.exists(os.path.join(main, 'pyproject.toml')):
        gates.append((RANK['test'], {'name': 'pytest', 'dir': '.', 'cmd': 'python3 -m pytest -q'}))
    mk = os.path.join(main, 'Makefile')
    if os.path.exists(mk):
        targets = {l.split(':')[0] for l in open(mk) if ':' in l and not l.startswith(('\t', '#', '.'))}
        gates += [(RANK[t], {'name': f'make {t}', 'dir': '.', 'cmd': f'make {t}'}) for t in GATE_SCRIPTS if t in targets]
    return gates


def find_first(main, names):
    for n in names:
        if os.path.exists(os.path.join(main, n)):
            return n
    return None


TRACKER_KEYS = {'tracker', 'tasks_file', 'taskmaster'}
# The draft keys each of the seven questions decides, in order. env_files is detected, not asked.
QUESTION_KEYS = (
    {'repo_rules', 'shared_rules'}, {'gates'}, {'db_test', 'db_snapshot'}, {'handoff', 'append_only'},
    {'closeout_skill', 'ledger_archive', 'worktree_setup'}, {'concurrency', 'test_slots'}, TRACKER_KEYS)


def questions(draft):
    """(keys it decides, printed line) for each of the seven questions, from the draft's detected values."""
    db, c = draft['db_test'], draft['concurrency']
    tracker = ('TaskMaster (' + draft['taskmaster'] + ')' if draft['tracker'] == 'taskmaster'
               else 'a Markdown list (' + draft['tasks_file'] + ')')
    lines = (
        f'1. House rules: {draft["repo_rules"]}; a shared rules path or git URL too? (default: none)',
        f'2. Gates: {", ".join(g["name"] for g in draft["gates"]) or "none detected"}. '
        'Right set and order? (cheapest first: type check, lint, test, build)',
        f'3. DB-test tier: {db["cmd"] + " in " + db["dir"] if db else "none detected"}. A snapshot command for the leak check?',
        f'4. Handoff: {draft["handoff"] or "none"}; append-only files: {", ".join(draft["append_only"]) or "none"}',
        f'5. Close-out skill: {draft["closeout_skill"] or "none"}; archive finished ledgers into the repo docs? (ledger_archive)\n'
        f'   Worktree setup: {"; ".join(draft["worktree_setup"]) or "none"} (generated-types steps are detected from the dependencies)',
        f'6. Concurrency: devin {c["devin"]}, sonnet {c["sonnet"]}, opus review {c["opus_review"]}; '
        'test slots 1 (raise once parallel test runs stop timing out)',
        f'7. Task tracker: {tracker}. Right one? Options: TaskMaster, a Markdown file (default; needs nothing), '
        'none (`tracker: "none"`). The coordinator reads it for open tasks and checks merged tasks against it.')
    return list(zip(QUESTION_KEYS, lines))


def compare(existing, draft):
    """(missing, kept): draft keys the adapter lacks, and keys it sets differently (the owner's choices).
    The tracker is one choice: any of its keys in the adapter means it was answered."""
    answered_tracker = bool(set(existing) & TRACKER_KEYS)
    missing, kept = [], []
    for k in draft:
        if k not in existing:
            if not (k in TRACKER_KEYS and answered_tracker):
                missing.append(k)
        elif existing[k] != draft[k]:
            kept.append(k)
    return missing, kept


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    main_ = ad.main_checkout(os.path.abspath(args[0]))
    target = os.path.join(main_, '.claude', 'coordinate.json')
    rules = find_first(main_, ('AGENTS.md', 'CLAUDE.md', '.cursorrules')) or 'AGENTS.md'
    ranked, db = node_gates(main_)
    gates = ordered(ranked + other_gates(main_))
    handoff = find_first(main_, ('documentation/agent-handoff.md', 'docs/agent-handoff.md', 'HANDOFF.md'))
    append_only = [f for f in (handoff, 'CHANGELOG.md') if f and os.path.exists(os.path.join(main_, f))]
    closeout = None
    for p in glob.glob(os.path.join(main_, '.claude/skills/*/SKILL.md')):
        if 'closeout' in p.replace('-', '') or 'release' in os.path.basename(os.path.dirname(p)):
            closeout = os.path.basename(os.path.dirname(p))
    env_files = [os.path.relpath(p, main_) for p in glob.glob(os.path.join(main_, '*/.env')) + glob.glob(os.path.join(main_, '.env'))]
    setup = ['npm ci'] if os.path.exists(os.path.join(main_, 'package-lock.json')) else []
    setup += generator_steps(main_)
    tracker = detect_tracker(main_)
    draft = {
        'repo_rules': rules,
        'shared_rules': None,
        'gates': gates,
        'db_test': db,
        'db_snapshot': None,
        'handoff': handoff,
        'append_only': append_only,
        'closeout_skill': closeout,
        'concurrency': ad.DEFAULTS['concurrency'],
        'test_slots': 1,
        'env_files': env_files,
        'worktree_setup': setup,
        'ledger_archive': None,
        **tracker,
    }
    existing = None
    if os.path.exists(target) and '--force' not in args:
        try:
            existing = json.load(open(target))
        except ValueError as e:
            sys.exit(f'adapter exists but is not valid JSON: {target}: {e} (fix it, or --force to overwrite)')
        print(f'adapter exists: {target} (--force to overwrite)')
    else:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        json.dump(draft, open(target, 'w'), indent=2)
        print(f'DRAFT written: {target}')
    # The task file to create: the adapter's own tracker choice when it made one, else the detected one.
    tr = existing if existing and set(existing) & TRACKER_KEYS else tracker
    tf = tr.get('tasks_file')
    if tr.get('tracker', 'markdown') == 'markdown' and tf and ensure_tasks_file(main_, tf):
        print(f'created {tf} (the default task list: no tracker was found; commit it)')
    gi = os.path.join(main_, '.gitignore')
    have = open(gi).read().split('\n') if os.path.exists(gi) else []
    if '.coordinate/' not in have and '.coordinate' not in have:
        with open(gi, 'a') as f:
            f.write(('' if not have or have[-1] == '' else '\n') + '.coordinate/\n')
        print('.gitignore: added .coordinate/ (ledgers, briefs, logs stay out of git: merge.py refuses a dirty main)')
    qs = questions(draft)
    if existing is None:
        print('\nAsk these in ONE AskUserQuestion batch (detected answer = recommended option):')
        print('\n'.join(line for _, line in qs))
    else:
        missing, kept = compare(existing, draft)
        if kept:
            print(f'kept (set differently from the draft: the owner\'s choices, not re-asked): {", ".join(kept)}')
        if not missing:
            print('adapter up to date: nothing to ask. Run preflight.py.')
            return
        print('missing keys, with the detected values (add them with the answers):')
        print(json.dumps({k: draft[k] for k in missing}, indent=2))
        asked = [line for keys, line in qs if keys & set(missing)]
        if asked:
            print('\nAsk only these in ONE AskUserQuestion batch (detected answer = recommended option):')
            print('\n'.join(asked))
    if not ad.auto_mode_named(main_):
        print('\nAuto mode: no autoMode.environment entry names this repo. Its owner adds this line to '
              '~/.claude/settings.json (a session cannot):\n  ' + ad.auto_mode_line(main_))
    print('\nThen commit .claude/coordinate.json and the .gitignore line, and run preflight.py.')


if __name__ == '__main__':
    main()
