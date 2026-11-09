# `/coordinate settings`: presets and plain-language settings

Design, 2026-11-09 (the owner and Claude). Status: shipped in 2.33.0.

## Why

The coordinator's governance already has knobs: who builds and reviews (`budget.overrides`), the
Devin models (`devin.model`, `devin.fusion_model`), the budget posture thresholds (`budget.*`) and
the context hand-off limits (`session_limits.*`). They live in `.claude/coordinate.json`. `init.py`
asks seven questions once, and after that the only way to change a knob is to edit the JSON by
hand. The owner's setup works well. Public users, though, will want to say things like "build with
Opus", "screw the budget, burn Devin on GPT Astra" or "let the session run longer", and to try
settings out on one release without committing the repo to them.

It also gives the README a third GIF: the settings picker.

## Goals

1. **`/coordinate settings` opens a picker** that runs on Claude Code's own `AskUserQuestion`
   (arrows to move, space to toggle). No mod is needed.
   - Screen 1: a preset. **Balanced (Recommended)** is today's defaults. The others are **Frugal**,
     **All-out** and **Custom**. Each preset's preview pane lists its values in the three groups below.
   - After a preset: one follow-up, "Change anything in <preset>?" (the owner's demo pick was
     Balanced minus Opus builds, so "a preset minus one thing" is expected to be common). Yes → the
     Custom screens, starting from that preset's values.
   - Custom: at most two dialogs of at most 4 questions each, covering every knob in the groups below.
   - Last screen: **This release (Recommended)** or **The whole repo**.
   - Then a one-line confirmation per changed knob: `builds: Opus off (release ux-improvements)`.
2. **Plain language works too.** Mid-release, "build with Opus on this release" or "turn the budget
   off" makes the coordinator run the same update (no picker) and confirm in one line. Release
   scope unless the person says repo.
3. **Release scope by default, repo scope on request** (the owner: "current release > repo optional").
4. **Every knob explains itself.** `settings.py show` prints each knob with its value, where the
   value comes from (release / repo / default), and one line of why the default is what it is
   (for example the context limits: turns cost more as context grows, a resume costs ~100k and
   10 minutes, and the hard limit leaves room to park before auto-compact).

## The three groups and their knobs

The knobs, grouped as the picker and `show` present them:

- **Who does the work**
  - builders allowed: Devin SWE-2, Devin Fusion, Claude Haiku, Sonnet, Opus (multi-select).
    Stored as `budget.overrides` `{<route>: false}` for the ones switched off.
  - reviewers allowed: Opus, Fusion, Sonnet (re-reviews), SWE-2 critiques (multi-select).
    Also `budget.overrides`.
  - Devin build model: `devin.model`. The picker offers `swe-2-high` (Recommended), `swe-2-medium`
    and "other", which takes free text (e.g. a GPT Astra model id).
- **How hard to spend**
  - budget: `on` (posture from the 7-day pace, today) or `off`. New key `budget.mode`:
    `"auto" | "off"`.
  - Claude build cutoff on the 5-hour window: `budget.five_hour_fit_pct` (85 today).
- **When to hand off**
  - soft / hard context limits: `session_limits.soft_tokens` / `hard_tokens` as one choice:
    450k / 650k (Recommended), 350k / 500k, 600k / 800k.

The rest of `budget.*` (pace thresholds, build costs, critical %) stays in the JSON and the
references: tuning knobs, not choices a user makes at the start of a release.

**Ticked means allowed, whatever the posture.** Today `budget.overrides` can only veto (`false`),
and ON PACE has no `opus_implement` at all, so "build with Opus" would do nothing. A tick writes
`overrides: {<route>: true}`, which `allowed()` and `route_row()` both treat as "in the route list
whatever the posture". An untick writes `false` (vetoed). With no entry, the posture decides, as
today. A ticked Claude build still has to pass the 5-hour fit check (`misfit`), so it can't stall the
coordinator, who shares the window. Only `budget.mode: off` skips that check. (Claude's call: the owner
asked for "build with Opus" to work; the fit check stays because it guards the coordinator itself.)

**Route coverage.** The "Claude Sonnet" reviewer toggle covers `sonnet_review`,
`sonnet_critique` and `sonnet_eyeball`. "SWE-2 critiques" covers `swe2_review` and
`devin_eyeball`. The picker's builder list has 5 entries, so it is split over two questions
(Devin / Claude). Frugal unticks every Claude route; its review before merge is Fusion.

**Release over repo, per route.** A release `SET` on overrides writes one route
(`budget.overrides.opus_implement=true`), merged over the repo's map. A release can turn a route
the repo vetoed back on, and the confirmation line names it: "Opus builds on for this release
(the repo has them off)".

## Default implementer (the owner, 2026-11-09)

The user picks who builds first: **Devin** (Recommended when `devin` is installed), **Claude
Sonnet**, **Claude Haiku** or **Claude Opus**. Today the route lists start with `devin_swe2`, and a
user without a Devin subscription has no free builder at all. New key
`routing.default_builder: "devin" | "sonnet" | "haiku" | "opus"`. It is the coordinator's first
choice for a task whenever the posture and the overrides allow it; the posture's list follows as
the fallback. `init.py` proposes `devin` only when the `devin` binary is found, and `sonnet`
otherwise. The picker shows it first in "Who does the work".

## Devin pricing is data, not a constant (the owner, 2026-11-09)

SWE-2 is free only with a Devin subscription, and only until 2026-12-01 (Devin Desktop); Cognition
keeps changing that. Promotional models come and go (now: Gemini 4 Argon, at some promo price).
When SWE models weren't free, they were still much cheaper than the rest, about Sonnet level and
now and then Opus level, never above. So `budget.py`'s "SWE-2 is free in every posture" turns into
a live lookup.

**Revised 2026-11-09 after running `devin models`:** `devin models list --format json` returns,
per model the account can use, `model_uid`, `cost_tier` (`Free` / `Low cost` / `Med cost` /
`High cost`) and `cost_summary` ($ per 1M input / cached / output). It does not return the quota
left, promo end dates or a promo flag (Gemini 4 Argon reads `High cost`, $2 / $10). So:

- **Free is read live, not kept by hand.** `adapter.devin_catalog()` runs that command (cached for
  the session in `~/.claude/coordinate/devin-models.json`, refreshed at preflight). A model is free
  when its `cost_tier` is `Free`. Anything else, or a model the catalog doesn't list, spends the
  Devin quota. There are no `until` dates: the day SWE-2 stops being free, the catalog says so.
  Without `devin` installed, or when the command fails, the last cached catalog is used, and with
  no cache SWE-2 high/medium count as free (today's assumption).
- **Run with the choice until it fails, then suggest a free one (the owner's flow).** A paid model runs
  until Devin says the quota ran out. `chain.py` and `scan_devin_log` already match that log line
  (`DEVIN_OUT`), mark the quota `exhausted` and stop the queue. New: on that event the coordinator
  refreshes the catalog and offers the free models in it: "Devin quota ran out on gpt-6-astra-high.
  Free now: swe-2-high, swe-2-flash-high. Switch this release to swe-2-high?" In away mode it switches
  to the first free model of the same family preference (`swe-2-high`, then any `Free`), records the
  pick with `decide --auto`, and relaunches the failed task.
- **Prices inform the picker.** The "Devin model" question lists the free models first (Recommended),
  then a few paid ones with their `cost_summary`, so the owner judges promos themselves.
- `promo`, `cheap` and `paid` collapse into one rule: not free means it spends the Devin quota
  (removed when the quota is `exhausted`, as Fusion is today).

## Presets

Defined once, in `adapter.py` beside `DEFAULTS`, as partial overlays over the defaults:

- **Balanced**: no overlay; today's defaults.
- **Frugal** (Claude's call, open to tuning): builders Devin SWE-2 only; reviewers Fusion and
  SWE-2; `five_hour_fit_pct` 60; limits 350k / 500k.
- **All-out** (Claude's call): every builder and reviewer on; `budget.mode` off; limits 600k / 800k.

Applying a preset writes the knobs where it differs from the current effective value, so a
release's ledger shows exactly what changed.

## Where settings live

- **Release scope:** rows in the release ledger, `SET <key>=<json value>` (author `owner`), the same
  pattern as `AWAY on|off`. For a given key the latest row wins, and `SET <key>=default` removes the release
  value. The ledger keeps the trail of what changed and when. No new file.
- **Repo scope:** the file `adapter_path()` resolves to (`.claude/coordinate.json`, else
  `~/.config/coordinate/<repo>.json`), written by `settings.py` (the edited keys only; the rest
  is left as it was). The committed `.claude/coordinate.json` can't sit dirty on main:
  `merge.py` refuses a dirty main. So `settings.py` commits it the way the repo's rules want, on a
  `chore/settings-<date>` branch merged into main with `--no-ff`, and prints the push for the
  owner (pushes stay theirs). (Claude's call.)
- **Precedence:** release `SET` rows over the repo adapter over `DEFAULTS`.
  `adapter.load(path, release=None)` applies the release rows when given a release, so
  `budget.py`, `session.py`, `chain.py`, `status.py` and the rest read one answer. Scripts that
  take `--release` pass it on.

## Budget off

`budget.mode: "off"` means: posture reads `OFF`, routes are SURPLUS's (everything allowed by the
overrides), `misfit` (the 5h / 7d fit checks) is skipped, and `session.py` stops lowering the hard
limit for TIGHT or parking for CRITICAL. The picker and the plain-language path both say what that
gives up in one line: "the coordinator may use up your 5-hour and 7-day windows".
ROUTE rows still carry the tokens and cost, so spend stays visible.

## Devin models

`DEVIN_BUILD_MODELS` (the owner's 2026-10-14 rule: SWE-2 medium or high) becomes the recommended
list, not a hard refusal: another model id is accepted, with a one-line note that it may spend the
paid Devin quota. `devin.model` stays named on every launch's command line. The "other" free text
covers `devin.fusion_model` too.

The model's cost comes from the live Devin catalog (below): a model that isn't `Free` there is paid, and then the
posture and the Fusion-exhausted removal apply to `devin_swe2` as they do to Fusion.

**Away mode** (the owner chose A, then widened it at the final review, 2026-11-09): the
`autoMode.environment` line `init.py` prints authorizes `--model <any model devin models list
shows for this account>` instead of naming SWE-2, so a release's model switch and the quota-out
fallback run unattended. `preflight.py` spots the old line text and says to re-paste it once.

## Interface

- `scripts/settings.py`:
  - `show [<repo>] [--release R] [--json]`: the knobs, values, sources and why-lines (the
    `--json` form feeds the picker's previews).
  - `set [<repo>] [--release R | --repo] <key>=<value> ...`: validates and writes. An unknown key or
    bad value exits non-zero with the valid list. A release scope with no release folder is refused.
  - `preset [<repo>] [--release R | --repo] <balanced|frugal|all-out>`: writes the diff.
- `SKILL.md`: a short "Settings" section. `/coordinate settings` runs the picker flow above, and
  plain-language requests map to `settings.py set`. Trigger phrases are added to the description.
- `references/adapter.md`: `budget.mode`, and the release-scope rows.
- Status pane / `status.py --json`: no change required. (Builder's choice: a `settings` badge
  when the release has SET rows.)

## Non-goals

- A mod-drawn settings pane. The picker runs on `AskUserQuestion`, so it works without the mod.
- Exposing every `budget.*` tuning number in the picker.
- More choices than the ones listed: added when users ask (the owner: "if we ever get feedback on more
  choices, we think about it").
- Changing the default limits. Whether 450k / 650k should move is a separate question, answered
  from the ledger's cost-per-merge data, not here.

## Anti-goals

- Two places that say what a preset is (one source of truth: `adapter.py`).
- A setting that silently does nothing: every knob listed is read by a script, with a test.
- Turning the budget off without the person being told what it stops protecting.

## Left to the builder

The exact wording of the why-lines and of the previews, how `settings.py` edits the JSON
(preserve key order and indentation), test layout (`tests/`, unittest), and whether `show`
output groups by section headers or a table.
