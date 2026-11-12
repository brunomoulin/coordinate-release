# The Per-Repo Adapter

Everything repo-specific lives in one JSON file, so the skill and its scripts stay generic.
`init.py <repo>` drafts it.

**Where:** `<main checkout>/.claude/coordinate.json` (committed; travels with the repo), else
`~/.config/coordinate/<main checkout folder name>.json` (private to the machine). Scripts find the
main checkout from any of its worktrees.

**Project state** lives in `<main checkout>/.coordinate/` (gitignored: `releases/`, older `ledgers/` and `briefs/`,
`logs/`, `lessons.md`). It stays out of git because `merge.py` refuses a dirty main: a tracked
ledger would block every merge. The close-out copies the finished ledger into the repo's docs when
`ledger_archive` says so. Relative paths below resolve against the main checkout.

| Key | Default | Meaning |
|---|---|---|
| `gates` | required | List of `{name, dir, cmd}`, run in order by `gates.py` and after every merge |
| `main_branch` | `main` | |
| `worktree_parent` | `..` | Worktrees are `<parent>/<repo>-<task>` |
| `env_files` | `[]` | Gitignored files copied from main into each new worktree (e.g. `backend/.env`) |
| `worktree_setup` | `[]` | Commands run in a new worktree (e.g. `npm ci`) |
| `path_prefix` | `''` | Prepended to PATH for every gate and DB run, when the gates need a different toolchain than the shell's |
| `gate_grep` | | Regex picking the summary lines from gate output |
| `install_on_change` | `{"package-lock.json": "npm install --no-audit --no-fund"}` | Lockfile name → command run in its folder when a merge (`merge.py`, `eyeball.py`) changed it; `{}` turns it off |
| `test_slots` | `1` | Test runs allowed at once (`testlock.py`); raise when parallel runs stop timing out. Each run gets `TEST_WORKER_BUDGET` (80% of the cores ÷ slots; all cores in away mode) for the repo's test config to size its worker pool, and runs at `nice -n 10` |
| `concurrency` | `{devin: 3, sonnet: 2, opus_review: 1}` | Parallel implementers and reviewers |
| `db_test` | `null` | `{dir, cmd, new_glob?, default_timeout_ms?}` for the shared-database tier; run only through `db.py` |
| `db_snapshot` | `null` | Command printing one JSON line about the DB (gets the worktree path as last arg). Include `pending_migrations: []`. Its script is trusted on first run; a later change stops `db.py` (exit 8) until `--trust-snapshot` |
| `append_only` | `[]` | Files where both sides only add entries; conflicts there are resolved keep-both |
| `handoff` | `null` | The repo's agent handoff log; `merge.py` writes entries under its `## Log` heading line |
| `handoff_agent` | `Claude (coordinator)` | The agent name in those entries |
| `taskmaster` | | The task register file implementers must never edit |
| `owner_marker` | `null` | Line prefix the owner annotates docs with (e.g. `> JD:`); the close-out brief says such lines are never deleted |
| `owner_name` | `null` | The owner's name as reviews and dispositions write it; close-out counts a disposition naming it, or "owner", as handed to the owner |
| `change_docs` | | Where change docs go (review files stay in `<briefs>/` until the close-out) |
| `repo_rules` | | The house rules file (e.g. `AGENTS.md`); `shared_rules`: an optional shared rules path or URL |
| `dev_ports` | `[]` | Ports the coordinator's dev servers use |
| `eyeball_verify` | `{url: null, accounts_file: null, rules: []}` | The machine eyeball brief (`eyeball.py verify`): the eyeball stack's URL (`--url` overrides), a gitignored file naming the dev logins the agent may use (never the passwords in the adapter: it is committed), and repo-specific Hard rules, one string each (the first pilot: never run `./dev-restart.sh`; 5 logins / 15 min; the audit log is permanent) |
| `eyeball_build`, `eyeball_howto` | `null`, `null` | For an eyeball that is not a dev server (a browser extension): a shell command `eyeball.py` runs in the eyeball tree after the fold and installs (its failure stops the fold's report), and a line printed by `eyeball.py` and every `checks add`, with `{worktree}` and `{release}` filled: the folder to load unpacked and the reload step. The eyeball tree's path is fixed per release, so an unpacked extension keeps its id and settings |
| `tracker` | `null` | The repo's task tracker, asked at init (question 7): `"markdown"` (the `tasks_file`), `"taskmaster"` (the `taskmaster` register) or `"none"`. Unset: `tasks_file` set means markdown, an existing `taskmaster` file means taskmaster, else none. `status.py` prints the tracker's line and `closeout.py` checks it against the ledger |
| `tasks_file` | `null` | The Markdown checklist (`- [ ] T64 — text`; `init.py` creates `TASKS.md` when the repo has no tracker): `status.py` lists the open tasks the ledger has not started, and `closeout.py` ticks the ones the ledger shows MERGED (commit the file with the close-out). With TaskMaster the register is read only: status shows pending and in-progress counts and the tasks MERGED in the ledger but not done there, and the close-out prints them for `set_task_status` |
| `closeout_skill` | `null` | The repo's release close-out skill |
| `release_dir` | `.coordinate/releases` | One folder per release (2.12.0 on): now, decisions, eyeball, timeline, history, briefs/; `index.md` lists the closed ones |
| `ledger_dir`, `briefs_dir`, `log_dir` | `.coordinate/ledgers`, `/briefs`, `/logs` | One-file ledgers and briefs of releases begun before 2.12.0; logs (all releases) |
| `live_caps` | `{"now": 60, "decisions": 60, "eyeball": 40, "lessons": 80}` | Line caps on the files a resume reads; `status.py` prints `OVER CAP` past them |
| `lessons_file` | `.coordinate/lessons.md` | Where each release's lessons are appended |
| `ledger_archive` | `null` | e.g. `documentation/releases/{release}-ledger.md`: `closeout.py` copies the ledger there; a value ending in `/` means `<folder>/{release}.md`, and `preflight.py` FAILs a fixed file name |
| `session_limits` | `{soft_tokens: 450000, hard_tokens: 650000, tight_tokens: 400000, closeout_tokens: 60000, merges_warn: 10}` | SKILL.md §8 |
| `budget` | `{surplus_pace: 0.7, tight_pace: 1.1, five_hour_fit_pct: 85, tight_headroom: 0.75, build_cost_5h: {haiku: 3, sonnet: 10, opus: 20}, build_cost_7d: {haiku: 0.5, sonnet: 2, opus: 5}, critical_pct: 90, surplus_reset_hours: 24, surplus_reset_pct: 70, pace_floor_pct: 25, overrides: {}, mode: auto}` | Posture thresholds (`five_hour_fit_pct`: a Claude build launches only while 5h % + its `build_cost_5h` stays under it, any posture; `tight_headroom`: under TIGHT, a Sonnet build launches when the week left after its `build_cost_7d` covers this share of on-pace (routing.md); tune the costs from the ROUTE rows' `5h=`/`7d=`; `pace_floor_pct`: the least week-elapsed % pace divides by); `overrides` per route: `false` vetoes it, `true` allows it whatever the posture (a Claude build still has to fit), unset lets the posture decide; `mode`: `auto`, or `off` (posture OFF: every route, no fit check, no park; ROUTE rows still record the spend) |
| `devin` | `{model: swe-2-high, fusion_model: <Opus High Fusion>}` | Any Devin model id, named on every launch. Its cost comes from the live catalog (below): a model not listed as Free spends the Devin quota, and its builds stop when the quota is exhausted |
| `routing` | `{default_builder: devin}` | Who builds first: `devin`, `sonnet`, `haiku` or `opus`. Leads `budget.py`'s build list whenever the posture or a tick allows it; never overrides the posture. Presets leave it and the Devin models alone. `init.py` drafts `sonnet` when the `devin` CLI is missing |
| `system_one` | `{mode: off}` | `shadow`: `s1_shadow.py` sends each build brief's text to TypeSafe's hosted Jev with the questions in `references/s1-coordinate-risk.json` and logs an `S1` row; nothing is routed by it. Needs `TYPESAFE_API_KEY` (environment or `~/.config/typesafe/env`). `off`: nothing is sent |

**Release settings.** `/coordinate settings` (`settings.py`) writes a release's choices as timeline
rows `SET <dotted.key>=<json value>` (who `owner`). The latest row per key wins and
`SET <key>=default` drops it. Precedence: release rows, then this file, then the defaults above;
`budget.overrides` merge per route, so a release can turn on a route the repo vetoed.
Every script given `--release R` reads them. A row whose value is not JSON is skipped with a warning.
`settings.py set --repo` edits this file; when it is committed, on a `chore/settings-<date>` branch
merged with `--no-ff` (main must be clean). The knobs and their reasons: `settings.py show`.

**Devin catalog.** `devin models list --format json` gives each model's `cost_tier` (Free, Low,
Med, High cost) and `cost_summary`. `preflight.py` refreshes the cache
`~/.claude/coordinate/devin-models.json`, and warns when the adapter model is paid or stopped
being free. No `devin`, or the command fails: the last cache; no cache: SWE-2 high and medium count
as free.

v1 keys `session_limits.context_tokens`, `session_limits.merges` and `review.quota_threshold_pct`
are ignored; `preflight.py` warns about them.

Examples: `examples/adapters/` in the coordinate repo.
