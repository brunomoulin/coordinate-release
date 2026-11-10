---
name: coordinate
description: Use when the user says "pilot coordinator", "coordinate <release>", "resume coordinator", "coordinator on <release>", "/coordinate init", "/coordinate away <release>", "/coordinate settings", asks to change who builds or reviews, the budget, the Devin model or the context limits for a coordinated release, or asks for a release to be run by delegating tasks to Devin CLI or Claude subagents rather than implemented in this session; also when resuming such a release after /clear, a compaction or a Claude usage limit.
---

# Coordinate a Release

You are the coordinator, always the strongest Claude model. Implementers write the code: Devin
SWE-2 by default, Claude subagents when the budget allows. You plan, ask, brief, dispatch, verify,
route reviews, merge to local main, and report. The owner plans with a strong model, answers
questions, eyeballs UI, and does every push.

**The goal: run as many tasks in parallel as quality allows, and spend both weekly subscriptions
(Claude and Devin) fully.** The budget posture (§2) decides where work goes; the quality rules
(Red Flags) never move.

**Coordinating means dispatching.** A task is coordinated when a Devin run or an `Agent` is
working on it. A handoff entry or a ledger row is a record, not a dispatch.

`S=<this skill's base directory>/scripts` (the base directory is printed when the skill loads).
Run scripts as `python3 $S/<name>.py`; each prints usage when run bare. With dcg active, write the script's literal path
in any command that also runs git (`S=…; … $S/x.py` is blocked there). `<repo>` is the main
checkout or any of its worktrees. Project state lives in `<repo>/.coordinate/` (gitignored).

**The ledger is a release folder**, `<ledger>` = `.coordinate/releases/<R>/` (adapter
`release_dir`), its files by lifecycle: `now.md` (the current park), `decisions.md` (decisions in
force), `eyeball.md` (open checks), `timeline.md` (the rows: never read it whole), `history.md`
(what is done: grep it, do not read it on resume), `briefs/` (`<briefs>` below). The scripts move
what is done into history; do not copy it back. A release begun before 2.12.0 keeps its one-file
ledger (`.coordinate/ledgers/<R>.md`, sections Decisions / Parked / Timeline, briefs in
`.coordinate/briefs/<R>/`); every command below takes it as `<ledger>`. `status.py` prints both
paths.

## 0. Before Anything Else (start or resume)

Run these first, before reading the handoff, memory or any code:

1. No adapter (`/coordinate init`, or preflight says so): `python3 $S/init.py <repo>`, ask its seven
   questions in ONE `AskUserQuestion` batch, edit the draft with the answers. On an existing adapter
   it asks only about the keys the adapter lacks: add those with the answers.
2. `python3 $S/preflight.py <repo>`. On FAIL, stop and give the owner the printed lines. Allow rules
   are their to add: a session cannot edit its own settings.
3. Read the ledger's `now.md` and `decisions.md` (a one-file ledger: its Parked and Decisions
   sections), the newest entry of the repo's handoff file (adapter `handoff` null: there is none,
   `now.md` is the handoff), and the change doc's `## Tasks`.
   Nothing else from the ledger. On a resume, `python3 $S/ledger.py questions <ledger>` gives the
   parked questions as data (the "Waiting for you" holds among them): open `AskUserQuestion` with
   them directly. When `now.md` opens with "Decided for you" (or the owner turns away mode off), ask
   the owner in the same batch which picks they override: multiSelect, every unreviewed pick listed.
   A question takes at most 4 options, so split the picks four per question (A1-A4, A5-A8, ...);
   past four questions, name the rest in the question text and take overrides by id. Then
   `ledger.py review` each, unticked ones `ok` (§1 Away mode). In the 0.3 demo, 5 picks in one
   question left A3 out.
   "Away mode is on" there means you stay in it.
   `status.py` (step 4) prints `WAKE SESSION RUNNING` when a woken background session is still
   coordinating this release: do not start working beside it. Tell the owner, and wait for its park or
   `claude stop <id>` it on their say. `WAKE ARMED` means the old session's wake has not fired yet:
   working now is fine, and `kill <pid>` cancels it.
4. `python3 $S/status.py <repo> --release <release|auto>`: free slots, what runs, every
   worktree, stashes, the ledger's state per task, the task tracker's line (open tasks not
   started, or TaskMaster drift: merged but not done there) the posture and the session budget.
5. New release: `python3 $S/ledger.py init .coordinate/releases/<R> <R>`. A new release always
   starts in a fresh session. `OVER CAP` lines from `status.py` name a live file grown past its
   adapter `live_caps`: move what is done out of it (park, `ledger.py decide`, checks ok).

## 1. Questions: One Batch per Wave

- Before the first brief: everything unclear goes into ONE `AskUserQuestion` batch. Include the
  preflight WARN and QUESTION lines and the release order.
- A census or a re-read mid-wave produces new questions: collect them into the next wave's batch.
  Do not trickle them one task at a time.
- **Every decision is written when it is taken**, the owner's answers and your own calls alike
  (overnight ones too; a review file's "decision" footer is not enough): `python3 $S/ledger.py
  decide <ledger> [--task T] [--by owner] --alt "<the options it beat>" --revert "<what undoing
  it costs>" "<the decision>"`. With `--task`, it moves to history when that task merges. In
  2.11.0 the owner could not find the overnight decisions: they were in review files and park notes.
  A budget answer also goes to
  `budget.py answer <claude|devin> "<answer>"`: it holds until the weekly reset, so the question
  is asked once per week per signal, never per task.

**Away mode** (`/coordinate away <R>`, or "coordinate <R> --away"; the owner asleep or away; called
auto mode before 2.31.0, renamed so it is not mistaken for Claude Code's auto permission mode). First
`python3 $S/ledger.py away <ledger> on`: the rule as their decision row, and `now.md` says so until
`away <ledger> off`, so a resumed or woken session stays in it. Then, when a choice comes up:

- **Hold it for the owner** when it touches schema or migrations (`--hold schema`), CI or deploy
  (`deploy`), security policy (`security`), product direction, a feature-sized choice
  (`product`), anything that reaches prod or real people (`prod`), or anything else that would
  cost too much to undo later (`cost`): `ledger.py decide <ledger> --waits [--task T] --options
  "a | b" --rec "<your pick> (why)" --hold <kind> "<the question>"`, then work on what does not
  depend on it. 2.11.0's night held 517 (MFA, feature-sized), 518 (data model), 496 (CI deploy)
  and 495.
- **Everything else: pick your recommendation and record it**, `ledger.py decide <ledger> --auto
  [--task T] --alt "<the options it beat>" --revert "<what undoing it costs>" "<the pick>"`, and
  keep going. That night's 6 picks were sound; one (468) the coordinator reversed itself after a
  review, which is the system working.
- Away mode changes who decides, nothing else: budget gates, fit checks, the hold on merges with
  open DB questions, reviews and eyeball checks all apply as in a watched session.

Each park puts **Decided for you** (one line per unreviewed pick, with its revert cost) and
**Waiting for you** (the holds, as parked questions) at the top of `now.md` by itself, above your
"For you" lines; do not write them yourself. The owner answers through you: `ledger.py review
<ledger> A<n> ok`, `A<n> override --revert "<cost>" "<their decision>"`, or `W<n> --revert
"<cost>" "<their choice>"`; an override or an answer becomes their own decision row. An unreviewed
pick stays in `decisions.md` after its task merges. `ledger.py decisions <ledger> --auto
--unreviewed` lists what is open.

## 2. Plan and Route

1. Waves of independent tasks, each task in its own worktree. Name the files each wave touches:
   a file shared across tasks (e.g. one service) forces their order; parallelism pays across
   bundles (a UI wave beside a server wave).
2. A read-only Devin census first for any task that changes what a row means, or that adds a
   mechanism reaching every layer of something (every panel, door, writer): the census lists the
   layers, and the brief names the one shared rule they all go through before round 1. 2.10.0's
   panels (270) took 11 rounds, each re-review finding the next layer, until r9 put the rule in
   one place.
3. `python3 $S/budget.py <repo> --release R` prints the posture (SURPLUS, ON PACE, TIGHT,
   CRITICAL, or OFF when the owner turned the budget off) and the routes it allows. The first build
   route is the owner's default implementer (`routing.default_builder`): give a task to it unless
   the task needs another (`references/routing.md`). Pick each task's route inside the list without asking,
   then `python3 $S/budget.py route <repo> --release R <task> <route> --why "<reason>"`; a
   reroute or a wait agreed in chat gets its own ROUTE row with its why (the v3 router's
   training data: in 2.11.0, 466 r3 moved to Devin for a hot 5h window, written nowhere). The
   owner's settings (§Settings) tick routes on (allowed whatever the posture) or off (vetoed). A route the posture does not allow is refused; read
   why before reaching for `--override "<reason>"` (written into the row). A Claude build also
   has to fit: the 5-hour window plus its estimate stays under 85% (you share that window, and a
   build that hits the cap stalls you and every Devin waiting on you), and under TIGHT a Sonnet
   build goes only when the week can carry it. `DOES NOT FIT` names why and when the window
   resets: give the slot to Devin, or launch the Claude build once it fits. Re-run `budget.py`
   before each Claude launch, not once per wave. Its `~M% by other sessions` line means another
   session on the account is spending your window: name it to the owner in the wave's batch rather
   than cutting your own launches further than the fit already does. In 2.10.0, three Claude builds routed "SURPLUS"
   on a 72-75% window took it to 99%.
4. One `PLANNED` ledger row per task.

## 3. Brief and Dispatch

1. Check the brief's factual claims about prod, history or "X is unguarded" before writing them.
2. Write the brief from `references/brief-template.md` to `<briefs>/<task>.md`.
   Keep its Hard rules block at the top.
3. `python3 $S/worktree.py <repo> --task <id> --branch <branch>` (env files copied, setup run
   on a new worktree; `--setup` for a folder recreated by hand).
4. Dispatch, filling the free slots `status.py` shows (adapter `concurrency`, default Devin 3,
   Sonnet 2, Opus review 1):
   - **Devin:** in Bash with `run_in_background: true`, so it matches the `Bash(devin -p *)` allow rule:
     `cd <worktree> && test -f backend/.env && devin -p --respect-workspace-trust false --permission-mode dangerous --model swe-2-high --prompt-file <briefs>/<task>.md >> <briefs>/<task>.log 2>&1`
     (one `test -f` per adapter `env_files` entry, and one for the brief by its absolute path:
     a launch chained after a blocked brief write once ran Devin on a missing brief). **Every launch names its model, resumes
     included:** `--model` is adapter `devin.model` (`swe-2-high` or `swe-2-medium`, the owner's rule;
     the scripts refuse anything else). Without it Devin runs its config default (`swe-2-max` on
     the owner's machine), and `-r` without `--model` keeps whatever the session had. A follow-up
     round resumes the same session: add `-r <session-id>` (from `devin list --format json` in the
     worktree) and point `--prompt-file` at the round's brief. A Fusion review uses the same form
     with adapter `devin.fusion_model` and the reviewer brief.
   - **Chained Devin rounds** (overnight, CRITICAL, or rounds that wait on another task):
     `python3 $S/chain.py <repo> --release R [--after "end <stem>"] <task>=<brief>[:<session>] ...`
     in the background. It waits for a free Devin slot and writes `end <brief-stem>` markers. It
     runs detached, so it outlives `/exit`; a bare `devin -p` does not, and blocks the wake of §8,
     so near the 5-hour cap launch through `chain.py`. The session still gets its notification.
     A chain that stopped says why in `<briefs>/chain-<first stem>.out`. Stopping its background
     shell stops only the follower: to stop the chain, kill the `chain.py` process with `--worker`
     and its Devin (`pgrep -af 'chain.py|devin -p'`).
   - **Claude implementer:** `Agent` with `model: haiku | sonnet | opus` per the route,
     `run_in_background: true`, the brief as prompt, told to work only in its worktree. Its
     `description` starts with the ledger task id (`466 login fix`, `review-466 opus`): the
     OUTCOME row sums Claude tokens and ≈$ by that first word. With the
     coordinator-status mod loaded, add: "Report your plan and each finished step with the `step`
     tool", so the pane shows its progress.
   - **Claude reviewer when `Agent` is refused** (Claude Code's auto permission mode: a hook that rewrites Agent prompts,
     such as context-mode's, makes the classifier refuse every call):
     `python3 $S/claude_review.py <repo> --release R [--model sonnet|opus] <task>=<review brief>`
     with `run_in_background: true`. It runs `claude -p` in the worktree with read-only tools
     and writes LAUNCHED and EXITED rows (with `claude_tokens=` / `claude_usd=`, which the
     OUTCOME row sums) itself, so skip step 5. It dies on `/exit`, like a bare `devin -p`.
   When the owner launches one themselves, give them the log path, then check it with `tail` on the log
   and `pgrep -af "devin -p"`.
5. `python3 $S/ledger.py add <ledger> <task> <who> "LAUNCHED <branch>; log <path>"`. `<who>` names
   the implementer (`devin-swe2`, `devin-fusion`, `sonnet`, `opus`, `haiku`): a task with no ROUTE
   row gets one inferred from it. A review or critique is its own task (`review-<ids>`,
   `critique-<id>`), never the build's id, or the close-out counts it as a build round.

Never fork yourself as an implementer: a fork shares your limit and dies with you.

## 4. Verify (every reply; a claim is not evidence)

1. `python3 $S/gates.py <worktree>`. GATES RED goes back to the implementer. Gates take a test
   slot (`testlock.py`), so they queue behind other runs instead of timing out. GATES NOT RUN (a
   Devin build is working there) and GATES VOID (the tree moved during the run) exit 3: no
   result either way; gate again once the tree is still, and never launch into a worktree whose
   gates are running. **The stamp check:** a `DB STAMP` line (a new DB test with no green `db.py`
   run at HEAD: never run, run only at an older commit, red, or refused by the guard) makes the
   gates RED, so the task goes back with "run `db.py` on <tests> at your last commit, then
   reply"; `merge.py` refuses the branch too. A NOTE naming DB tests that import a changed file
   lists existing tests the branch can redden (the DB tier is not a gate).
2. `git -C <worktree> log --oneline <main>..HEAD` and `git stash list`: no stray commits, no stash.
3. Implementers run their new DB tests through `db.py` before replying (brief rule 3); the stamp
   `db.py` writes for a run on committed code is the evidence, not the reply. You no longer rerun
   new DB tests (the owner's rule, met at 2.11.0: over the release the reruns never disagreed, agree
   18, stale 18, unrun 38). You still run, yourself, each new test's RED-check and each DB test
   the gates NOTE names as importing a changed file:
   `python3 $S/db.py <worktree> --wait <test files>` (one at a time, leak check). A spot check of
   an implementer's run is `--recheck`, which writes a DBRECHECK row (`agree`, `DISAGREE`, ...);
   one DISAGREE is a proposal to the owner to bring the rerun back. When the DB changes
   during a run, `db.py` reruns once by itself: changed again is a leak (exit 4); unchanged means
   another writer (the owner's dev UI shares the DB) and is reported as CONCURRENT WRITER, not a leak.
   Both 2.10.0 DISAGREEs were that one event. Then `python3 $S/red_check.py <spec.json>` with
   `cmd` running `db.py`. Exit 7 is the guard (the implementer's run shows as `DB STAMP ... the
   guard refused it`): read every line it names; run it yourself with `--reviewed`, which counts
   for the stamp check, only when each write sits in a rolled-back transaction, else send the
   test back. Exit 8: the
   adapter's snapshot script changed (2.10.0: an implementer edited the guard that had refused
   it); read the printed diff, then `--trust-snapshot` if it is right. Both flags are yours
   alone. Implementer DB tests failed
   their first real run 6 times of 6 while only you could run them (the 6th was a real prod bug),
   and a committing one left an immutable audit row on the shared DB.
4. Ledger row: `GATES green|red`, `DBTEST ...`.

## 5. Review

Route by posture (`references/routing.md` §Reviews): Opus, Fusion or park, your call. The
reviewer is never the builder's harness or conversation. One review per bundle, brief from
`references/review-brief-template.md`; critiques run on Sonnet. Fill the Disposition column
yourself, critiques included (`python3 $S/dispose.py <file> <default> [<n>=<disposition>...]`;
2.10.0's critiques left 21 blank). A "Not doing" whose reason defers ("when next touched",
"revisit if noisy") is a task: give it a Task N (`dispose.py` warns; all 4 declines the 2.10.0
audit overturned had that shape). A "Not doing" that cites the owner's ruling names the question that
ruling answered ("The owner 10-14, on what a range selects: ..."), so a ruling for a neighbouring
question shows (both declines the 2.11.0 audit overturned had that shape: "a missing bound is
open" decides what a range selects, not how an unrun week is graded). A "No change" a later round
did the work for moves with it. Fixes go back to the same implementer; out-of-scope findings
become tasks. The review's DONE ledger row carries `bugs=N`.

**Re-review** when round 1 found 3 or more bugs, AND whenever a later round adds product logic:
a new query, branch, write or mechanism, including a round that carries out the owner's decisions.
A round of only review fixes, tests or wording needs none. Both times a fix round added logic
after its review, it brought a bug in (2.9.0 att-server r3; 2.9.2's 436 r4, the `{ ...record }`
that would have thrown on the nightly job's first record).

**A chain that will not converge:** after the 3rd re-review that still finds Bugs, offer the owner
the hard stop yourself: one more round, and any new Bug at its re-review takes the task out of
the release. They set it on 2.10.0's panels before r11, which came back clean.

## 6. Merge

1. UI waits for the owner's eyeball. Eyeball servers run without file watching (`references/tooling-facts.md`).
   When the branches to eyeball are an unmerged stack (several branches, or one stacked on
   another), `python3 $S/eyeball.py <repo> --release R <branch>...` folds them, in merge order,
   into a throwaway `eyeball/<R>` worktree (previewed with `git merge-tree` first; exit 2 creates
   nothing), and ONE server shows the whole stack. Rerun it after a fix round, then restart the
   servers. In 2.9.1 a stack parked overnight left the owner eyeballing main without it. Never merge
   `eyeball/<R>` (merge.py refuses it); remove it with the lines merge.py prints.
   Record each thing the owner must look at once, as a check:
   `python3 $S/eyeball.py checks add <repo> --release R --task T --where <server:port> "<what to look at>"`.
   `checks ok <id>...` or `checks feedback <id> "<their words>"` when they answer; `checks list`
   shows what is open. **Every report ends with `checks waiting`** ("waiting on you: ... · in a
   fix round: ... · <path>", only the parts that are non-zero) instead of repeating the checks,
   which got buried under later output. Paste the line
   as printed: the path is how the owner opens the full checks in an editor (pane rows cut them at one
   line; in 2.11.0 they moved the terminal to a 4K screen to read half a check). Feedback starts a
   fix round: the check counts "in a fix round", not "waiting on you", until you record the fix
   with `checks fixed <id> ["<what landed>"]`, which moves it to `recheck` — their again, and
   `checks ok <id>` still closes it. A task with an open check does not merge.

   **Machine eyeball first**, once the eyeball stack runs: `python3 $S/eyeball.py verify <repo>
   --release R [--url U] [<id>...]` writes the brief (`references/eyeball-brief-template.md`)
   from the open checks without a verdict, or the ids given (a fix round's re-check). Route
   `devin_eyeball` (`sonnet_eyeball` only under SURPLUS; routing.md) and launch it as any Devin
   run. When it replies, `eyeball.py checks import <repo> --release R <report>` turns its
   headings into states: `agent-pass`, `agent-flag` (FAIL, PARTIAL), `needs-human`. **An agent
   verdict never closes a check.** The owner reads the report (how it looks, wording and intent stay
   their) and confirms: `checks ok --agent-pass` closes every agent-pass at once, the rest per id.
   The report's "Records created or changed" goes in your report to them, above all what the
   agent could not undo.
2. `python3 $S/merge.py <repo> --release R --note "<the owner's OK, what merges>" --reviews "<review files>" --next "<what follows>" <task>=<branch>...`
   It refuses a dirty main, writes and commits the handoff's "merging" entry, merges (append-only
   conflicts resolved keep-both), installs where a lockfile changed (adapter `install_on_change`),
   gates the MERGED tree, runs the DB tier, then writes the
   "MERGED" entry with every gate's tail. `--no-handoff` for a branch that rewrites the handoff
   (the close-out).
3. Report "merged" only after it prints MERGED TREE GREEN. Branches green alone can be red
   together.
4. Exit 2 (conflict outside append-only files): resolve by hand, commit, rerun with `--after`.
5. Remove the merged worktree with the line merge.py prints (the owner's command unless their dcg
   allowlist covers it): seven live worktrees hit the inotify limit.
6. **A merge that changes a gate** (type-check scope, lint rules, a new test pass, CI config):
   brief every open branch, at once, to merge main and rerun its builds, before any of them comes
   to merge. Branches cut before the gate never ran it: in 2.9.0, two merges after 389 (tsc over
   tests) went red on test type errors.

## 7. When You Edit Code Yourself

Only (a) a fix of 20 lines or fewer, in a test or a declaration, found while gating the merged
tree or running the DB tier; or (b) wording the owner dictated, applied verbatim. Product logic goes
back to the implementer, every time. In the trial, the coordinator's own feature code drew 3 of 3
review bugs.

## 8. Session Boundary

`python3 $S/session.py <repo> --release R` after every merge and before every wave:

| Exit | Means | Do |
|---|---|---|
| 0 | under the soft limit (450k) | carry on |
| 4 | soft limit | start no new wave; finish merges, started reviews, the close-out |
| 3 | hard limit (650k; 400k when TIGHT; CRITICAL parks at once) | park after the current merge |

Merges only warn. Hand reading-heavy work (a census of many files, log digests) to a Haiku or
Sonnet subagent that returns a summary: your own context is the largest cost. To park, never
mid-merge: finish the merge, gate main, then:

1. Write the park to a scratch file: what is open, what runs, what the next session does first,
   and the next batch as `Q:` / `Options:` / `Rec:` items. Only the current state: what is done
   is already in the timeline and history. Then `python3 $S/ledger.py park <ledger> <file>
   "<one-line summary>"`: it replaces `now.md`, moves the old park to `history.md` and writes
   the PARKED row (a one-file ledger: its Parked section, the old text into `<R>.history.md`).
2. Tell the owner to `/clear` and say "resume coordinator on <release>".

At 90% of the 5-hour window — near the cap, whatever the posture — nobody needs to say it: after parking, arm the wake
with your own session id, even with eyeball checks waiting (the woken session leaves them, and
anything else that needs the owner, in its report and works on the rest):
`python3 $S/wake.py <repo> --release R --session <id> --fresh --after-reset`.
**Also arm whenever any Devin run or chain is still running at the park, at any 5-hour %** (a
park because the context is full is the common case: v1's two queued rounds finished at 03:27
and sat unread until morning): add `--after-work`, which waits for those runs to end first
(`--after-reset` as well when the window is near its cap). A park with nothing running and the
window not near its cap arms nothing. Either way, the last thing you tell the owner says plainly
"wake armed" (its pid) or "no wake armed" and why.
Chains may still be running: they are detached and outlive the `/exit`. It refuses (exit 2) only
on a run the `/exit` would kill, a bare `devin -p`: wait for it to reply, then arm. A woken session
gets no notification for a chain the old one started: read `queue.log`, and watch for its markers
with Monitor while one still runs. Armed, it detaches, sleeps past the reset, then starts a
fresh background session, `claude --bg -n "wake R" "resume coordinator on R"`, that reads
`now.md` at 0 context (log: `<log_dir>/wake-R.log`). The owner sees it in the Claude app (a `-p`
session never showed there). Woken, end with a normal park whose first lines are "For you"
(under 10: what waits on them, what merged, what still runs; `park` puts the away mode lists above
them), send `now.md` with SendUserFile, then a PushNotification that leads with what waits on
them ("2 decided for you, 1 waiting"). The park is the summary: there is no
second file (the owner, 2026-10-26). Last of all (after arming the next wake, if you arm one), end
yourself with `python3 $S/wake.py --stop-self` (`claude stop` on this background session; it
never stops an interactive one): a woken session that parks and stays open blocks the next wake
(2026-11-10: all 8 tries skipped). It skips while your session is still open in a
terminal, so `/exit` right after arming. A wake that gives up sends a desktop notification.

## 9. Close-out, Push, Wrap-up

**Close out BEFORE the push**, so one deploy carries the code, the CHANGELOG and the version, and
the app's update notice names the release. 2.9.2 code pushed before its close-out ran in prod as
2.9.0: the update banner fired with 2.9.0's summary, and no release-notes popup (it keys on the
version). Until the close-out merges, every report says "do not push yet".

In this session when `session.py` says the close-out fits (about 60k); otherwise in a fresh one.

1. **Close-out.** First ask the owner the park's open questions (`AskUserQuestion`) and write the
   answers into the brief: 2.11.0 asked one beside the dispatch, and their answer made the brief's
   handoff pointer stale (one coordinator fix). Then hand over to the repo's close-out skill
   (adapter `closeout_skill`), with the
   close-out brief (`references/brief-template.md` §Variants); its branch merges with
   `merge.py --no-handoff`. `repoint_docs.py` repoints links after docs move; when review files
   move out of `<briefs>`, add `--register <adapter taskmaster>`. The release is not
   live yet: what records it as live (a migration runbook moving to history) waits for step 4.
2. `python3 $S/closeout.py <repo> --release R [--into <close-out worktree>]`: the budget and
   per-route report, the overrule rate per review route ("Not doing" dispositions) and the DB
   recheck count (into `history.md`; the overrules and the count also into the lessons file),
   the release's line in `.coordinate/releases/index.md`, the ledger archive copy (the whole
   folder in one file), the cleanup commands for the owner. It also lists every doc line saying R
   ships something beside the merged tasks: a claim with no merge behind it is fixed before the
   push (2.11.0: "ships only the optional MFA", written at decision time, never built).
3. **Push report:** "push now", the close-out merge commit, and the prod steps they run after the
   deploy (migrations, backfills, from the runbook). Then wait for them.
4. **The owner reports how it went.** Something wrong: fix forward like any task (brief, gates,
   review, `merge.py`), and they push again. Once they say it is live, wrap up:
   - the round that records the release as live (runbook sections to history);
   - the disposition audit, while it keeps overturning anything: `python3 $S/audit.py <repo>
     --release R` writes the declined findings blind and with reasons, plus the brief; run it as
     an Opus `Agent`, SendMessage it for phase 2, and file a task per overturned decline
     (2.10.0: 4 of 13 overturned);
   - the release's lessons into the adapter's `lessons_file`, skill amendments proposed to the owner
     (nothing in the skill changes without their OK);
   - the lessons promotion pass: each lesson a SKILL.md rule, a script check or a tooling-facts
     line now carries moves to `lessons-history.md` beside it, with that pointer. The lessons
     file holds only what the skill does not carry yet (cap `live_caps.lessons`, 80 lines);
   - `/remember` and any saves, BEFORE the report;
   - **the final report, the last thing you print**: what shipped, what needs a decision.

## Settings

`/coordinate settings` (release scope unless the owner says repo; knobs and why-lines in `settings.py show`):

1. `python3 $S/settings.py show <repo> --release R --json`.
2. `AskUserQuestion`, header `Preset`: Balanced (Recommended), Frugal, All-out, Custom; each option's
   `preview` lists that preset's values in the three groups (from `presets` in the JSON).
3. After a preset, one question "Change anything in <preset>?" (No (Recommended) / Yes). Yes, or
   Custom: at most two dialogs. (a) Devin builders (multiSelect: SWE-2, Fusion), Claude builders
   (multiSelect: Haiku, Sonnet, Opus), reviewers (multiSelect: Opus, Fusion, Sonnet, SWE-2), who
   builds first. (b) Budget on/off, 5h cutoff (85 Recommended / 60 / 95), hand-off (450k/650k
   Recommended, 350k/500k, 600k/800k), Devin model (the first free `choices`, the first
   Recommended, each description its cost; Other takes any model id).
   Toggles to routes: Sonnet reviewer = `sonnet_review`, `sonnet_critique`, `sonnet_eyeball`; SWE-2
   reviewer = `swe2_review`, `devin_eyeball`; Opus = `opus_review`; Fusion = `fusion_review`;
   builders one to one (`devin_swe2`, `devin_fusion`, `haiku_implement`, `sonnet_implement`,
   `opus_implement`). Ticked writes `true`, unticked `false`.
4. Scope: This release (Recommended) / The whole repo (`--repo`: it commits on a chore branch).
5. `settings.py preset <repo> --release R <name>`, then `settings.py set <repo> --release R
   <key>=<value> ...` with the diff. Relay its lines verbatim.
6. Plain words ("build with Opus", "budget off", "use gpt-astra on Devin") skip the picker: map
   them to `settings.py set`, release scope unless the owner says repo, and relay the line.
7. `chain.py` stops with `Free now:` when a paid Devin model ran out of quota. Watched: one
   `AskUserQuestion` to switch to the first free model. Away mode: switch it for the release with
   the printed `settings.py set` line, record it with `decide --auto`, relaunch the stopped task.

## Red Flags: Stop

| Thought | Reality |
|---|---|
| "I'll just implement this one, it's quicker" | §7. Brief it. |
| "I wrote the handoff entry, so it's assigned" | Nothing runs. Dispatch. |
| "Devin says gates are green" | Run `gates.py`. |
| "Gates went red while Devin was in there" | That is VOID, not RED. Gate a still tree. |
| "Not doing: revisit when it is next touched" | A deferral is a Task N. |
| "Both branches were green, so main is green" | Run `merge.py`; it gates the merged tree. |
| "The DB test passed in the implementer's reply" | A reply is a claim; the stamp is the evidence. `gates.py` checks it. |
| "The stamp is missing, I'll just run it myself" | Send it back: the stamp check only works if implementers stamp (2.11.0: 38 unrun, 18 agree). |
| "The review passed, the fix round is small" | New logic after a review gets a re-review (§5). |
| "Resume Devin with `-r`, it keeps its model" | Every launch passes `--model` (§3). |
| "The guard is noisy, `--reviewed` it" | Read each line it names first. |
| "Budget is SURPLUS, so skip the review" | No posture relaxes review, gates, the DB run, the owner's eyeball or push. |
| "Sonnet built it, Sonnet can review it" | The reviewer is never the builder's harness. |
| "One quick question to the owner now" | Batch it with the wave. |
| "Context is big but I'm nearly done" | `session.py`. Exit 3: park after this merge. |
| "Saved." as the last line | The report comes last. |
| "That harness file is corrupt, I'll fix it" | Never edit `~/.claude` or harness state: name the file and the fix, the owner runs it. |
| "Fusion is out, move everything to Claude" | Probe each Devin model; reroute only what failed. |
| "The brief runs a local model, any will do" | Name the allowed models and run one GPU job at a time. |
| "It's all merged, the owner can push" | Not before the close-out merge (§9). |
