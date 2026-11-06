# Agent & Developer Workflow Rules — coordinate

This file is read automatically by AI coding assistants (Claude, Devin, Cursor, etc.).
It defines the development workflow rules for coordinate, the Claude Code plugin that runs a
software release as a coordinator (see `README.md`).
**All rules apply equally to human developers and AI agents.**

Governance weight: **lean**: branches + worktrees + CI running the test suite. Everything below
applies at every weight. The weight only changes how much tooling backs each rule.

Task tracking: **`ROADMAP.md`** (repo root). It is the one list of what comes next. `CHANGELOG.md`
records what each version shipped. Decided 2026-11-06, not re-derived every session.

---

## Branch Rules

- **Never commit directly to `main`**
- Create a `feature/<description>` or `bugfix/<description>` branch for every task. Use exactly
  these two prefixes (not `fix/*`, `hotfix/*`, or other variants). Branches before 2026-11-06 used
  `feat/*`; they stay as they are in history.
- Merge back to `main` with `git merge --no-ff` (a merge commit, so merged worktrees can be found
  and removed) only when the work is complete and the tests pass
- `main` represents the latest stable state. A coordinator that loads the skill from a
  checkout sees a merge there on its next script call
- Each release bumps `plugins/coordinate/.claude-plugin/plugin.json` and adds a `CHANGELOG.md`
  entry; the publish steps are in `README.md` § Developing. The owner does every push.

```
feature/your-feature ──┐
bugfix/your-fix       ─┴──> main ──[tests]──> plugin release
```

## Parallel Agents — Use a Worktree, Not Just a Branch

A branch alone doesn't isolate concurrent agents. One physical folder can only have one branch
checked out at a time: if a second agent runs `git checkout` in the same folder, it silently
overwrites the first agent's uncommitted work. That's a **working-directory collision**, not a
merge conflict.

1. Before starting a task, create a dedicated worktree: `git worktree add ../coordinate-<task-slug> -b feature/<description>`
2. `cd` into that folder for every step of the task. Never work on it from the main checkout
3. Check `git worktree list` before creating a new one, to avoid duplicate folders for the same branch
4. Once merged: `git worktree remove ../coordinate-<task-slug>`

This doesn't replace normal conflict resolution. Worktrees only stop agents from clobbering each
other's working directory while a task is in progress.

## Before Starting Work

1. Use the task tracker declared at the top of this file (`ROADMAP.md`). If this file is silent on
   something, that's a doc gap, not permission to guess: ask.
2. Confirm your task doesn't overlap with an in-progress task from another session: check
   `ROADMAP.md` *and* `git worktree list` together
3. Mark the item in progress in `ROADMAP.md` **before** branching

## Change Docs Are the Source; Tasks Are Pointers

Most work here is an increment against a system that already exists. The carrier for that work is a
change doc in `documentation/active/<topic>.md`, and the pipeline is:

```
The owner writes the problem  →  agent investigates and enriches the doc in place
  →  the owner reviews inline with "> OWNER:"  →  agent files one ROADMAP.md item per `## Tasks` entry
  →  worktree per task, execute  →  doc moves to completed/ when the chain closes
```

Start from `documentation/guides/change-doc-template.md`.

### Required sections in every change doc

A change doc is ready for execution once it carries both of these at the end:

```markdown
## Delta
- ADDED: <behaviour that does not exist today>
- MODIFIED: <existing behaviour> — was X, now Y
- REMOVED: <behaviour> — and what replaces it

## Tasks
- [ ] T1 — <title> — ref: — depends: none — priority: high
- [ ] T2 — <title> — ref: — depends: T1 — priority: medium
```

`## Delta` states the change against **current** behaviour, not against an ideal. `## Tasks` is
machine-readable on purpose: `ref:` names the task's `ROADMAP.md` section or item. Every ROADMAP
item filed from a doc carries the doc's path, so the investigation travels with the task.

### The `> OWNER:` convention

Blockquote lines beginning `> OWNER:` are the owner's own review annotations, written inline at the exact
claim they respond to.

- They are **authoritative** and override the surrounding analysis, including analysis you wrote.
- **Never delete, reword, summarise, or "tidy up" a `> OWNER:` line.** Add below it; don't edit it.
- If a `> OWNER:` line contains a question or an instruction, it is unresolved work: do not move the
  doc to `completed/` and do not mark the chain done while one is outstanding.
- When your investigation contradicts a `> OWNER:` line, say so explicitly underneath it rather than
  quietly proceeding either way.

### Where status actually lives

| Question | Authority |
| --- | --- |
| Is *this task* done? | `ROADMAP.md` |
| Is *this chain* open? | `documentation/active/` vs `completed/` placement |
| What shipped in which version? | `CHANGELOG.md` |
| Anything else | **git is authoritative for nothing**: it is source control, not a tracker |

Checkboxes in a doc's `## Tasks` are a **mirror**. Tick `- [x]` in the same action as updating
`ROADMAP.md`, never one without the other. On disagreement, `ROADMAP.md` wins.

## Scratch Folders Are Never a Source of Truth

`.coordinate/` (ledgers, briefs, logs of releases run *on* other repos), `graphify-out/`,
`.remember/`, `.superpowers/`, `__pycache__/` and any `*-cache/` or `logs/` folder are tool working
state. They are gitignored, and they go stale silently.

- **Never cite one as evidence of project status.** `ROADMAP.md` is the record.
- Delete them freely; the tool regenerates what it needs.
- Individual Superpowers skills (`brainstorming`, `systematic-debugging`, `requesting-code-review`,
  `using-git-worktrees`) may be invoked ad hoc when useful. Its full methodology
  (`writing-plans` / `executing-plans` / `subagent-driven-development`) is **not** adopted: it
  would be a second planning system alongside `ROADMAP.md`. One planning system per repo.

## Design Quality

coordinate has no web UI. The `coordinator-status` mod draws inside Claude Code's terminal, so `/impeccable` and `PRODUCT.md` / `DESIGN.md` don't
apply. If a web page or app UI is ever added (a public site, a herdr-app panel with real layout
work), this section gets the full `/impeccable` workflow from the Moulin Intelligence template.

## If You're Blocked

Don't sit on a blocker silently or guess past it. Prefix the `ROADMAP.md` item `BLOCKED:` and leave
one line stating what's blocked and why, so the next session doesn't repeat the investigation.

## When Completing Work

Marking a task done is **mandatory**, not optional cleanup:

1. Merge your branch to `main` with `--no-ff` once the tests pass
2. Update `ROADMAP.md` (and `CHANGELOG.md` for a release) **immediately**, before closing the session
3. Never assume a task is done because code exists: verify the commit is on `main`
4. Remove the worktree once merged

## Commit Messages

- One logical change per commit
- Stage files by name: never `git add .` or `git add -A`
- Format: `<type>: <what changed>` (`feat`, `fix`, `docs`, `refactor`, `chore`, `test`); a release
  commit may read `coordinate <version>: <what changed>`, as the history does
- Body (optional): explain *why*, not *what*

## Verification Before Committing

"Code exists" is never proof it works.

1. Run `python3 -m unittest discover tests` from the repo root (153 tests, about 3 s on 2026-11-06)
2. For a script change, run the script itself once on a scratch repo or a fake adapter, the way a
   coordinator would call it
3. For a `coordinator-status` mod change, load it in a live Claude Code session (it loads from this
   checkout through `CLAUDE_CODE_PLUGIN_DIRS`) and look at the pane
4. Fix, re-run, re-verify before committing

**Skip only when** the change is docs-only or arranging the check would cost more than the risk.

## Code Review (Post-Merge)

Request a review with the `/code-review` skill for multi-task chains and anything touching
`ledger.py`, `merge.py`, `budget.py` or `wake.py`. Output findings to
`documentation/active/<feature>-code-review.md`.

| Severity    | Meaning                                             | Action            |
| ----------- | --------------------------------------------------- | ----------------- |
| Bug         | Incorrect behavior, crash, data loss risk           | Fix before release |
| Improvement | Works but fragile, inefficient, or hard to maintain | ROADMAP item      |
| Suggestion  | Stylistic, optional, nice-to-have                   | Author discretion |

Skip for single-file, cosmetic or docs-only changes.

## CI Requirements

**Not wired yet.** Lean governance calls for CI running `python3 -m unittest discover tests` on
every push; the item is in `ROADMAP.md` (2.30.0 left no personal paths for a runner to meet).
Until it exists, step 1 of § Verification is the gate, run by hand before
every merge.

## Before Implementing Anything New

Check current docs (Context7, or the tool's own `--help` / manual) before writing code against an
API you haven't touched recently: Claude Code, the Devin CLI and herdr-core (`hc --skill`) all
change faster than training data.

## Documentation Rules

See `documentation/AGENTS.md` for the full taxonomy. Key points:

- New work → `documentation/active/`
- Completed work → `documentation/completed/`
- Evaluations and bug write-ups → `documentation/history/` (bug fixes in `history/bugfixes/`)
- Guides → `documentation/guides/` (one doc per topic, update in place)
- `CHANGELOG.md` entry on every release

## Ground Rules & Architecture Philosophy

- **YAGNI**: build what the current task needs, not what a hypothetical future task might.
- **DRY, but not prematurely**: duplicate once; extract the shared abstraction on the third
  repetition, when the real shape of the pattern is clear.
- **KISS**: the simplest thing that correctly satisfies the current requirement wins.
- **Single source of truth**: every piece of state (task status, config, adapter keys, rules) has
  exactly one authoritative location; everything else references it.
- **Boring technology first**: the scripts are Python 3 standard library only. Keep it that way
  unless a task genuinely can't be done without a dependency.
- **Delete over deprecate**: dead code, unused flags and abandoned experiments get removed. Git
  history is the "just in case."
- **Explicit over implicit**: no hidden side effects, no convention that isn't written down in this
  file, `README.md`, `SKILL.md` or `documentation/guides/`.

## Tech Stack Quick Reference

- **Skill:** `plugins/coordinate/skills/coordinate/SKILL.md` plus `scripts/*.py`, Python 3.10+,
  standard library only; tests in `tests/` (`unittest`)
- **Mod:** `plugins/coordinator-status/`, TypeScript loaded by Claude Code's plugin runtime
- **Runs on:** Claude Code, git, and optionally the Devin CLI (Devin routes) and herdr-core `hc`
  (planned runner, `ROADMAP.md`)
- **Per-repo config:** `.claude/coordinate.json` in each repo the skill coordinates (adapter keys:
  `plugins/coordinate/skills/coordinate/references/`)

## Production Deployment

No server. coordinate ships as a Claude Code plugin marketplace from its GitHub repo. Users
install it with `/plugin install` (`README.md` § Install); the release steps are in
`README.md` § Developing.
