# Disposition Audit Brief

Once per release, in the wrap-up (SKILL.md §9), while it keeps overturning anything. `audit.py`
writes the findings files and fills this brief into `<briefs>/audit/audit-brief.md`;
the placeholders in braces are its. Run it as `Agent` with `model: opus`, `run_in_background:
true`. The auditor never sees the coordinator's conversation.

Why: a long-running coordinator that wrote the briefs may defend its own designs. In 2.10.0 a
fresh Opus upheld 9 of 13 declines and overturned 4, all one shape: a deferral written as a
decline ("when next touched", "revisit if noisy"). No sign of defending its own designs.

```markdown
# Disposition audit: {n} review findings the coordinator declined ({release})

You are an independent auditor. Read-only: edit no file in the repo, run no git command that
writes, touch no database. The one file you write is your verdict file (below).

**Repo:** `{repo}` (local main; every {release} branch is merged into it, so a review's
`file:line` may have drifted a few lines).

**Why this exists.** In {release}, code reviewers filed findings; the release coordinator (a
long-running session that wrote the briefs) declined {n} of them as "Not doing". The question is
whether the coordinator was right, or whether a long context that wrote the designs made it
defend them.

## Phase 1 (now): judge blind

1. Read `{dir}/audit-blind.md`: the findings, the coordinator's reasons removed. **Do not open
   the review files the findings name, the ledgers, or `audit-reasons.md`**: they hold the
   coordinator's reasons, and seeing them first defeats the audit.
2. Read `{rules}`: the house rules a disposition may cite.
3. For each finding, read the code it points at and decide: **SHOULD FIX** (now), **FILE** (a task
   for later), or **DECLINE** (no action is right). One or two sentences of evidence each:
   file:line you read, what is true there.
4. Write `{dir}/audit-verdicts.md` with a `## Phase 1` table: `| A# | verdict | evidence |`. Then
   STOP and reply only "phase 1 written". The coordinator's reasons follow in a message.

## Phase 2 (after the follow-up)

Read `{dir}/audit-reasons.md`. For each finding, add a `## Phase 2` row: `| A# | reason holds?
(yes / no / partly) | did the reason change your verdict, and why |`. Mark which reasons rely on
context the reviewer did not have (an owner's ruling, a brief's hard rule, an earlier decision)
and whether that context is real (check it in the house rules, the code, or git log). Then a
5-line summary: how many declines you would overturn, and any pattern.

Reply under 30 lines.
```
