# Routing: Who Does What

Costs measured on pilot 2.6.0–2.7.0 (cached tokens read: what a session's every turn re-reads).

| Who | Use for | Cost | Notes |
|---|---|---|---|
| **Devin SWE-2 High or Medium** | Default implementer (unless `routing.default_builder` names a Claude model): backend, security fixes, migrations, censuses, review-fix rounds, overnight chains | free while the Devin catalog lists it Free; bounded by `concurrency.devin` slots | Always launched with `--model` (adapter `devin.model`, or a release's `/coordinate settings`; never Devin's own default). Runs its DB tests through `db.py` only; the stamp check (a green run at HEAD) is the evidence. Weak git hygiene: check `git stash list` and the branch history after each run. Resume fails while Devin Desktop holds the session |
| **Haiku** (`Agent`, `model: haiku`) | Mechanical work: doc repoints, renames, census reads, log digests for the coordinator | cheapest Claude | SURPLUS only for implementation; digests any time |
| **Sonnet** (`Agent`, `model: sonnet`) | UI tasks, medium tasks; `/critique` | 1.3–2.3M per critique | Resumable with SendMessage in the same coordinator session |
| **Opus** (`Agent`, `model: opus`) | Code and security review; hard or security implementation in SURPLUS | 2–9M per review | 12 of 12 reviews changed code or filed a task |
| **Devin Fusion** (Opus High + SWE-2) | Reviews when Claude is TIGHT or CRITICAL (open in every posture, e.g. a review trial); a task too hard for SWE-2 | paid Devin quota | A log line saying the quota ran out marks it exhausted (`budget.py`) |
| **Fork of the coordinator** | Never | 4.8M lost in the trial | Shares the coordinator's limit and dies with it |
| **The coordinator** | Plan, brief, dispatch, verify, dispositions, merge, report | the largest cost (181M in one session) | Hands reading-heavy work to Haiku/Sonnet; context limits in SKILL.md §8 |

## Posture (`budget.py` prints it)

`pace = Claude 7-day % used / % of the week elapsed`; 1.0 spends exactly 100% by the reset. The
elapsed % is floored at adapter `budget.pace_floor_pct` (25): in a week's first quarter, pace is
7d % / 25, so 10% used on day one reads 0.4 (SURPLUS), not 1.4 (TIGHT); 30% reads 1.2 (TIGHT).

| Posture | When | Builds | Reviews | Coordinator context |
|---|---|---|---|---|
| **SURPLUS** | pace < 0.7, or reset < 24 h with 7d < 70% | Devin slots full, then Claude by task: Haiku (mechanical), Sonnet (UI, medium), Opus (hard, security) | Opus on every bundle; re-reviews per SKILL.md §5; Sonnet critiques | hard 650k |
| **ON PACE** | 0.7–1.1 | Devin (all slots); Sonnet for UI | Opus | hard 650k |
| **TIGHT** | pace > 1.1 | Devin; Sonnet only when it fits the week (below) | Fusion | park at 400k |
| **CRITICAL** | 7d ≥ 90% | Devin only, chained with `chain.py` so they run without Claude turns | Fusion, else park the review | park after the current merge |
| **OFF** | the owner set `budget.mode` off (`/coordinate settings`) | every route (SURPLUS's), no fit check | every route | hard limit as set, never parks for the budget |

**The owner's settings move routes.** A route ticked in `/coordinate settings`
(`budget.overrides.<route>: true`) is allowed whatever the posture; a Claude build still has to
fit (below) unless the budget is off. Unticked (`false`) is never allowed. `routing.default_builder`
leads the build list: give it the task unless the task needs another. A paid `devin.model` (not
Free in the Devin catalog) leaves the list once the Devin quota is exhausted, as Fusion does.

**A Claude build has to fit, in any posture.** The 5-hour window plus the build's estimate
(`build_cost_5h`: Haiku 3, Sonnet 10, Opus 20) stays under `five_hour_fit_pct` (85%), or the
build waits (`budget.py` prints `DOES NOT FIT` and the reset time). The week is the budget, the
5-hour window is the rate: burning it fast costs nothing by
itself — the 5h window never sets the posture — but the coordinator shares it, and when it runs out the coordinator stops, a cut-off agent
loses its work, and finished Devins sit idle. Near its cap it drives the park-and-wake of SKILL.md
§8. The 85% leaves room for other sessions on the
account, which spend the same window. Each session with the coordinator-status mod writes its
cost to `~/.claude/coordinate/sessions/<id>.json`, and when another session spent this hour
`budget.py` prints `this hour 5h +N%: ~M% by other sessions (<repo> $X), ~K% by this one`: the
split is by dollars, so read it as a share, not a measurement. Each closed subagent row goes to
`~/.claude/coordinate/agents/<id>.json`, which the OUTCOME row sums per task (SKILL.md §3). Under TIGHT, a Sonnet build also has to fit the week: after
it (`build_cost_7d`: Haiku 0.5, Sonnet 2, Opus 5), what is left covers `tight_headroom` (0.75) of
an on-pace share of the rest of the week, `(100 − 7d − cost) / (100 − week %) ≥ 0.75`. At 7d 45%
on 33.5% of the week, a Sonnet build leaves 0.80: it goes; at 70% on 40%, 0.47: it waits. `budget.py route` refuses a route outside the posture unless
`--override "<reason>"`; a launch routed by `ledger.py` is written with `offposture=1`.

Turned around: Claude nearly spent while Devin used only SWE-2 → TIGHT → reviews move to Fusion.
Devin slots full and Claude healthy → SURPLUS → Haiku/Sonnet/Opus take the next tasks.

**Unknown signals.** 7-day window unknown (no fresh `usage.json`): treat as ON PACE and ask once
this week. Devin paid quota unknown: ask once this week whether Fusion may take reviews and hard
tasks, or have the owner run `budget.py devin <pct>` after a glance at the dashboard.

**Your agency.** Pick the route inside the posture without asking, and write it:
`budget.py route <repo> --release R <task> <route> --why "<reason>"`. `devin_fusion` (a build too
hard for SWE-2) spends the paid Devin quota and is open in every posture. Route names: `devin_swe2`,
`devin_fusion`, `haiku_implement`, `sonnet_implement`, `opus_implement`, `opus_review`,
`fusion_review`, `sonnet_review`, `swe2_review`, `sonnet_critique`, `park_review`, `devin_eyeball`,
`sonnet_eyeball`. `sonnet_review` is a narrow
re-review (a few files a round-1 fix touched) of work Claude did not build, in any posture but
CRITICAL: the big review stays Opus or Fusion. `swe2_review` is SWE-2 critiquing or re-reviewing
Claude-built work, free and open in every posture (pilot 2.11.0: it found 466's one real UI defect
and a data leak); like `sonnet_review`, never the review before merge. The owner vetoes with adapter
`budget.overrides` (e.g. `{"opus_implement": false}`).

## Never relaxed by any posture

- An independent review before merge. **The reviewer is never the builder's harness or
  conversation**: a Devin build gets a Claude (or Fusion) review; a Sonnet build gets Opus or
  Fusion, never Sonnet.
- `gates.py` on the branch and `merge.py` on the merged tree.
- The stamp check: every new DB test green through `db.py` at the branch head, or the task goes
  back (`gates.py`, `merge.py`), whatever the implementer's reply says. The coordinator runs
  the RED-checks and the existing DB tests a branch can redden.
- The owner eyeballs UI and does every push.
- Questions in one batch per wave.

## Reviews

1. Posture SURPLUS or ON PACE → **Opus** review.
2. TIGHT or CRITICAL → **Fusion** review: same reviewer brief, read-only, writing the same
   review file. A Claude limit mid-review loses the whole review (5.4M lost once).
3. Fusion refused or out of quota (the log says so in the first minutes): probe `swe-2-high` and
   the Fusion model separately and reroute only what is out (tooling-facts). No review route
   left → **park the review**:
   ledger row `PARKED review <ids>: no Claude window, no Devin quota`. A SWE-2 pre-review
   (`swe2_review`) may run
   meanwhile, but never replaces the Opus/Fusion review before merge.

## Machine eyeball

`eyeball.py verify` writes the brief; it runs on **Devin SWE-2** (`devin_eyeball`, free, any
posture). **Sonnet** (`sonnet_eyeball`) only under SURPLUS. Its verdicts never close a check:
The owner confirms each (SKILL.md §6). The 2.11.0 trial on SWE-2 never passed what the owner then failed.

## Other rules

- A task that changes what a row MEANS gets a read-only Devin census first, then the design.
- Critiques run on Sonnet. Opus is for code and security review.
- Re-review when round 1 found 3 or more bugs, and after any later round that adds product logic
  (SKILL.md §5). Any posture: a TIGHT re-review goes to Fusion.
- Concurrency (adapter `concurrency`): Devin 3, Sonnet 2, Opus review 1. Test runs queue on
  `test_slots` (`testlock.py`), so implementers code in parallel.
