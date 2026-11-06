"""Set a repo up for coordination: draft `.claude/coordinate.json` and gitignore `.coordinate/`.

  init.py <repo> [--force]

Detects what it can and writes a DRAFT adapter (never over an existing one without --force), then
prints the seven questions for the coordinator to ask in ONE AskUserQuestion batch, each with the
detected answer as the recommended option. Edit the draft with the answers; preflight.py checks it.

  1. House rules: the repo's file, plus an optional shared rules path or git URL
  2. Gates (from package.json / pyproject.toml / Makefile)
  3. DB-test tier: command, or none
  4. Handoff file and append-only files, or none
  5. Close-out skill, or none
  6. Concurrency caps and test slots
  7. Task tracker: TaskMaster, a Markdown list (default TASKS.md, created when missing), or none
"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad

GATE_SCRIPTS = ('test', 'build', 'lint', 'typecheck', 'check')


def node_gates(main):
    gates, db = [], None
    pkgs = [p for p in glob.glob(os.path.join(main, '*/package.json')) + [os.path.join(main, 'package.json')]
            if os.path.exists(p) and 'node_modules' not in p]
    for p in sorted(pkgs):
        d = os.path.relpath(os.path.dirname(p), main)
        try:
            scripts = json.load(open(p)).get('scripts', {})
        except ValueError:
            continue
        for s in GATE_SCRIPTS:
            if s in scripts:
                cmd = 'npm test' if s == 'test' else f'npm run {s}'
                gates.append({'name': f'{"" if d == "." else d + " "}{s}', 'dir': d, 'cmd': cmd})
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
    gates = []
    if os.path.exists(os.path.join(main, 'pyproject.toml')):
        gates.append({'name': 'pytest', 'dir': '.', 'cmd': 'python3 -m pytest -q'})
    mk = os.path.join(main, 'Makefile')
    if os.path.exists(mk):
        targets = {l.split(':')[0] for l in open(mk) if ':' in l and not l.startswith(('\t', '#', '.'))}
        gates += [{'name': f'make {t}', 'dir': '.', 'cmd': f'make {t}'} for t in GATE_SCRIPTS if t in targets]
    return gates


def find_first(main, names):
    for n in names:
        if os.path.exists(os.path.join(main, n)):
            return n
    return None


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    main_ = ad.main_checkout(os.path.abspath(args[0]))
    target = os.path.join(main_, '.claude', 'coordinate.json')
    rules = find_first(main_, ('AGENTS.md', 'CLAUDE.md', '.cursorrules')) or 'AGENTS.md'
    gates, db = node_gates(main_)
    gates += other_gates(main_)
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
    if os.path.exists(target) and '--force' not in args:
        print(f'adapter exists: {target} (--force to overwrite). Draft for comparison:')
        print(json.dumps(draft, indent=2))
    else:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        json.dump(draft, open(target, 'w'), indent=2)
        print(f'DRAFT written: {target}')
    if tracker['tracker'] == 'markdown' and ensure_tasks_file(main_, tracker['tasks_file']):
        print(f'created {tracker["tasks_file"]} (the default task list: no tracker was found; commit it)')
    gi = os.path.join(main_, '.gitignore')
    have = open(gi).read().split('\n') if os.path.exists(gi) else []
    if '.coordinate/' not in have and '.coordinate' not in have:
        with open(gi, 'a') as f:
            f.write(('' if not have or have[-1] == '' else '\n') + '.coordinate/\n')
        print('.gitignore: added .coordinate/ (ledgers, briefs, logs stay out of git: merge.py refuses a dirty main)')
    print('\nAsk these in ONE AskUserQuestion batch (detected answer = recommended option):')
    print(f'1. House rules: {rules}; a shared rules path or git URL too? (default: none)')
    print(f'2. Gates: {", ".join(g["name"] for g in gates) or "none detected"}. Right set and order?')
    print(f'3. DB-test tier: {db["cmd"] + " in " + db["dir"] if db else "none detected"}. A snapshot command for the leak check?')
    print(f'4. Handoff: {handoff or "none"}; append-only files: {", ".join(append_only) or "none"}')
    print(f'5. Close-out skill: {closeout or "none"}; archive finished ledgers into the repo docs? (ledger_archive)')
    print(f'   Worktree setup: {"; ".join(setup) or "none"} (generated-types steps are detected from the dependencies)')
    print(f'6. Concurrency: devin {draft["concurrency"]["devin"]}, sonnet {draft["concurrency"]["sonnet"]}, '
          f'opus review {draft["concurrency"]["opus_review"]}; test slots 1 (raise once parallel test runs stop timing out)')
    t = tracker['tracker']
    print(f'7. Task tracker: {"TaskMaster (" + tracker["taskmaster"] + ")" if t == "taskmaster" else "a Markdown list (" + tracker["tasks_file"] + ")"}. '
          'Right one? Options: TaskMaster, a Markdown file (default; needs nothing), none (`tracker: "none"`). '
          'The coordinator reads it for open tasks and checks merged tasks against it.')
    if not ad.auto_mode_named(main_):
        print('\nAuto mode: no autoMode.environment entry names this repo. Its owner adds this line to '
              '~/.claude/settings.json (a session cannot):\n  ' + ad.auto_mode_line(main_))
    print('\nThen commit .claude/coordinate.json and the .gitignore line, and run preflight.py.')


if __name__ == '__main__':
    main()
