# Tooling Facts

Facts the runs paid for once. Scripts already handle most of them; this is for when you work by
hand.

## Claude Code

- Auto mode's classifier (Claude Code's permission mode, not the coordinator's away mode) reads context. After `/clear`, it no longer sees why Devin launches are
  allowed, so the allow rules `Bash(devin -p *)` and `Bash(devin list *)` must be in settings.
  A session cannot add them itself (refused as self-modification): the owner adds them.
- `/clear` keeps background shells running, and each one that ends starts a turn in the cleared
  session. `/exit` stops them ("Exit and stop tasks"), children included; a process that left with
  `setsid -f` lives on (tested 2026-10-30, claude 2.1.312), which is what `chain.py` does.
- `ctx_execute_file` cannot read files in other worktrees. Use Read or Bash there.
- `$CLAUDE_CODE_SESSION_ID` names the session's transcript; `session.py` reads its context size.
- A background `Agent` cut off by a limit resumes with SendMessage in the same session only.
- Opus has a 1M context window; the coordinator's limits (450k soft, 650k hard) are our own.
  A merge costs about 18k of context (Devin does the build); a resume about 10 minutes and ~100k.
  The merge count is not a limit, only `merges_warn`: a 5-merge cap once parked a session at a
  quarter of its context. When `session.py` exits 3 on merges alone, finish the wave if context
  is under ~300k and park on context.
- The status mod writes `~/.claude/coordinate/usage.json` (5-hour and 7-day windows, their
  resets, context). Without it, `budget.py` reports the 7-day signal as unknown.

## dcg (the shell guard)

- Long heredocs, heredocs containing `${…}`, and `python3 -` / `python3 -c` with backticks get
  blocked. Write a script file with Write, then run it. Commit messages go in a scratch file:
  `git commit -F <file>`.
- `git -C <dir>` inside a shell `for` loop is blocked, and so is `W=…; git -C $W …` (variable
  expansion). One plain command per worktree with literal paths, or `status.py`.
- `> ~/...` is blocked; use `>>`, or write under the scratchpad or `/tmp/claude-*`.
- `rm -rf` is blocked; `git branch -d/-D`, `git worktree remove`, `git checkout --`,
  `git restore`, `git reset` are the owner's unless their allowlist covers them. Hand them the exact
  command (`status.py` and `closeout.py` print them).
- Never route around a block (no script that runs the blocked command for you). If a block is
  wrong, tell the owner.

## Devin CLI

- `devin list --format json`, never bare: bare is an interactive picker and returns nothing.
- Session ids come from `devin list --format json` in the worktree's directory.
- Devin Desktop cannot open a session the CLI holds; resume fails while Desktop holds it.
- Devin's config default model is not what you want per task: pass `--model` on every launch.
- When the owner launches Devin themselves, give them the log path, then check it with `tail` on the log
  and `pgrep -af "devin -p"`. All output goes to the log; their terminal shows nothing.
- A reply can be lost to Devin's output-token limit: the brief caps it at 60 lines; recover with
  `devin -p -r <id>` and a reply-only brief.
- Devin once `--amend`ed into the wrong commit and once ran `git stash pop` on another worktree's
  stash. Check `git log <main>..<branch>` and `git stash list` after each run.
- Billing (the owner's plan, 2026-10-13): SWE-2 standalone is free, so implementer rounds on it are
  unlimited. Fusion and other models use a daily and weekly quota, and a Fusion pair bills only
  its main model (Opus), not the SWE-2 sidekick. "daily usage quota has been exhausted"
  (resource_exhausted) came from a Fusion review while SWE-2 builds kept going. A refused
  launch: tell the owner, who checks the plan. Budget Fusion against the daily quota. **Probe each
  model before rerouting:** on a quota error, launch a one-line probe on `swe-2-high` and another
  on the Fusion model, and reroute only the one that fails (second pilot v1, 10-30: Fusion ran
  out, the coordinator moved everything to Claude, and plain SWE-2 still worked until the owner said so).
- Local model work (E2E, Ollama) runs on the owner's laptop, which hard-stopped twice on 2026-11-02
  (heat suspected). A brief that runs a local model names the allowed models (v1: `gemma4:26b`,
  `gemma3:12b`, `ornith`; never `qwen3.6:27b`) and runs one GPU job at a time.
- Never edit `~/.claude` or other harness state (v1: the coordinator repaired a corrupted
  `session-env/<id>/sessionstart-hook-3.sh` itself, and the next build was denied as
  "Self-Modification"). Name the file and the fix; the owner runs it.
- dcg (the command guard) blocks `S=<dir>; ... $S/x.py` in a command that also runs git
  (`core.git:git-alias-semantic-unverified`): write the literal script path, or keep git out of that
  command. It also blocks long heredocs, so write briefs with the Write tool, and a launch chained
  after a brief write must `test -f <absolute brief path>` first (a blocked write once let Devin run
  on a missing brief; Devin also fails on a relative `--prompt-file`).
- Devin's own hook blocks `$(cat ...)`: briefs say `git commit -F <file>`. rtk rewrites `find` and
  fails on `-not`/`-exec`: use `/usr/bin/find`. dcg blocks `git worktree remove` and `branch -D`,
  and `wchop` skips an eyeball worktree: print every cleanup as one whole line for the owner to paste.
- Devin loads the repo's `AGENTS.md`, `CLAUDE.md` and `.windsurfrules` as always-on rules
  (`devin rules list`) and follows them over a brief's rule that disagrees (it called the task
  register's status tool "per workflow" against a brief that said never). The brief opens with
  a "Hard rules, these OVERRIDE <repo_rules>" block naming each overridden section.
- Trust Devin's reasoning and dispositions, not its gate reports: a red build was pushed under
  three "tsc clean" reports because `tsc -b` is incremental and exits 0 having checked nothing.
  Rerun the gates (`gates.py`); test a "pre-existing on main" claim with one `git blame`.
- Chaining rounds: wait on a marker unique to the predecessor (`end 380-r2`), matched as a whole
  line. A substring wait once matched an earlier line and two Devins ran at once. `chain.py` does
  this.

## Machine

- Two full test runs at once can time out real-timer tests (vitest sizes its pool to the core
  count per run). `testlock.py` queues runs on adapter `test_slots`; raise it once the repo's
  tests survive parallel runs.
- inotify (65536 watches) runs out near seven worktrees: `tsx watch` and vite crash with ENOSPC,
  and a crashed `tsx watch` can leave its child listening on the port. Eyeball servers start
  without watching (`npx tsx src/server.ts`; vite with `CHOKIDAR_USEPOLLING=1`), and merged
  worktrees are removed at merge time.

## Shell

- `cmd | tail || fallback` never falls back: the pipe's status is `tail`'s. Use
  `set -o pipefail`, or no pipe on a step whose failure matters. The scripts check each step.

## Databases (repos with a DB-test tier)

- The DB tier shares one database: one run at a time (`db.py` holds a lock; exit 6 when another
  run has it). Implementers run DB tests through `db.py` only; `--reviewed` is the coordinator's.
- `db.py` takes test paths relative to `db_test.dir` and strips a leading `<dir>/`. "No test files
  found" means a wrong path, not a failing test.
- Before the DB tier, compare the DB's migration table with the branch's migrations folder. A
  pending migration fails every reader. `db.py` stops with exit 5 when the snapshot reports one.
- Backend DB tests may sit outside the type-check (`tsconfig` excludes tests): a changed return
  type can break an existing DB test with every gate green. The coordinator's DB run catches it.
- A probe that gates a destructive step lists every route that can satisfy the gate and prints an
  explicit status column, not a date to interpret.
- DB scripts in npm workspaces need `pg`/`dotenv` from the root `node_modules`.
- Prod access is the owner's. The coordinator writes read-only queries; the owner runs them.
