# Changelog

## 2.33.0 (2026-11-09)

- **`/coordinate settings`.** A picker on `AskUserQuestion`: presets Balanced (today's defaults),
  Frugal and All-out, or Custom over three groups (who does the work, how hard to spend, when to
  hand off). Plain words work too ("build with Opus", "budget off"). New `settings.py show | set |
  preset`: every knob shows its value, where it comes from (release, repo, default) and why.
- **Release scope by default.** A release's settings are `SET <key>=<json>` rows in its timeline,
  over the repo adapter, over the defaults; every script given `--release` reads them. Repo scope
  (`--repo`) edits the adapter, committing it on a `chore/settings-<date>` branch merged `--no-ff`.
- **Ticked means allowed.** `budget.overrides.<route>: true` allows a route whatever the posture (a
  Claude build still has to fit the 5-hour window). `budget.mode: off` gives posture OFF: every
  route, no fit check, no budget park; ROUTE rows still record the spend.
- **Who builds first.** `routing.default_builder` (devin, sonnet, haiku, opus) leads the build
  list. `init.py` drafts `sonnet` when the `devin` CLI is missing, and a missing `devin` is only a
  warning then.
- **Devin cost is read live.** `devin models list --format json` (cached in
  `~/.claude/coordinate/devin-models.json`, refreshed at preflight) says which models are Free.
  Any Devin model id is accepted; a paid one spends the Devin quota and leaves the build list when
  it runs out. `chain.py` then stops with `Free now: ...` and the line that switches the release.
  Preflight warns when the adapter model is paid or stopped being free.
- **Away-mode line.** The `autoMode.environment` line allows any model `devin models list` shows
  for the account, not SWE-2 only, so a release's model switch and the quota-out fallback run
  unattended. Preflight says to re-paste an old line once.
- Fix: `adapter.load` no longer shares `DEFAULTS`' nested maps with the loaded adapter.

## 2.32.1 (2026-11-09)

- **The pane follows your skin (mod 0.11.0).** With the skins mod on a skin made with `/skin` or
  its designer, the pane's status colours (ok, warn, err, muted, body text) and highlights (`read`,
  `user`, `write`, `web` slots) come from that skin, and change when it does. Coordinator gold,
  Claude orange, Devin teal and the sprites stay. Built-in skins, slots a made skin leaves to its
  base, and no skins mod keep the pane's own colours (skins keeps built-in palettes in its code;
  ROADMAP has the request to share them).

## 2.32.0 (2026-11-07)

- **The status pane opens by itself (mod 0.10.0)** the first time a coordinator starts in a
  session: a prompt that starts with the skill's own phrases (`coordinate <R>`, `/coordinate`,
  "resume coordinator", "pilot coordinator", "coordinator on <R>") or the main session loading
  the skill. Only in a repo with an adapter, once a session: closed after that, it stays closed
  until `/coord-status`. A subagent loading the skill does not open it.
- **README:** what it does in one paragraph, install and update steps, a quick start, a table of
  modes and commands (watched, away, resume, wake, `/coord-status`), and what the pane shows.
- `publish/README.md` (private): the routine is now fix here, publish, update the public install.

## 2.31.0 (2026-11-07)

The coordinator's auto mode is now **away mode**, so it is not mistaken for Claude Code's auto
permission mode (a refused Agent call in one was read as a reason to leave the other).

- **`/coordinate away <R>`, `ledger.py away <ledger> on|off`.** It writes `AWAY on|off` rows;
  `now.md` says "Away mode is on" and `status.py` prints `AWAY MODE`. A ledger turned on before
  2.31.0 (`AUTO on` rows) still reads as on. `decide --auto` and the A<n> pick ids are unchanged.
- **Pane badge (mod 0.9.0):** `status.py --json` gives `away`, and the pane header shows
  `· away mode` beside the release. Read-only: turning it on stays the owner's word in chat.
- SKILL.md §Claude reviewer names the refusing mode as Claude Code's auto permission mode.

## 2.30.2 (2026-11-06)

`init.py` fixes found running `/coordinate init` on a TypeScript repo with a hand-tuned adapter.

- **Type-check gates by command:** a script running `tsc`, `vue-tsc`, `svelte-check` or `astro check`
  is a gate whatever its name (`"compile": "tsc --noEmit"` was missed). A `build` that runs `tsc`
  stays a build; watch modes and `pre`/`post` hooks are not gates.
- **Cheapest-first gates:** type check, lint, test, build, across packages and the Makefile.
- **Re-run on an existing adapter** asks only the questions for keys it lacks and prints those keys
  with the detected values. Keys set differently from the draft are listed once as kept. Nothing
  missing prints `adapter up to date`. The task file it creates follows the adapter's own tracker.

## 2.30.1 (2026-11-06)

No project names or client details in the public tree.

- **`> OWNER:`** replaces the owner's initials as this repo's inline review marker (AGENTS.md, the change-doc
  template). Repos that set adapter `owner_marker` keep their own.
- **Pilots by role:** the first client project is "the pilot" with its release number kept (`pilot 2.11.0`); the
  browser-extension project and its product name are "the second pilot".
- **Client details cut from the stories:** upload paths, list rows and a data leak replace the
  domain terms; the eyeball test fixture uses a placeholder name. Each rule keeps its reason.

## 2.30.0 (2026-11-06)

Depersonalize (ROADMAP quick win 5): the skill names no owner and no client project.

- **"The owner" everywhere.** SKILL.md, references, scripts, tests and this file say "the owner"
  (they/their) where they named one person; owner-facing output says "you" (`For you`, `You: ok or
  override each`). `ledger.py decide --by owner` replaces the old name.
- **`NEEDS OWNER`** is the machine eyeball's verdict for what an agent cannot judge. `checks.py`
  reads any `NEEDS <WORD>` heading as `needs-human`, so older reports still import.
- **Adapter `owner_name`** (default none). The close-out counts a disposition as `to owner` when it
  says "owner" or names `owner_name`; set it in a repo whose dispositions name the owner.
- **The client project is "the first pilot"** in prose and `app` in test fixtures; the example
  adapter is `examples/adapters/fullstack-db.json`, with no personal paths.
- 156 Python tests (3 new in `test_owner_name.py`) and the mod's 11 pass.

## 2.29.1 (2026-11-05)

Review severities agree (the second pilot's v2-perf finding 4).

- **`findings.py` reads `Risk` and `Nit` rows** beside `Bug`, `Improvement` and `Suggestion`
  (`SEVERITIES`). v2-perf's briefs asked for Bug / Risk / Nit, so `dispose.py` printed "no
  findings rows" and the Disposition column was filled by hand; the close-out's overrule counts
  and `audit.py` missed the same rows. On v2-perf's 8 review files, 45 rows read where 6 did.
- **`review-brief-template.md` names the severities**, with a line each for Bug, Risk and Nit; a
  test holds the template's list equal to `SEVERITIES`. 153 tests.

## 2.29.0 (2026-11-05)

A Claude review without `Agent` (the second pilot's v2-perf finding 3).

- **`claude_review.py`** runs a review, re-review or critique brief as `claude -p --model
  sonnet|opus --permission-mode acceptEdits --output-format json`, brief on stdin, in the task's
  worktree, with read tools, Write, and read-only git including `Bash(rtk git:*)`. In auto mode
  the context-mode hook rewrites every Agent prompt after the classifier checked it, so the
  classifier refused review-T87 four times; the hand-typed workaround is now one command. It
  writes LAUNCHED (`who` = the model, so the inferred ROUTE and the close-out read
  `sonnet_review` / `opus_review`) and EXITED with `claude_tokens=` and `claude_usd=` from the
  JSON result (`modelUsage`, else `usage`; checked against claude 2.1.318). A build brief or a
  Haiku model is refused.
- **`ledger.py` OUTCOME rows count those runs:** `claude_cost` adds the `claude_tokens` /
  `claude_usd` of EXITED rows under the task or a review of it, with or without the
  coordinator-status mod. Before, a `claude -p` reviewer was missing from the row, which the v3
  router's shadow test needs whole.
- SKILL.md §3 names it. 150 tests.

## 2.28.0 (2026-11-03)

Any task tracker, not only a Markdown file (2.27.0's `tasks_file`).

- **`init.py` asks what the repo tracks tasks with** (question 7) and detects it: TaskMaster when
  `.taskmaster/tasks/tasks.json` exists, an existing `TASKS.md` / `documentation/TASKS.md` /
  `TODO.md`, else the default `TASKS.md`, which it creates (no dependency). Adapter `tracker`
  (`markdown`, `taskmaster`, `none`) records the answer; unset still works from `tasks_file` or an
  existing `taskmaster` register, so the first pilot needs no change.
- **TaskMaster repos get a read-only line.** `status.py` prints the pending and in-progress counts,
  the tasks MERGED in the ledger but not done in TaskMaster, and in-progress tasks the ledger never
  names; `closeout.py` lists the merged-but-not-done ones for `set_task_status`. The scripts never
  write the register. The pilot's tasks are plain numbers matching the ledger; on its 2.12.0 ledger the
  line finds 540 and 543. It lists no "open tasks": TaskMaster has no release field, so that is the
  whole backlog.
- **Markdown behaves as in 2.27.0**, through the same `tasks.py` entry points.

## 2.27.0 (2026-11-03)

Portability, from the second pilot's v1 lessons (what assumed the first pilot).

- **Eyeball for a browser extension.** Adapter `eyeball_build` runs in the eyeball tree after the
  fold (v1's `.output` was stale until `gates.py` ran there); `eyeball_howto` prints the folder to
  load and the reload step after the fold and with every `checks add`.
- **`init.py` proposes the generated-types step**: `wxt prepare`, `prisma generate`,
  `svelte-kit sync`, `nuxi prepare` into `worktree_setup` when the package depends on it and its
  own `postinstall`/`prepare` does not run it (v1 needed `npx wxt prepare` after `npm ci`).
- **Auto mode in a new repo.** `init.py` prints the `autoMode.environment` line for the repo's
  sibling worktrees; `preflight.py` WARNs, with the line, when no entry in the user or project
  settings names the repo (v1's classifier denied launches as "Auto-Mode Bypass").
- **Adapter `tasks_file`** (a Markdown checklist, new `tasks.py`): `status.py` lists open tasks the
  ledger has not started; `closeout.py` ticks the ones the ledger shows MERGED. On v1's
  `TASKS.md` it finds 47 task ids and names the two never started.

## 2.26.0 (2026-11-03)

Review overrule counts, from the second pilot's v1 lessons ("Review files the close-out could not
match to a route", "Routing signal").

- **Rounds named `review-T64r3` match `v1-T64-r3-rereview.md`.** v1's 14 `unmatched` findings were
  three Sonnet re-reviews whose ledger task had no hyphen before the round. `closeout.py` also
  prints any review file it still cannot route.
- **Overrules count declines, not confirmations or repeats.** A disposition such as "No change:
  checked, holds" is `noted`, and the same decision typed into several rows of one review counts
  once (the rest are `repeat`); neither enters the percentage. v1's `sonnet_review` goes from 14%
  to 10% (36 of 355; Opus 6%, Fusion 4%). What is left is mostly "by design" and intent calls, not
  reviewer errors: no routing change.

## 2.25.0 (2026-11-03)

From the second pilot's v1 lessons ("Process" and "Tooling facts").

- **`wake.py --after-work`** waits until the repo's Devin runs and chains have ended (a look a
  minute, 12 h cap) before waking. SKILL.md §8: a park with work still running arms the wake at any
  5-hour %, with `--after-work`; v1's two queued rounds had sat unread until morning. The park
  ends by saying plainly whether a wake is armed.
- **A resume sees a wake in flight.** An armed `wake.py` writes `<log_dir>/wake-<R>.pid`;
  `status.py` prints `WAKE ARMED pid N` while it sleeps and `WAKE SESSION RUNNING <id>` while a
  woken background session is still coordinating the release (SKILL.md §0: wait for its park or
  `claude stop` it, never work beside it).
- **Rules from the v1 run, text only:** probe each Devin model before rerouting on a quota error;
  never edit `~/.claude` or harness state; a brief that runs a local model names the allowed models
  and runs one GPU job at a time; `now.md` is the handoff when `handoff` is null; literal script
  paths where dcg blocks `S=…`; `test -f` the absolute brief path before a launch. In SKILL.md Red
  Flags, `references/tooling-facts.md` and `references/routing.md`.

## 2.24.0 (2026-11-03)

From the second pilot's v1 lessons (`.coordinate/lessons.md`, "Fix first").

- **`ledger_archive` accepts a folder.** A value ending in `/` means `<folder>/<release>.md`;
  `preflight.py` FAILs a value with no `{release}` that is not a folder (a fixed name overwrites
  the last release's archive).
- **`closeout.py` keeps going when the archive step fails**, so Cleanup and Next always print; it
  exits 1 at the end and says what failed.
- **The archive is scanned for key-shaped strings before it is written** (Anthropic, AWS, GitHub,
  Google, Slack keys, private-key headers, `API_KEY=...` lines). A hit refuses the write, names the
  lines, and leaves the ledger untouched for redaction.
- **`session.py <repo>` without `--release` no longer crashes** (`merges_since` checked the ledger
  path before its own release check).
- **`preflight.py` WARNs about untracked paths on main** (v1: `.codex/`), the paths `merge.py`
  would refuse at the first merge.

## 2.23.0 (2026-10-30)

The second pilot's v1 park waited out a 5-hour reset by hand: four chains were running, so
`wake.py` refused to arm.

- **`chain.py` outlives the Claude session.** After checking its items it hands the chain to a
  worker that leaves with `setsid -f`, so `/exit` or a closed terminal leaves the chain and its
  Devins running. The launcher stays as a follower: it relays the output and ends with the worker,
  so a live session still gets its notification and exit code (1 when the queue stopped or the
  worker died). The output is kept in `chain-<first brief stem>.out` beside the briefs, the only
  place a stop message lands once the follower is gone.
- **`wake.py` refuses only runs a `/exit` would kill**: those with a `claude` process among their
  ancestors, which means a bare `devin -p` or a chain started before this release. Armed, it says
  that "Exit and stop tasks" stops only a chain's follower: the dialog lists the chain as stopping.
- **SKILL.md §3 and §8:** near the 5-hour cap launch through `chain.py`. A woken session gets no
  notification for a chain the old one started, so it reads `queue.log` and watches with Monitor.
- Tested live, claude 2.1.312: a real Devin launched from a real session's background shell ran
  through `/exit` and a closed terminal, and wrote its log and marker.

## 2.22.0, mod 0.8.1 (2026-10-30)

- **The 5-hour window no longer sets the posture.** Posture comes from the weekly budget only:
  CRITICAL at 7d ≥ 90%, TIGHT at pace > 1.1, else SURPLUS/ON PACE as before. The 5h window keeps
  doing its two jobs — the per-launch fit check (5h % + the build's `build_cost_5h` under
  `five_hour_fit_pct` 85%, `DOES NOT FIT` naming the reset) and, near its cap, arming `wake.py`
  (SKILL.md §8: a doc rule, never a posture trigger). Adapter `budget.five_hour_tight_pct` is gone;
  `session.py` limits follow the weekly posture only. In the second pilot's v1 run a 71% 5h
  window turned the week-healthy posture TIGHT, rerouting builds to Devin and dropping the
  coordinator's context limits.
- **`checks waiting` splits "waiting on you" from "in a fix round"** (`waiting on you: 1 open ·
  in a fix round: 1 (T19) · <path>`, only non-zero parts): a `feedback` check is the coordinator's
  fix round, not the owner's queue. `eyeball.py checks fixed <id> [note]` records the fix landed and
  moves the check to `recheck`, waiting on them again; `checks ok` accepts it.
- **The pane's merged count reads the ledger's MERGED rows.** It counted tasks whose *latest*
  ledger row starts with MERGED — but `merge.py` writes the OUTCOME row right after MERGED, so a
  merged task's latest row is OUTCOME and the count read 0. `status.py --json` now flags `merged`
  on any task with a MERGED row; the pane and band count it (latest-event fallback on older
  status.py), same total as before.

## 2.21.0, mod 0.8.0 (2026-10-28)

- **MAP rows unfold into their changed files** (Phase D slice 3). ▸ beside a worktree draws its
  files as a tree, after Filetree: folders first, a lone child folder folded into its parent's
  path, git's letter per file (A M D, `?` untracked), lines +/− summed up the folders, ● on a file
  not committed yet. ▾ folds it again.
- **`status.py --json` lists each worktree's `files`**: a branch's since its fork point from main,
  committed or not; main's uncommitted ones. 40 per worktree, the rest counted in `files_more`.

## 2.20.0, mod 0.7.0 (2026-10-28)

- **Claude tokens and ≈$ per task in the OUTCOME row** (`claude_tokens=`, `claude_usd=`; also
  columns of `ledger.py outcomes`). The coordinator-status mod writes each closed subagent row to
  `~/.claude/coordinate/agents/<session>.json`; `ledger.py` sums the rows whose description starts
  with the task id or a review of it (`466 …`, `review-466 …`), from a session in this repo, ended
  between the task's first row and its merge. SKILL.md §3 names the description rule. `?` without
  the mod; Devin runs stay out (free or paid quota). A bundled review counts toward each task in it.
- **`fusion_review` in every posture.** It spends the paid Devin quota, not Claude's, like
  `devin_fusion`; an agreed review trial no longer needs `--override`. TIGHT and CRITICAL still
  send reviews to Fusion first.
- Savvy Progress is uninstalled (it registered the same `step` tool as the mod).

## 2.19.0 (2026-10-28)

Four findings from the pilot 2.11.0 trial.

- **`swe2_review` route.** SWE-2 critiques and re-reviews Claude-built work, free, in every
  posture: in the trial it found 466's one real UI defect and a data leak. Like
  `sonnet_review`, it never replaces the Opus or Fusion review before merge. `infer_route` maps a
  Devin `review`/`critique`/`rereview` task to it, and `closeout.py` counts its overrules.
- **Devin's weekly quota message counts as out.** `DEVIN_OUT` now matches "weekly usage quota has
  been exhausted", which kept Fusion allowed in the trial.
- **The budget line shows the pace floor:** "at 7% of week (floor 25%)" while the floor applies,
  so "7d 11% at 7% of week (pace 0.44)" adds up on sight.
- **Brief template, review fixes:** a fix that adds a reader, query or endpoint names the
  visibility and permission rule it obeys (466 r2 added a reader that skipped document
  visibility).

## 2.18.1 (2026-10-27)

- **The implementer brief points at the graph.** Where the repo has `graphify-out/graph.json`, the
  brief tells the implementer to find code with `graphify query`/`path`/`explain` before grep,
  passing `--graph <main checkout>/graphify-out/graph.json` (the folder is gitignored, so a
  worktree has none). Structure questions only: a broad query returned 357 nodes, mostly noise,
  so files are still read for their content.

## 2.18.0 (2026-10-27)

Machine eyeball: an agent with a browser checks what it can, the owner still confirms every check.
The trial was pilot 2.11.0 checks #7-#18 on Devin SWE-2 (2026-10-26, a hand-written brief): 9 PASS,
2 PARTIAL, 1 NEEDS OWNER. It never passed what the owner then failed, and its one over-flag (#16) the owner
turned into a PASS. The report's shape worked, so the brief and the parser keep it.

- **`eyeball.py verify <repo> --release R [--url U] [<id>...]`** writes the brief from
  `references/eyeball-brief-template.md`: the open checks without a verdict, or the ids given (a
  fix round's re-check, with the owner's feedback quoted). Its Hard rules carry the trial's lessons:
  no data trawling (~600 list GETs for one DECLINED row drew 429s: answer NEEDS OWNER and name
  the fixture), clean up what it creates and list what it could not (a 53-event draft series was
  left in dev), temp passwords only for dev logins it creates, how something looks stays the owner's.
- **`eyeball.py checks import <repo> --release R <report>`** reads the report's `## #<id> PASS |
  FAIL | PARTIAL | NEEDS OWNER` headings into AGENT lines: states `agent-pass`, `agent-flag`,
  `needs-human`. **An agent verdict never closes a check**: only the owner's OK, and `checks ok
  --agent-pass` is their bulk confirm. `checks waiting` counts each state; the pane's 👁 list keeps
  agent-verdict checks (they still wait on the owner) and `status.py --json` gives each its `state`.
  On the pilot's real 2.11.0 report the parser reads 9 agent-pass, 2 agent-flag, 1 needs-human.
- **Routes `devin_eyeball`** (every posture, free) and **`sonnet_eyeball`** (SURPLUS only);
  `budget.py` prints an `eyeball` route list; a launch of task `eyeball-*` infers its route.
- **Adapter `eyeball_verify`**: `{url, accounts_file, rules}`. The accounts file is a pointer to a
  gitignored file: passwords never go in the adapter, which is committed.

## 2.17.1 (2026-10-27)

- `references/routing.md` still said the coordinator reruns every DB test (the "Never relaxed"
  list and the Devin SWE-2 row): both now name the stamp check (2.16.0). Found by graphify's
  first run on this repo. `graphify-out/` is gitignored.

## 2.17.0 (2026-10-27)

Auto mode: `/coordinate auto <R>`. The owner ran it by hand in pilot 2.11.0 (2026-10-26 00:38, asleep:
"pick your recommendation, record why and the alternatives, keep going; wait for me where undoing
it later costs too much"). The night took 6 decisions and held 4; the picks were sound, but the owner
could not find them in a 118 KB one-file ledger among their own decisions and hundreds of ROUTE
rows. This makes it a mode whose results are on top of the morning park.

- **`ledger.py auto <ledger> on|off`**: an `AUTO on` row plus the owner's decision row with the rule;
  `now.md` says "Auto mode is on" until it is turned off, so a resumed or woken session stays in it.
- **`decide --auto`** records a pick made without the owner with an id (A1, A2, ...); **`decide
  --waits --options --rec --hold <kind>`** records a choice held for them (W1, ...). The hold rule,
  from what that night held: `schema`, `deploy`, `security`, `product` (feature-sized), `prod`
  (reaches prod or real people), `cost` (too costly to undo).
- **`park` puts "Decided for you" and "Waiting for you" at the top of `now.md`** by itself,
  rebuilt from `decisions.md` at each park and each review, so the woken session's summary (its
  park, 2.15.1) opens with them. The holds are written as `Q:`/`Options:`/`Rec:` items, so
  `ledger.py questions` hands them to `AskUserQuestion` on the next resume.
- **`ledger.py review <ledger> A<n> ok | A<n> override ... | W<n> ...`**: an override or an
  answer becomes the owner's own decision row, and the line it replaces moves to `history.md`. A pick
  they have not reviewed stays in `decisions.md` after its task merges. `ledger.py decisions
  --auto --unreviewed` lists what is open; `status.py` prints an `AUTO MODE` line.
- Auto mode changes who decides, nothing else: budget gates, fit checks, the DB-question merge
  hold, reviews and eyeball checks are unchanged (SKILL.md §1 Auto mode). Release folders only
  (2.12.0 on): a one-file ledger refuses `--auto`.

## 2.16.0 (2026-10-26)

Pilot 2.11.0 lessons, approved by the owner ("go", 21:32).

- **The stamp check replaces the coordinator's rerun of new DB tests.** The owner's 2026-10-14 rule
  is met: over 2.11.0 the reruns never disagreed (DBRECHECK agree 18, stale 18, unrun 38,
  DISAGREE 0). `db.stamp_check` asks for a green `db.py` run at HEAD of every new DB test (the
  latest run decides; a coordinator's `--reviewed` run after the guard refused counts).
  `gates.py` prints `DB STAMP <test>: <why>` and goes RED (`db stamp`), and `merge.py` refuses
  the branch before committing anything. Strict on purpose: 38 unrun against 18 agree means the
  check only works if implementers stamp, so brief rule 3 now makes "commit, then `db.py` at
  that commit" the last step before the reply. RED-checks and the DB tests that import a changed
  file stay the coordinator's; `db.py --recheck` stays for spot checks, and one DISAGREE is a
  proposal to bring the rerun back. `unstamped()` is gone.
- **Park questions before the close-out brief** (SKILL.md §9 step 1): 2.11.0 asked one beside the
  dispatch, and the answer made the brief stale.
- **"Ships in R" claims are checked against the merges.** `closeout.py` lists every tracked doc
  line (outside `.coordinate/`) saying R ships something, beside the merged tasks; the close-out
  brief gets a Hard rule to check each against `git log`. 2.11.0's roadmap said "ships only the
  optional MFA" with no commit behind it.
- **A "Not doing" that cites a ruling names the question that ruling answered** (SKILL.md §5):
  both declines the 2.11.0 audit overturned (2 of 23) cited a real ruling for a neighbouring
  question.

## 2.15.1 (2026-10-26)

One path for the woken session's summary (the owner: "let's settle with one lest we trip"). 2.14.0
added `wake-summary.md` beside `now.md`; an earlier roadmap note had said the last park is the
summary. Settled on the park:

- **The woken session ends with a normal `ledger.py park`** whose first lines are "For you"
  (under 10: what waits on them, what merged, what still runs), sends `now.md` with SendUserFile,
  then a PushNotification. No `wake-summary.md`.
- A one-file ledger (2.11.0 and older) has no `now.md`: the prompt says to send the file given to
  `ledger.py park`. `wake.park_file()` picks between them.

## 2.15.0, coordinator-status 0.6.0 (2026-10-26)

The DB tier's run shows beside the test slots. In pilot 2.11.0's merges `db.py --wait` ran
`npm run test:db` with every core busy while the pane said all slots were free: `db.py` has its
own lock, not a `testlock` slot.

- **`db.py` writes a holder line** in `<log_dir>/db.lock` (`pid time db <tree> (N files)`), as a
  test slot does, and opens the lock with `a+`, not `w`, so a queued run no longer wipes the line
  of the run that holds it.
- **`status.py`** prints `db running|free[, N queued]` in its Slots line and `db held: ...`
  under it; `--json` has `db: {holder, waiting}` (null with no `db_test`). `testlock.held()` reads
  any lock file's holder.
- **The pane** draws `db running` (yellow) or `db free` after the test slots, the queue, and a
  `⧗ db <tree> · since HH:MM:SS` line while a run holds it.

## 2.14.0 (2026-10-26)

Trial fix 7: a woken session the owner can see. The `wake.py` session of 2026-10-26 ran 04:32-05:27
as `claude -p` and never showed in the Claude app on their phone.

- **`wake.py` starts a background session**, `claude --bg -n "wake <R>"`, not `claude -p`.
  With `remoteControlAtStartup` it connects to Remote Control, so it is listed in the app and its
  push reaches the phone (checked: a `--bg` test session showed on the owner's phone; a push from
  `-p` has no Remote Control to go through).
- **The woken session ends with `<release_dir>/<R>/wake-summary.md`** (under 20 lines: what
  merged, what waits on the owner, what still runs), sent with SendUserFile, then a PushNotification
  that leads with what waits on them.
- **`claude --bg` returns at once, so each try watches it** (`claude agents --json --all`, every
  30 s): busy after a minute, or a turn ended with no limit message, is awake; a limit message
  on an idle session is a refusal (`claude stop`, retry after `--retry-minutes`). The limit
  pattern is read only from an idle session's screen and drops "resets at" / "try again", which
  a working session can print.

## 2.13.0, coordinator-status 0.5.0 (2026-10-26)

Trial fix 5: who is spending the 5-hour window. The windows are the account's, so `usage.json`
says how full they are, not which session filled them.

- **The mod writes each session's cost** to `~/.claude/coordinate/sessions/<session id>.json`
  (`{session, cwd, samples: [[unix s, usd, 5h %]]}`, one sample per 2 min, the last hour plus a
  baseline). One file per session, so two sessions never overwrite each other; `usage.json`
  keeps its keys.
- **`budget.py` prints `this hour 5h +N%: ~M% by other sessions (<repo> $X), ~K% by this one`**
  when another session spent this hour. The climb runs from the lowest 5h reading this hour
  (since the window's reset) and is split by each session's dollars; this session is
  `CLAUDE_CODE_SESSION_ID`. `--json` has it under `spend`. Files idle a day are removed.
- The roadmap's other option, re-reading `budget.py` before each Claude launch with the 85% fit
  as headroom, already shipped in 2.10.0.

## 2.12.0 (2026-10-26)

Release folders: what a session reads apart from what is done (after ICM, arXiv 2603.16021;
the evaluation is in a private history note). Trial fixes 6 and 8. Pilot 2.11.0's ledger had reached
113 KB, and a resume read 6k tokens of Decisions + Parked, most of it 9 superseded parks.

- **One folder per release**, `.coordinate/releases/<R>/` (adapter `release_dir`): `now.md` (the
  current park), `decisions.md` (decisions in force), `eyeball.md` (open checks), `timeline.md`
  (the rows), `history.md` (what is done), `briefs/`. A resume reads `now.md` and `decisions.md`
  only. A release begun before keeps its one-file ledger, and every script still reads it.
- **`ledger.py park`** replaces `now.md` (a one-file ledger: its Parked section) and moves the old
  park to history, with the PARKED row.
- **`ledger.py decide`** writes a decision when it is taken, with the options it beat and its
  revert cost; one tagged `--task` moves to history when the task merges. The owner could not find
  2.11.0's overnight decisions: they were in review files and park notes.
- **A passed eyeball check leaves `eyeball.md`** for history; ids stay unique.
- **`OUTCOME` row after each MERGED** (`merge.py`): routes, rounds, review bugs, gate reds, wall
  time, 5h at the route and at the merge. `ledger.py outcomes <ledger>...` turns ledgers into one
  TSV row per merged task (on the first pilot's ledgers 2.8.0-2.11.0: 97 tasks), computing the row for
  ledgers written before OUTCOME existed. Tokens and ≈$ per agent are still only in the mod.
- **`status.py` prints `OVER CAP`** for a live file past adapter `live_caps` (now 60, decisions 60,
  eyeball 40, lessons 80 lines), including an old ledger's Parked section.
- **Close-out:** the report goes to `history.md`, a line to `releases/index.md`, the archive holds
  the whole folder in one file, and the wrap-up runs a lessons promotion pass: a lesson the skill
  now carries moves to `lessons-history.md` with its pointer.
- Logs stay in `log_dir` for every release: nothing reads them whole, and the DB stamps, the
  trusted snapshot and the test-slot locks there are shared across releases.

## 2.11.0 (2026-10-25)

Three fixes from pilot 2.11.0 wave 4.

- **`sonnet_review` route:** a narrow re-review of work Claude did not build, allowed in every
  posture but CRITICAL. The owner's "Mix" (Opus for the big review, Sonnet for the narrow re-review)
  had to be written as `sonnet_critique`. A `sonnet` launch on a review task now infers it.
- **Existing DB tests a branch can redden.** `gates.py` NOTEs the DB tests already on main that
  import a file the branch changed; brief rule 3 and SKILL.md §4 rerun them with `db.py`. Vault
  497 changed an upload path and a DB test went red unseen.
- **Finding ids of any shape.** `R2-1` rows were skipped (`dispose.py` filled 0, closeout counted
  none); now any id in the first column is a row, and a file with no findings row makes
  `dispose.py` WARN and exit 1.

## 2.10.0 (2026-10-25)

Trial fix 4 and the wave-4 TIGHT finding: Claude builds go by fit, not fixed gates.

- **The 5-hour gate is by fit.** A Claude build launches when the 5h window plus its estimate
  stays under 85% (adapter `budget.five_hour_fit_pct`; `build_cost_5h` Haiku 3, Sonnet 10,
  Opus 20), in any posture. The fixed 50% (`five_hour_build_pct`, removed) made a Sonnet build
  wait at 59%. `budget.py` prints `DOES NOT FIT` with the reason and the reset time.
- **TIGHT allows a Sonnet build the week can carry.** When what is left after it
  (`build_cost_7d` Sonnet 2) covers `tight_headroom` (0.75) of an on-pace share of the rest of the
  week. Pilot 2.11.0 at 7d 36% on 30.5% of the week refused one; it needed `--override`.
- **The wake arms with eyeball checks open** (the owner, 2026-10-24). Its prompt tells the woken
  session to leave what needs the owner in the report and work on the rest (SKILL.md §8).

## 2.9.0 (2026-10-25)

`wake.py` fixes from pilot 2.11.0 wave 4, before its first real wake test.

- **`--fresh` wakes at 0 context.** It starts a new `claude -p "resume coordinator on R"` that
  reads the Parked section, as a `/clear` resume does. Resuming with `-r` woke a coordinator
  parked at ~280k against its 340k TIGHT limit: one or two steps, then park again. SKILL.md §8
  arms with `--fresh`.
- **Arming refuses while this repo's Devin runs or `chain.py` are live** (exit 2, names each pid).
  They are children of the coordinator's shell, so the `/exit` the wake needs would kill them.
- **The armed wake detaches itself** into its own session (no `nohup ... &`), prints its pid and
  log, and so survives the `/exit`. `--foreground` runs the tries in place.

## 2.8.3, coordinator-status 0.4.0 (2026-10-25)

Trial fixes 1-3 from pilot 2.11.0 (ROADMAP "Next: fixes from the trial").

- **Cut rows open in the pane.** Eyeball checks, Devin's last line and quest log rows carry a `▸`:
  press it and the row wraps in full, `▾` cuts it again. The owner had moved the terminal to a 4K
  screen to read half a check. The open rows live in the `expanded` state key.
- **Party figures in one unit.** Rows read `ctx 91k (9%)`, live context; the total reads
  `1.9M processed`, every request's input summed (it read `1903k tokens` beside rows of 91k).
- **Figures before the step note.** `0/6 · ctx 91k (9%) · ≈$0.40 1:23 · Reading task 466…`: a
  long note now cuts only itself, not the cost and time.
- **The report pastes `checks waiting` as printed.** The line has named
  `.coordinate/eyeball/<R>.md` since 2.6.0; the coordinator paraphrased the path away (SKILL.md §6).

## 2.8.2 (2026-10-23)

- **Early-week pace no longer reads TIGHT.** `pace` divides by the week elapsed % floored at the
  new adapter key `budget.pace_floor_pct` (25). The mod trial on pilot 2.11.0 hit it: 7d 10% at 7%
  elapsed read pace 1.4, TIGHT, which refused `sonnet_implement`, forced reviews to Fusion and cut
  the session's hard limit to 400k. Now 0.40, SURPLUS; a real burst (30% on day one) still reads
  TIGHT. Past a quarter of the week nothing changes.
- `tests/test_budget.py`: the repo's first script test (`python3 -m unittest discover tests`).

## 2.8.1, coordinator-status 0.3.0 (2026-10-23)

Phase D, slice 2: Savvy Progress folded into the mod (code adapted, MIT, credited in the README).

- **Per-agent context, cost and time.** Each Claude row in PARTY adds a bar and `ctx N% · tokens
  ≈$cost m:ss`, from the subagent's own model requests (`turn.step`) and its last turn. The bar is
  the subagent's reported steps, or its context, dim, when it reports none. A `claude party:` line
  totals cost and tokens. Runs are tracked from `agent.spawn`, not polled from `$.agent.list()`.
- **`step` tool** (`mcp__coordinator-status__step`): a subagent reports its plan and each finished
  step. SKILL.md step 4 tells Claude implementers to use it when the mod is loaded.
- **A band above the prompt**: `● <release> ████░░ 5/12 merged · devin 2 · claude 1 · 👁 1`, with
  `▣ pane` (opens or closes the pane) and `✕` (hidden until the next `/coord-status`). It appears once status.py has resolved
  a release this session and refreshes after a main turn (at most once a minute) with the pane
  closed. A repo with no coordinate adapter is asked once a session.
- Not taken from Savvy Progress: its `progress` tool and planned-task rows (the ledger is the
  plan here), its tier costumes and desktop SVG drawings, and its language option.
- Uninstall Savvy Progress once this has run in a real session: both register a `step` tool.

## 2.8.0, coordinator-status 0.2.0 (2026-10-23)

Phase D, slice 1: the command-center mod's own rows (Savvy Progress and Filetree come later).

- **👁 eyeball checks in the pane.** A "WAITING ON YOU" block under the HP bars lists the open
  checks (`#id task server:port what`), and 👁 (👁2 for two) marks their task in the quest log and
  their worktree on the map, until the owner answers with `checks ok` or `checks feedback`.
- **Slots and the test-lock queue.** The party opens with `devin N/M free · tests N/M free · K
  queued`, and one line per held test slot (label, since when).
- **Devin rows show model and cost**: `swe-2 free`, `fusion-opus quota`, or `unpinned cost ?`.
- **The release follows the newest ledger** when `/coord-status` gets no release: the header shows
  the release status.py resolved instead of `?`.
- `status.py --json` adds `checks` (open only) and `test_waiting` (`testlock.py` runs queued for a
  slot); the text view's slots line adds the queue count.

## 2.7.0 (2026-10-23)

ROADMAP quick win 3.

- **`wake.py`: overnight auto-resume.** Sleeps past the 5-hour reset (`--after-reset`), then runs
  `claude -p -r <session> --permission-mode auto "resume coordinator on <release>"` from the repo,
  retrying every 15 minutes up to 8 times when the window still refuses. Skips while the session
  is open elsewhere (`--fork-session` resumes a copy). Log: `<log_dir>/wake-<release>.log`.
- SKILL.md §8: at 90% of the 5-hour window with no eyeball checks waiting, park and arm it.
- Tested against a fake `claude`; not yet against a real resume of a parked release.

## 2.6.0 (2026-10-23)

ROADMAP quick wins 1, 2 and 4.

- **The status mod is in this repo** as a second plugin, `coordinator-status`, installable from
  the same marketplace. Optional.

- **One list of eyeball checks.** `eyeball.py checks add|list|ok|feedback|waiting` keeps
  `.coordinate/eyeball/<release>.md`, append only: an ADD line per check (task, server:port, what
  to look at), open until an OK or FEEDBACK line. Every coordinator report ends with the
  `checks waiting` line instead of repeating the checks.
- **Portability sweep.** Knowledge that lived only in the pilot's memory is in
  `references/tooling-facts.md`: Devin billing, Devin following `AGENTS.md` over a brief, trusting
  its reasoning but not its gate reports, and the merge count that is not a limit. The first pilot-only
  `> OWNER:` marker is now the adapter key `owner_marker`; the brief template's TaskMaster wording
  names the adapter's `taskmaster` and says what to do without one.

## 2.5.0 (2026-10-23)

From the 2.10.0 spend analysis (the owner asked why the 5-hour window went faster than in 2.9.x):
2.10.0 spent 2.7× as much Claude per active hour, rightly for a week at 1%, but three Claude
builds were routed "SURPLUS" while the posture said TIGHT on a 72-75% window, which went to 99%
and stalled the coordinator that shares it. The owner's OK the same day.

- **`budget.py route` refuses a route the posture does not allow**, unless `--override
  "<reason>"`, which the ROUTE row records with `offposture=1`. A launch `ledger.py` routes after
  the fact is written with `offposture=1` and a warning. `devin_fusion` (paid Devin quota) is open
  in every posture.
- **Claude builds wait while the 5-hour window is hot.** At or past adapter
  `budget.five_hour_build_pct` (default 50), whatever the weekly posture, the build routes drop
  the Claude implementers and the note says when the window resets, so the slot goes to Devin or
  the Claude build waits for the reset. Reviews go on until TIGHT (70%).
- **The 5-hour reset time is read** from `usage.json` (`five_hour_resets_at`, now written by the
  coordinator-status mod in `company/coordinator/mod/`) and printed in the budget line; a window
  already past its reset reads as unknown, not as its last percentage.

## 2.4.0 (2026-10-23)

The owner's pick for the shared dev DB (option 1 of 4): tell a leak from a concurrent writer by
rerunning, not by reworking the leak check.

- **A DB change is confirmed before it is called a leak.** `db.py` reruns the tests once when
  the snapshot changed: changed again is a leak (exit 4); unchanged is CONCURRENT WRITER, and the
  result is the tests' own. Both 2.10.0 DISAGREEs were one implementer run during which the owner's
  dev UI wrote 20 audit rows (a login, a person delete). A real leak writes twice, as it already
  did under the coordinator's recheck; the confirmation runs only when something changed.
- **The recheck counts runs, not files.** DBRECHECK rows carry `run=<implementer stamp>` and
  `closeout.py` counts each run once: the coordinator rechecks file by file, so one 2-file run
  had counted as DISAGREE 2.

## 2.3.1 (2026-10-23)

The two review items the owner left to Claude's judgement (A7, A8), and a stale example.

- **A leak wins over a red test.** `db.py` exits 4 when the DB changed, even when a test also
  failed: exit 1 hid the leak behind "fix the test", and leaked rows stay after the fix.
- **The close-out budget covers the release.** `closeout.py` reports the posture each ROUTE row
  recorded (2.10.0: SURPLUS 31, TIGHT 14, ON PACE 2) above the close-out-time line, which in
  2.10.0 had been sampled after the weekly reset ("7d 0%").
- The first pilot's example adapter loses `path_prefix: /usr/bin`: `/usr/bin/node` was removed on
  2026-10-22, so it pointed at nothing.

## 2.3.0 (2026-10-23)

From the skill review of 2026-10-23 and the pilot 2.10.0 lessons, the owner's
OK the same day.

- **The DB recheck count was wrong.** `db.py --recheck` matched test files as literal strings:
  implementers pass basenames, the coordinator `src/tests/db/...`, so 7 matching runs read
  `unrun`. And `unrun` lumped in runs at an older commit. Now files match by basename, and a new
  class `stale` means the implementer ran the test only at an older commit. Recounted, 2.10.0 is
  agree 18, stale 10, DISAGREE 2, unrun 0, not agree 11, DISAGREE 2, unrun 18: implementers never
  skipped `db.py`.
- **`gates.py` refuses a moving tree.** It does not gate a worktree where a Devin build or fix round
  runs (GATES NOT RUN), and says GATES VOID instead of RED when HEAD, the uncommitted files or a
  merge in progress changed during the run (exit 3 for both; `merge.py` says MERGED TREE VOID).
  Two of 2.10.0's six gate reds were this. It also notes new DB tests with no implementer stamp
  at HEAD.
- **The snapshot script is trusted, then checked.** `db.py` keeps a copy of the adapter's
  `db_snapshot` script on first run and stops with the diff (exit 8) when it changes, until the
  coordinator reruns with `--trust-snapshot` (a 2.10.0 implementer edited `dbcheck.js` after it
  refused its run). `db.py --wait` queues behind a held lock instead of exit 6; briefs and
  `merge.py` use it.
- **Dispositions.** `findings.py` reads review tables for `closeout.py`, the new `dispose.py`
  (fills blank cells, warns on a "Not doing" that defers) and the new `audit.py` (writes the blind
  disposition audit's files and brief, `references/audit-brief-template.md`). `closeout.py` lists
  the dispositions still owed: blank cells (2.10.0's critiques left 21) and declines that defer.
  On 2.10.0 that flag catches 3 of the 4 declines the audit overturned, and none of the 9 it upheld.
- **Review files are where the close-out reads them.** The reviewer template named
  `<change_docs>/`, while practice and `closeout.py` use `<briefs_dir>/<release>/`.
  `repoint_docs.py --register` repoints the task register when the close-out moves them, and full
  paths before relative ones.
- `status.py` flags a Devin whose worktree was deleted under it. `worktree.py` runs setup only on
  a new worktree (`--setup` forces it): `eyeball.py` reran `npm ci` on every fix round.
  `merge.py` dedupes a bundle's branch, keys a merged-tree red by the bundle's ledger task (2.10.0
  counted two under `unrouted`), and finds the real worktree for the removal line.
- SKILL.md: a cross-cutting mechanism starts with a census of its layers and the shared rule;
  after the 3rd re-review with Bugs the coordinator offers the owner's hard stop; the disposition
  audit is a wrap-up step. Brief template: the "no reply, work left in the tree" variant; never
  edit outside the worktree.

## 2.2.1 (2026-10-22)

- **Review overrules per route.** `closeout.py` counts the findings the coordinator disposed
  "Not doing", per review route, into the report and the lessons file (the owner, 2026-10-22).

## 2.2.0 (2026-10-14)

- **DB recheck, counted.** `db.py` stamps every run on committed code (`db-stamps.jsonl`);
  `db.py --recheck` compares the coordinator's rerun with the implementer's stamp at the same
  commit and writes a DBRECHECK ledger row (`agree`, `DISAGREE`, `unrun`, `guard`, `dirty`).
  `closeout.py` puts the count in the report and in the lessons file with the owner's rule: a release
  with no DISAGREE → propose replacing the rerun with a stamp check.
- **Every launch is routed.** A LAUNCHED row for a task with no ROUTE row writes one, inferred
  from `who`; `chain.py` logs a review brief under its own id, not the build's; `budget.py route`
  refuses an unknown route name (2.9.0's `devin`, which the report counted apart from
  `devin_swe2`). Across 2.8.0–2.9.1, 14 launches and 10 review bugs had landed in "unrouted".
- **Merges install changed dependencies.** `merge.py` and `eyeball.py` run adapter
  `install_on_change` (default `npm install` where a `package-lock.json` changed) before gating:
  2.8.0's 403 gate went red on a package main never installed.

## 2.1.0 (2026-10-14)

From the pilot 2.9.1 + 2.9.2 run (its `.coordinate/lessons.md`); the three
amendments the owner approved on 2026-10-14.

- **`eyeball.py`: one server for an unmerged stack.** Previews the stack with `git merge-tree
  --write-tree` (a conflict outside `append_only` creates nothing, exit 2), then merges it into a
  throwaway `eyeball/<release>` worktree; rerunning merges a fix round's new commits. `merge.py`
  refuses an `eyeball/*` branch and prints the eyeball tree's removal lines after a merge.
- **Close-out brief variant:** `> OWNER:` lines are never deleted; an entry that leaves the live
  handoff takes them verbatim into the history file.
- **Push after the close-out merge** (SKILL.md §9.5 and a Red Flag): code, CHANGELOG and version
  deploy together.
- **§9 reordered: close-out, push, wrap-up.** The push report follows the close-out merge; the
  coordinator waits for the owner to say the release is live (fixing forward if not), then records it
  as live (runbook to history), appends lessons, saves, and prints the final report.
- Brief template hard rule 7 (pasted build tails with exit codes), committed 2026-10-13.

Then the lessons the owner picked from 2.8.0–2.9.2 on 2026-10-14:

- **Devin builds run on `swe-2-high` or `swe-2-medium`, always named.** `adapter.devin_model()`;
  `chain.py` refuses any other build model, `preflight.py` FAILs on one, and warns when Devin's
  config default (read from `agent.model`: the old check read a key that does not exist) is not
  one of them; `status.py` marks a running Devin without `--model` UNPINNED.
- **Implementers run their DB tests through `db.py`** (brief rule 3: exit 7 means fix the test,
  `--reviewed` stays the coordinator's); the coordinator still reruns every one. First real runs
  had failed 6 of 6.
- **Re-review a later round that adds product logic**, not only a round 1 with 3+ bugs (2.9.0
  att-server r3, 2.9.2 436 r4).
- **A DB test sets its own starting state** (brief template): eyeball rows broke two tests.
- **A merge that changes a gate** sends every open branch to merge main and rebuild (§6.6).

## 2.0.0 (2026-10-10)

From the pilot 2.7.0 run (`company/coordinator/run-2.7.0-skill-notes.md`) and
`company/coordinator/PLAN-skill-v2.md`, phases A, B2–B4, C and F.

- **Own repo, plugin marketplace layout.** Scripts are found from the skill's base directory, not
  `~/.claude/skills/coordinate`. Project state moves to `<repo>/.coordinate/` (gitignored);
  `init.py` drafts the adapter and asks six questions.
- **Budget-aware routing.** `budget.py`: pace from the Claude 7-day window against the week
  elapsed, postures SURPLUS / ON PACE / TIGHT / CRITICAL, routes per posture, the owner's vetoes in
  `budget.overrides`, once-a-week questions for missing signals, the Devin paid quota recorded
  by hand or from an out-of-quota log line, and machine-readable ROUTE ledger rows.
- **Parallel implementers.** `concurrency` caps (Devin 3, Sonnet 2, Opus review 1); `testlock.py`
  queues test runs on `test_slots`, and `gates.py` runs every gate through it; `chain.py` chains
  Devin rounds on whole-line `end <stem>` markers and waits for a free Devin slot (fixes the
  substring-marker bug).
- **Context policy.** Soft 450k (no new wave, exit 4), hard 650k (park, exit 3), 400k when TIGHT,
  park at once when CRITICAL; merges only warn; close-out in the same session when 60k fit.
- **`merge.py` writes the handoff entries**: the "merging" entry before, the "MERGED" entry with
  every gate's tail after, both committed; `--no-handoff` for close-out branches. It prints the
  merged worktree's removal command.
- **DB guard.** `db.py` refuses a new DB test that writes outside a transaction, opens one it never
  rolls back, deletes rows in afterAll/afterEach, or sets a `lock_timeout` with no longer test
  timeout (exit 7; `--reviewed` after reading each hit). It strips a leading `<db dir>/` from test
  paths. On the first pilot it catches both 2.7.0 incidents and refuses none of the 33 current DB tests.
- **Parked questions as data:** `Q:` / `Options:` / `Rec:` items; `ledger.py questions` returns
  them for `AskUserQuestion`.
- **`status.py`:** free slots, REMOVABLE worktrees with their removal command, worktrees whose
  folder is gone, the posture, `--release auto`.
- **`closeout.py`:** budget and per-route report into the ledger, the ledger archive copy,
  cleanup commands, the lessons step.
- Brief template: the Hard rules block that overrides the house rules, the test lock, the 60-line
  reply cap, and "a DB test commits nothing". Tooling facts: dcg variable expansion, heredocs
  with `${…}`, `git commit -F`, inotify limits.

## 1.0.0 (2026-10-03)

The skill as run for pilot 2.6.1–2.7.0 from `company/coordinator/skill/coordinate`.
