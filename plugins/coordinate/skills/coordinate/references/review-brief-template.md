# Reviewer Brief Template

One independent review per bundle (tasks that touch the same area, or are small, share one).
The reviewer has a fresh context and never sees the implementer's conversation.

Opus code review: `Agent` with `model: opus`, `run_in_background: true`, this text as the prompt.
Fusion review (TIGHT or CRITICAL posture): the same text as a Devin brief, run with
`devin.fusion_model`. Sonnet UI critique: `model: sonnet`, and `/critique` in place of
`/code-review`. The reviewer is never the builder's harness. Reviews at once: adapter
`concurrency.opus_review` (default 1).

```markdown
You are an independent reviewer for <repo>, release <release>. Read-only: do not edit code,
commit, merge, or run the DB-test tier.

## What to review

- <task id>: branch `<branch>` in worktree `<path>`, diff against `<main>`: `git -C <path> diff <main>...HEAD`
- The briefs the implementers worked from: <brief paths>. **Check each brief's factual premises
  against the code and history.** A brief can be wrong; say so when it is.
- House rules: `<repo_rules>`.

## How

Run `/code-review` on the diff at high effort. Then read the surrounding code the diff relies on.

## Write

`<briefs>/<release>-<ids>-code-review.md` (a re-review:
`<release>-<ids>-rN-rereview.md`; a critique: `<release>-<ids>-critique.md`), with:
1. A findings table: `| # | Severity | File:line | Finding | Fix | Disposition |`. Severity is one of
   `Bug` (wrong behaviour), `Risk` (may break under conditions you name), `Improvement`,
   `Suggestion`, `Nit` (wording, style). Leave Disposition empty: the coordinator fills it.
2. **Out of scope:** anything you noticed outside the diff (security exposures, siblings with the
   same defect, dead code). This section has found HIGH issues before. Keep it.
3. A verdict: merge as is / merge after fixes / do not merge.

Reply with the file path, the counts by severity, and the verdict.
```

## After the review

The review file stays where the brief put it: `closeout.py` and `audit.py` read every
`<briefs>/*-{code-review,rereview,critique}.md`, and a review written anywhere
else is never counted. The close-out moves them into the repo's docs (`repoint_docs.py
--register`).

The coordinator fills the Disposition column (To fix in round N / Not doing, why / Task <id>),
critiques included, with `dispose.py`; a "Not doing" that defers gets a Task N instead. It
files new tasks for out-of-scope findings and sends the fixes back to the same implementer.
The review's DONE ledger row carries `bugs=N` (the Bug-severity count) for the close-out report.
Re-review when round 1 found 3 or more bugs, and after any later round that adds product logic
(SKILL.md §5). A re-review gets the same brief, scoped to the commits since the last review.
