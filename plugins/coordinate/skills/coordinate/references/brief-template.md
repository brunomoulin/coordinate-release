# Implementer Brief Template

One file per task at `<briefs>/<task>.md`. The implementer's log goes next to it
(`<task>.log`). Brief in, log out: both are kept as training data. Follow-up rounds get their own
file: `<task>-r2.md`, `<task>-r3.md` (`chain.py` writes `end <task>-r2` when a round exits).

Before writing: every factual claim the brief makes about prod, history or "X is unguarded" is
checked against the code or data first. Three of 14 trial briefs carried a false premise, and
reviews caught all three at Opus prices.

The Hard rules block goes FIRST. The repo's house rules (`AGENTS.md`) are loaded into the
implementer's context and are written for an agent working alone; without this block Devin
followed AGENTS.md over the brief (it set a task in-progress from its worktree). Name each
house-rule section it overrides.

```markdown
# <id>: <title> (<task register> <tag>#<id>, <priority>)

**Worktree:** `<absolute worktree path>`
**Branch:** `<branch>` (already checked out; setup done)

## Hard rules — these OVERRIDE `<repo_rules>` for this run

`<repo_rules>` is loaded into your context and is written for an agent that works alone. Here a
coordinator owns the register, the handoff, the merge and the final DB run. Where they disagree, this
block wins:

1. **No task-register edits.** Never edit or stage `<taskmaster file>` (adapter `taskmaster`), and
   call no task-status tool. (Drop this rule if the repo has no register.) (Overrides <repo_rules> "<section names>".)
2. **Never edit `<handoff file>`.** (Overrides <repo_rules> "<section name>".)
3. **No merge, no push, no dev server, no migrations on the dev DB.** DB tests run only through
   `python3 <S>/db.py <worktree> --wait <test files>`, never `<db_test cmd>` directly; run each
   new DB test that way, and its RED-check, and every DB test file that imports a file you
   changed, before replying. **The last step before you reply: commit, then run every new DB
   test through `db.py` at that commit.** `db.py` records only a run with nothing uncommitted,
   and a new DB test with no green record at your last commit sends the task back unreviewed
   (the gates go red on it). Exit 7 (the guard refused): fix the test; never pass `--reviewed`. Exit 5 (pending
   migration), 4 (the DB changed) or 8 (the snapshot script changed): stop and say so in the
   reply; never clean up rows. Never edit anything outside your worktree, the coordinator's
   guards above all (the adapter, its snapshot script, `<S>`), and never pass
   `--trust-snapshot`.
4. **Never `git stash`, `git checkout --`, `git restore`, `git reset`, `git clean`.** Commit, or
   copy to a scratch file. Stashes are shared by every worktree; never pop one.
5. **Run tests through the test lock:** `python3 <S>/testlock.py -- npm test` (other runs queue;
   two at once time out the timing tests).
6. **Reply under 60 lines.** A longer reply was once lost to the output limit.
7. **Gate evidence, not a claim.** Before replying, run each build (<the adapter's build gates,
   by directory>) and paste its last 3 lines with the exit code. A reply that says "build
   passes" without the pasted tail is not accepted.

## What is wanted

Read task <id> in `<taskmaster file>` (details and testStrategy) first. It is the complete spec.
(No register: put the spec here instead.)
<Change doc section link, if any.>

<What is wrong or wanted, in the owner's decided terms. Name the files likely involved and the
existing pattern to copy ("fix it the way task 257 did in personService.ts, search 'task 257'").>

**Find the code through the graph first:** `graphify query "<question>" --graph
<main checkout>/graphify-out/graph.json` (also `path "A" "B"` and `explain "X"`, same `--graph`)
answers what references, calls or breaks with a file, in fewer tokens than grep. Read the
files it names for their content. (Drop this paragraph if the repo has no
`graphify-out/graph.json`; it is gitignored, so the worktree has none of its own.)

**Read each <file/writer/route> before changing it.** The list came from <source>. If one already
does this, or the change would alter a different behaviour, leave it and say so in your reply.

**Sibling sweep:** look for the same defect in <siblings: other doors, writers, routes>. Report
each one you find in your reply. Do not fix them.

## Done means

- Tests: <what to add>. Each seen to FAIL with the fix removed, then restored; say so per test in
  the commit body.
- If an existing test's fake hides the change, fix the FAKE, not the assertion.
- **A DB test commits nothing:** every write inside one transaction that is rolled back. A
  concurrency test proves the lock order by blocking, not by committing. It sets an explicit
  timeout longer than every `lock_timeout` it sets. (`db.py` refuses a new DB test that breaks
  this.)
- **A DB test sets its own starting state** inside that transaction, and never assumes what the
  shared DB holds: the owner's eyeball writes real rows there. Two tests that counted a table-wide
  state broke after one eyeball session.
- Gates (<path prefix if any>): <the adapter's gates, by name and directory>.
- Commit early and often: one commit per <unit>, staged by file name. Uncommitted work is lost if
  you are cut off.

## Out of scope / ownership

- <What not to touch, and which other agent owns which shared file right now.>

## Reply (under 60 lines)

Your commit hashes, the gate tails with exit codes, the RED-check result per test, the sibling
sweep findings, and anything you skipped or were unsure of.
```

`<S>` is the skill's scripts folder, written out as an absolute path.

Why rule 7: in 2.9.0, a reply said "backend build green" while `tsc` was red on a test file (vitest
never type-checks); 2.8.0's audit found a red build pushed under three "tsc clean" reports. Every
brief that demanded the pasted tail got a true answer. It does not replace `gates.py`: the
coordinator still runs the gates; the rule makes the implementer run the build before it stops.

## Variants

- **Census (read-only, before a design):** "Do not change code. Classify every <reader/writer/
  reference> of <X> by kind, with file:line. List the design forks you see." Commit the census as
  one Markdown file. It takes 7 to 15 minutes on SWE-2.
- **Review fixes:** the review file's path, the finding numbers to fix with their dispositions,
  the same Hard rules/Done/Reply sections. Same implementer, same branch: resume the session
  (Devin) or SendMessage (Claude, same coordinator session). A fix that adds a mechanism (a new
  reader, query or endpoint) names the visibility and permission rule it obeys: task 466 r2 added
  a reader that skipped document visibility.
- **Reply only:** when a Devin reply was lost, resume with `-r <id>` and a brief that asks only
  for the reply.
- **No reply, work left in the tree** (`<task>-rNb.md`): a Devin exited with no reply and
  uncommitted files. A fresh session, same Hard rules, told: "First commit what is in the tree as
  it is (WIP commit, staged by file name). Then run the gates, finish round N from `<round N
  brief>`, and reply." 2.10.0 panels r6 (25 files uncommitted, 4 tests red) recovered in one
  round this way.
- **Close-out:** names the repo's close-out skill and the release, carries the owner's answers to the
  park's open questions (asked before this brief, §9), and adds two Hard rules. "**Every 'R ships
  X' line is checked against the merges.** A roadmap or doc sentence saying the release ships
  something needs a commit in `git log <previous tag>..HEAD`; one with none is corrected, and the
  reply lists both kinds." (2.11.0: "ships only the optional MFA" had no commit; this cross-check
  caught it.) And "**The owner's review lines are never deleted.** Lines starting `<owner_marker>` (adapter
  `owner_marker`, e.g. `> JD:`; no rule if unset) stay verbatim. An entry may leave the live
  handoff or a doc, even when the owner's own note says 'remove this entry': its marked lines go word for word into the history
  file the entry moves to." At the 2.9.2 close-out the implementer deleted two of them on exactly
  that instruction.
