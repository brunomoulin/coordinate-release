# <Short title — what changes, not what's broken>

**Found:** <date> — <how this surfaced: a session, a report, a code review>
**Status:** investigating | ready for tasks | in progress | blocked
**Related:** <links to other docs, tasks, or PRs>

---

## Problem

What is wrong or missing, in plain terms. Written by the owner first; the agent may sharpen it but must
not replace their framing.

## Investigation

Filled in by the agent. Evidence, not assertion:

- Code traces with real references — `backend/src/services/event/eventService.ts:492-790`
- What was verified by running it vs. what was inferred from reading it. Say which. A code-trace
  finding that has not been reproduced is labelled **suspected**, not **confirmed**.
- What was ruled out, and why — this is what stops the next session re-deriving it.

## Delta

State the change against **current** behaviour, not against an ideal. Naming what is modified or
removed is what stops requirements being invented that were never there.

- **ADDED:** <behaviour that does not exist today>
- **MODIFIED:** <existing behaviour> — was X, now Y
- **REMOVED:** <behaviour> — and what replaces it

## Acceptance Criteria

- [ ] <observable, checkable statement — "a child occurrence shows the parent's frequency", not "recurrence works">
- [ ] <one per criterion; these are what the owner ticks to know it's done>

## Tasks

- [ ] T1 — <title> — ref: — depends: none — priority: high
- [ ] T2 — <title> — ref: — depends: T1 — priority: medium

`ref:` points at this task's entry in whatever tracker **this repo declares in its `AGENTS.md`**:

- **TaskMaster repos** — leave it empty while drafting; fill in `tm:master#168` as soon as
  `add_task` returns. Never hand-edit `tasks.json` to create the task.
- **`documentation/TASKS.md` repos** — use the anchor or bullet text it lives under, or leave it
  empty if the task exists only here.

Tick `- [x]` in the same action as marking the task done in the tracker — never one without the
other. On disagreement the tracker wins; fix this doc, don't reopen the task.

---

<!--
Conventions for this file:

  > OWNER: lines are the owner's inline review annotations. They are AUTHORITATIVE and override the
  surrounding analysis, including analysis the agent wrote. Never delete, reword, summarise, or
  tidy one up — add below it. An unanswered "> OWNER:" question blocks this doc from moving to
  documentation/completed/.

  Every task created from this doc must link back to this file path, so the investigation above
  travels with the task instead of being retyped into it.
-->
