# `/coordinate settings` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Presets, a picker and plain-language edits for the coordinator's governance knobs, scoped to the release by default, plus a default implementer and Devin cost read live from `devin models`.

**Architecture:** `adapter.load(path, release=None)` layers release `SET` ledger rows over the repo adapter over `DEFAULTS`, so every script reads one answer. `budget.py` learns `budget.mode: off`, ticked routes (`overrides: true`), `routing.default_builder` and Devin cost from the live `devin models` catalog. A new `settings.py` shows, validates and writes knobs (ledger rows or the adapter file). SKILL.md drives the `AskUserQuestion` picker from `settings.py show --json`.

**Tech Stack:** Python 3.10+ standard library only; unittest (`python3 -m unittest discover tests`).

**Spec:** `documentation/active/coordinate-settings.md` (approved 2026-11-09). Read it first.

Scripts dir below: `S = plugins/coordinate/skills/coordinate/scripts`.

## Global Constraints

- Never commit to `main`: work in `../coordinate-settings` on `feature/coordinate-settings`, merge `--no-ff`.
- Standard library only; no new dependencies.
- One source of truth: presets live only in `adapter.py`; knob metadata only in `settings.py`.
- Release scope is the default; repo scope only when asked (`--repo`).
- Ledger row format: `SET <dotted.key>=<json value>`, who `owner`, task `-`; `SET <key>=default` clears it; latest row per key wins.
- Version: skill `2.33.0` (mod unchanged).
- Devin cost is binary: `free` (catalog `cost_tier == 'Free'`) or `paid` (anything else, or unlisted). Paid spends the Devin quota and is removed only when the quota is `exhausted`. No hand-kept prices or dates (spec § Devin pricing, revised).
- Writing style in docs and CLI output: plain words, no em dashes, short lines (repo `AGENTS.md`).

## Review Focus

1. A `SET` row with malformed JSON already in a ledger (hand-edited): `load()` must skip it with a stderr warning, never crash every script. Test in Task 1.
2. Repo `budget.overrides: {opus_implement: false}` plus release `SET budget.overrides.opus_implement=true`: release wins per route, other repo vetoes survive. Test in Task 1.
3. `devin` missing, or `devin models` failing or printing non-JSON: the catalog falls back to the cache, then to SWE-2 high/medium free; never a crash. Test in Task 2.
4. `budget.mode` off with `CRITICAL`-level signals: no park, routes are SURPLUS's, posture label `OFF`. Test in Task 3.
5. `settings.py set --repo` when `.claude/coordinate.json` is tracked and main is dirty: refuse with the reason, write nothing. Test in Task 5.

---

### Task 1: Release overlay in `adapter.load`

**Files:**
- Modify: `S/adapter.py` (`load`, new helpers)
- Test: `tests/test_settings.py` (new)

**Interfaces:**
- Produces: `ad.load(path='.', release=None) -> (dict, main)`; with a release, applies its `SET` rows. `ad.release_sets(ledger_path) -> dict[str, object]` (dotted key → value, `default` rows remove the key). `ad.set_dotted(d, key, value)` / `ad.del_dotted(d, key)`. `a['_sources']: dict[str, 'release'|'repo'|'default']` for every key set by a row or present in the repo file (dotted, leaf level).

- [ ] **Step 1: Write failing tests** in `tests/test_settings.py`, class `ReleaseOverlay`, using a temp git repo with `.claude/coordinate.json` and `ledger.py init` on `.coordinate/releases/1.1`:
  - `test_set_row_overrides_repo`: repo `session_limits.hard_tokens` 650000, row `SET session_limits.hard_tokens=800000` → `load(repo, '1.1')[0]['session_limits']['hard_tokens'] == 800000`, `_sources['session_limits.hard_tokens'] == 'release'`; `load(repo)` (no release) still 650000.
  - `test_latest_row_wins_and_default_clears`: rows `=700000`, `=750000`, then `=default` → 650000 and source `repo`.
  - `test_override_merges_per_route`: repo overrides `{opus_implement: false, sonnet_review: false}`, row `SET budget.overrides.opus_implement=true` → `{opus_implement: True, sonnet_review: False}`.
  - `test_bad_json_row_is_skipped`: row `SET budget.mode=off` (unquoted, invalid JSON) → value stays `auto`, stderr contains `skipped`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_settings -v` → FAIL (`load() got an unexpected keyword 'release'`).
- [ ] **Step 3: Implement.** `release_sets` reads the timeline with `ledger.ROW`'s pattern (copy the regex into adapter to avoid the import cycle: `ledger` imports `adapter`), matches `^SET ([a-z_.0-9-]+)=(.*)$` on the event. `load` applies them after `DEFAULTS` merging, using `ledger_file(a, release)`. A missing release folder means no rows (no error).
- [ ] **Step 4: Run** the tests → PASS; then `python3 -m unittest discover tests` → all pass.
- [ ] **Step 5: Commit** `feat(settings): release SET rows layered in adapter.load`.

### Task 2: Presets, Devin catalog, relaxed Devin models, away-mode line

**Files:**
- Modify: `S/adapter.py` (`DEFAULTS`, `PRESETS`, `devin_model`, `devin_catalog`, `devin_cost`, `free_devin_models`, `auto_mode_line`, `auto_mode_outdated`)
- Test: `tests/test_settings.py` class `Catalog`

**Interfaces:**
- Produces:
  - `DEVIN_CATALOG = USER_STATE + '/devin-models.json'` (cache: `{"at": epoch, "models": {model_uid: {"tier": cost_tier, "summary": cost_summary}}}`).
  - `devin_catalog(refresh=False, run=subprocess.run) -> dict[str, dict]`: with `refresh`, runs `devin models list --format json` (timeout 60 s), flattens `families[].variants[]` by `model_uid`, writes the cache; on any failure (no binary, non-zero exit, bad JSON) returns the cache; no cache → `{'swe-2-high': {'tier': 'Free'}, 'swe-2-medium': {'tier': 'Free'}}`. Without `refresh`, reads the cache (same fallback).
  - `devin_cost(model, catalog=None) -> 'free'|'paid'`: `free` iff the catalog's `tier == 'Free'`.
  - `free_devin_models(catalog=None) -> list[str]`: free models, `swe-2-high` first if present, then the rest sorted.
  - `DEFAULTS['budget']['mode'] = 'auto'`, `DEFAULTS['routing'] = {'default_builder': 'devin'}`.
  - `PRESETS: dict[str, dict]` of dotted keys → values. Pin these values:
    - `balanced`: `{}`
    - `frugal`: `budget.overrides.<r>=False` for `haiku_implement, sonnet_implement, opus_implement, opus_review, sonnet_review, sonnet_critique, sonnet_eyeball`; `budget.five_hour_fit_pct=60`; `session_limits.soft_tokens=350000`; `session_limits.hard_tokens=500000`
    - `all-out`: `budget.overrides.<r>=True` for `haiku_implement, sonnet_implement, opus_implement, opus_review, sonnet_review, sonnet_critique`; `budget.mode='off'`; `session_limits.soft_tokens=600000`; `session_limits.hard_tokens=800000`
  - `devin_model(a, fusion=False) -> str`: no longer dies on a non-SWE-2 or non-`fusion-` model; prints `note: Devin model <m> is paid: it spends the Devin quota` to stderr when `devin_cost` is `paid`.
  - `auto_mode_line(main)`: names `--model <the devin.model or devin.fusion_model in {main}/.claude/coordinate.json>` instead of `swe-2-high|swe-2-medium`.
  - `auto_mode_outdated(main, home=None) -> bool`: an `autoMode.environment` line naming this repo still contains `swe-2-high|swe-2-medium`.

- [ ] **Step 1: Write failing tests** (fake `run` returning a trimmed copy of the real JSON: `swe-2-high` Free, `swe-2-flash-high` Free, `gemini-4-argon-high` High cost): `test_catalog_parses_and_caches` (cache file written; `free_devin_models() == ['swe-2-high', 'swe-2-flash-high']`); `test_catalog_failure_uses_cache` (Review Focus 3: run raises `FileNotFoundError`, then returns exit 1, then non-JSON → cached result each time; with no cache → SWE-2 fallback); `test_tier_change_flips_cost` (refresh with `swe-2-high` now `Low cost` → `devin_cost('swe-2-high') == 'paid'`); `test_unlisted_model_is_paid`; `test_devin_model_accepts_other` (`devin.model='gpt-astra'` returns it, stderr has `paid`); `test_auto_mode_line_names_adapter` (no `swe-2-high|` in the line, contains `coordinate.json`); `test_auto_mode_outdated` (settings file with the old line → True; new line → False); `test_presets_only_known_keys` (every preset key's parent exists in `DEFAULTS`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the interfaces above. Keep `DEVIN_BUILD_MODELS` as the recommended list (used by the picker and preflight notes).
- [ ] **Step 4: Run** `tests.test_settings` and the full suite → PASS (update any existing test that asserted the old die or the old line text; say which in the commit body).
- [ ] **Step 5: Commit** `feat(settings): presets, live Devin catalog, any Devin model`.

### Task 3: Budget routing: mode off, ticked routes, default builder, paid Devin

**Files:**
- Modify: `S/budget.py` (`posture`, `allowed`, `misfit`, `claude_candidates`, `summary`, `route_row`, `ROUTES`), `S/session.py` (`limits`)
- Test: `tests/test_settings.py` class `Routing`

**Interfaces:**
- Consumes: Task 2's `devin_cost`, `DEFAULTS` keys.
- Produces:
  - `posture(a, s)` returns `('OFF', pace, known)` when `a['budget']['mode'] == 'off'`; `ROUTES['OFF']` is `ROUTES['SURPLUS']` with note `Budget off: every route allowed; spend is still recorded on ROUTE rows.`
  - `misfit(...)` returns `None` under `OFF`.
  - `allowed(a, p, s)`: routes with `overrides[r] is True` join their kind's list whatever the posture (a ticked Claude build still subject to `misfit`); `False` removes; the default builder's route (`devin`→`devin_swe2`, `sonnet`→`sonnet_implement`, `haiku`→`haiku_implement`, `opus`→`opus_implement`) counts as ticked unless vetoed, and is moved first in `build`; when `ad.devin_cost(a['devin']['model']) == 'paid'` and the Devin quota is `exhausted`, `devin_swe2` is removed like Fusion.
  - `session.limits(a, 'OFF') == (soft, hard, False)` (no TIGHT lowering, no CRITICAL park).

- [ ] **Step 1: Write failing tests** (patch `budget.signals` and `budget._load` as `tests/test_budget.py` does):
  - `test_off_never_parks`: mode off, signals 7d 95% → posture `OFF`, `session.limits(a,'OFF')[2] is False`, `'opus_implement' in allowed(...)['build']`.
  - `test_ticked_opus_on_pace`: ON PACE, `overrides.opus_implement=True`, 5h 20% → in `build`; 5h 80% → not in `build` (misfit).
  - `test_default_builder_first`: `routing.default_builder='sonnet'`, ON PACE → `allowed(...)['build'][0] == 'sonnet_implement'`.
  - `test_paid_devin_dropped_when_exhausted`: `devin.model='gpt-astra'`, Devin `exhausted` → `devin_swe2` not in `build`; with `swe-2-high` → still there.
  - `test_route_row_off`: `route_row` under mode off writes `posture=OFF` and no `offposture`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the interfaces; `summary` prints `posture OFF (budget off)`.
- [ ] **Step 4: Run** `tests.test_settings tests.test_budget` and the full suite → PASS.
- [ ] **Step 5: Commit** `feat(settings): budget off, ticked routes, default builder, Devin cost`.

### Task 4: Scripts read the release's settings

**Files:**
- Modify: `S/session.py:main`, `S/status.py:main` (and its `paid` flag at `status.py:237`), `S/chain.py:main`, `S/budget.py:main` (`route` and any command taking `--release`), `S/preflight.py` (if it takes a release)
- Test: `tests/test_settings.py` class `Callers`

**Interfaces:**
- Consumes: `ad.load(path, release)`.
- Produces: every `--release R` command loads with `release=R` (after `resolve_release`; load once without, resolve, then reload with it). `status.py --json` devin rows: `paid = ad.devin_cost(model) == 'paid'`; top-level `settings: {key: value}` for the release's `SET` keys (empty dict when none).

- [ ] **Step 1: Write failing tests**: `test_status_json_lists_release_settings` (row `SET budget.mode="off"` → `status` JSON `settings == {'budget.mode': 'off'}`); `test_chain_uses_release_model` (row `SET devin.model="gpt-astra"`; patch `subprocess` in chain → the launch argv has `--model gpt-astra`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite → PASS.
- [ ] **Step 5: Commit** `feat(settings): release settings reach session, status, chain, budget`.

### Task 5: `settings.py` show / set / preset

**Files:**
- Create: `S/settings.py`
- Test: `tests/test_settings.py` class `SettingsCli`

**Interfaces:**
- Consumes: `ad.load`, `ad.PRESETS`, `ad.release_sets`, `ad.devin_cost`, `budget.ALL_ROUTES`, `ledger.add`.
- Produces (CLI, exit 0 ok, 2 bad input, 1 refused):
  - `settings.py show [<repo>] [--release R] [--json]`. Text groups: `WHO DOES THE WORK`, `HOW HARD TO SPEND`, `WHEN TO HAND OFF`; each knob line `<label>  <value>  (<source>)  <why>`. JSON: `{"release": R|null, "groups": [{"name", "knobs": [{"key","label","value","source","why","choices"}]}], "presets": {name: {dotted: value}}, "preset": <name of the matching preset or "custom">}`.
  - `settings.py set [<repo>] (--release R | --repo) <key>=<value> ...`. Value parsing: JSON first, else bare string. Validation by `KNOBS` (below); unknown key or bad value → exit 2 and print the valid keys/choices. Prints one confirmation line per change: `<label>: <old> -> <new> (release R)`; a release `true` over a repo `false` adds `(the repo has it off)`; `budget.mode=off` adds `the coordinator may use up your 5-hour and 7-day windows`; a non-free Devin model adds the quota note.
  - `settings.py preset [<repo>] (--release R | --repo) <balanced|frugal|all-out>`: writes only the keys whose effective value differs; `balanced` on a release writes `=default` rows for every release key set.
  - `KNOBS` (the only place knob metadata lives): `routing.default_builder` (devin|sonnet|haiku|opus), `budget.overrides.<route>` (bool, route in `ALL_ROUTES`), `budget.mode` (auto|off), `budget.five_hour_fit_pct` (int 1-100), `session_limits.soft_tokens` / `hard_tokens` (int, soft < hard < 1000000), `devin.model`, `devin.fusion_model` (non-empty str; `choices` in `show --json` = `ad.free_devin_models()` then the catalog's paid models with their `summary`). Each has `group`, `label`, `why`. Why-line for the limits: `turns cost more as context grows; a resume costs ~100k and 10 min; the hard limit leaves room to park before auto-compact`.
  - Repo scope writes `ad.adapter_path(main)`. When that file is tracked in git: refuse (exit 1) if main is dirty; else `git worktree add ../<repo>-settings -b chore/settings-<YYYYMMDD-HHMM>`, write and commit there, `git -C main merge --no-ff`, `git worktree remove`; print `pushed? no: git push when ready`. Untracked or `~/.config` file: write in place. Edits preserve the file's key order and 2-space indent (`json.dump(..., indent=2)` after loading with `object_pairs_hook=dict`), trailing newline.
  - A release scope with no release folder → exit 1, `no release folder: ledger.py init ...`.

- [ ] **Step 1: Write failing tests**: `test_show_json_groups` (3 groups, `preset == 'balanced'` on a fresh repo, `source == 'default'`); `test_set_release_row` (writes `SET budget.overrides.opus_implement=true` row, prints `Opus` and `release 1.1`); `test_set_unknown_key_exit_2`; `test_set_bad_limits_exit_2` (soft 700000 > hard 650000); `test_preset_frugal_release_then_balanced_clears`; `test_repo_scope_commits_on_chore_branch` (tracked adapter, clean main → main's log has a merge commit of `chore/settings-*`, file updated); `test_repo_scope_refuses_dirty_main` (Review Focus 5: exit 1, file unchanged); `test_set_paid_devin_model_notes_free` (cached catalog; `set devin.model=gemini-4-argon-high` prints `spends the Devin quota` and `free: swe-2-high`).
- [ ] **Step 2: Run** → FAIL (no module).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite → PASS.
- [ ] **Step 5: Commit** `feat(settings): settings.py show, set and preset`.

### Task 6: Preflight, quota-out suggestion, init

**Files:**
- Modify: `S/preflight.py` (devin checks ~line 85-101, auto-mode warning ~line 37), `S/chain.py` (the `DEVIN_OUT` stop ~line 143), `S/init.py` (draft + printed summary)
- Test: `tests/test_settings.py` class `PreflightInit`

**Interfaces:**
- Consumes: `ad.auto_mode_outdated`, `ad.devin_catalog`, `ad.devin_cost`, `ad.free_devin_models`.
- Produces:
  - preflight: calls `ad.devin_catalog(refresh=True)` once; `devin` missing is a FAIL only when `routing.default_builder == 'devin'` (else a WARN `devin CLI not on PATH: builds go to <builder>`); the adapter-model FAIL becomes a WARN when the model is paid: `Devin model <m> is paid (<summary>): builds spend the Devin quota. Free now: <free list>`; a WARN when a model that was `Free` in the previous cache is no longer free: `<m> is no longer free (<summary>). Free now: <list>. /coordinate settings to switch`; `auto_mode_outdated` warns `the autoMode line names SWE-2 only: re-paste it once: <auto_mode_line>`.
  - chain.py: on `DEVIN_OUT`, after recording `exhausted`, refreshes the catalog and prints `Devin quota ran out on <model>. Free now: <list>. Switch: settings.py set <repo> --release R devin.model=<first free>` before stopping the queue.
  - init: draft sets `routing.default_builder` to `devin` when `shutil.which('devin')`, else `sonnet`, and prints `Default implementer: <x> (change with /coordinate settings)`. The seven questions stay seven.
- [ ] **Step 1: Write failing tests**: `test_no_devin_not_fatal_with_sonnet_builder`; `test_preflight_warns_when_free_model_turns_paid` (previous cache `swe-2-high` Free, refreshed `Low cost` → warning has `no longer free` and `Free now: swe-2-flash-high`); `test_chain_quota_out_suggests_free` (log line `out of quota` → output has `Free now:` and `devin.model=swe-2-high`); `test_outdated_auto_mode_line_warns`; `test_init_without_devin_drafts_sonnet` (patch `shutil.which` → None).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite → PASS.
- [ ] **Step 5: Commit** `feat(settings): live Devin cost checks, quota-out suggestion, init default builder`.

### Task 7: SKILL.md picker, references, docs, version

**Files:**
- Modify: `plugins/coordinate/skills/coordinate/SKILL.md` (description triggers; new `## Settings` section; where it routes builds: take the first allowed build route), `references/adapter.md` (rows for `routing`, `budget.mode`, the live Devin catalog, release `SET` rows and precedence), `references/routing.md` (OFF posture row, ticked routes), `README.md` (modes/commands table row `/coordinate settings`; a short Settings paragraph), `CHANGELOG.md` (2.33.0), `plugins/coordinate/.claude-plugin/plugin.json` (2.33.0), `ROADMAP.md` + `publish/ROADMAP.md` (version line), spec status line → `shipped in 2.33.0`.
- Test: `tests/test_settings.py::SkillText` (`test_skill_mentions_settings`: SKILL.md contains `/coordinate settings` in the description and `settings.py show --json` in the section).

The `## Settings` section pins the picker flow (keep it under 25 lines):
1. `python3 $S/settings.py show <repo> --release R --json`.
2. `AskUserQuestion` screen 1: header `Preset`; options Balanced (Recommended), Frugal, All-out, Custom; each option's `preview` = that preset's knobs in the three groups (from the JSON).
3. After a preset: one question "Change anything in <preset>?" (No (Recommended) / Yes). Yes, or Custom → at most two dialogs: (a) builders Devin (multiSelect: SWE-2, Fusion), builders Claude (multiSelect: Haiku, Sonnet, Opus), reviewers (multiSelect: Opus, Fusion, Sonnet, SWE-2), default implementer; (b) budget on/off, 5h cutoff (85 Recommended / 60 / 95), hand-off (450k/650k Recommended, 350k/500k, 600k/800k), Devin model (the first free models from `choices`, the first marked Recommended; Other: free text; each option's description shows its cost summary).
   Toggle → routes: Sonnet reviewer = `sonnet_review`, `sonnet_critique`, `sonnet_eyeball`; SWE-2 reviewer = `swe2_review`, `devin_eyeball`; Opus = `opus_review`; Fusion = `fusion_review`; builders map one-to-one (`devin_swe2`, `devin_fusion`, `haiku_implement`, `sonnet_implement`, `opus_implement`).
4. Scope: This release (Recommended) / The whole repo.
5. `settings.py preset` then `settings.py set` with the diff; relay its confirmation lines verbatim.
6. Plain-language requests ("build with Opus", "budget off", "burn Devin on GPT-6 Astra") skip the picker: map to `settings.py set`, release scope unless the owner says repo, relay the confirmation.
7. Devin quota out (chain.py prints `Free now:`): a watched session asks the owner to switch to the first free model (one `AskUserQuestion`); away mode switches it for the release with `settings.py set`, records `decide --auto`, and relaunches the stopped task.

- [ ] **Step 1: Write the failing `SkillText` test** → run → FAIL.
- [ ] **Step 2: Write the docs and bump versions.**
- [ ] **Step 3: Run** `python3 -m unittest discover tests` and `claude plugin validate plugins/coordinate` → PASS.
- [ ] **Step 4: Commit** `docs(settings): SKILL picker, references, README, 2.33.0`.
