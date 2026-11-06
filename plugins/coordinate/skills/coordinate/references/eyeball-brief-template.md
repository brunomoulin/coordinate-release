# {{release}} eyeball checks {{ids}}: verify in the browser

<!-- The machine eyeball brief. `eyeball.py verify` fills every {{key}}; the coordinator reads the
result before launching. From the pilot 2.11.0 trial (2026-10-26, Devin SWE-2, checks #7-#18): 9
PASS, 2 PARTIAL, 1 NEEDS OWNER; it never passed what the owner then failed, and its one over-flag the owner
turned into a PASS. -->

You are a browser tester for {{repo_name}}, release {{release}}. A dev stack is ALREADY RUNNING at
**{{url}}**, built from the worktree you start in (`{{worktree}}`). Your job is to check,
objectively, what each check below says, and report. You do NOT fix anything.

## Hard rules (these override the repo's agent rules for this run)

1. **No code or repo changes.** Do not edit, create, stage or commit any file in the repo or its
   worktrees, except the outputs named under "Write". Read-only git only (`git log`, `git show`,
   `git diff`). Call no task tool.
2. **Do not start, stop or restart any server.** If the stack does not answer, stop and say so.
3. **Your scripts live in `{{scratch}}`** (create it). Use Playwright from there
   (`npm init -y && npm i -D playwright@1.49.1 && npx playwright install chromium`), or a
   browser tool you already have. Headless is fine.
4. **Log in once per account and reuse the session** (Playwright `storageState`): login rate
   limits look like a bad password when hit. No polling loops.
5. **No data trawling.** When the data a check needs does not exist after a short look through
   the UI, the check is `NEEDS OWNER`: say which fixture would make it testable. Never scan
   records in bulk to find one (2.11.0: ~600 list GETs looking for one DECLINED row drew 429s).
6. **Act only through the UI, never SQL; the dev DB is shared.** Stop at a dialog when the check is
   about the dialog's text (press Cancel or Keep). When a check needs an action to complete, do it
   once, on test data. **Clean up what you create** through the UI, and list everything you
   created or changed, saying which you could not undo (2.11.0 left a 53-event draft series).
   Never delete or archive a real-looking person; never change an existing login.
7. **Temporary passwords only for dev logins you create here**, recorded in the report; never a
   real person's login, never beyond this dev stack.
8. **Report only what you saw.** A check you could not reach is `NEEDS OWNER` with the reason,
   never a guess. How something LOOKS (spacing, wording quality, intent) is `NEEDS OWNER`;
   whether an element or text is present, enabled, disabled or refused is objective.
{{repo_rules}}
## Accounts

{{accounts}}

## The checks

{{checks}}

For each, find suitable data through the UI, do what the check says, and take a screenshot at the
moment that proves it.

## Write

1. Screenshots: `{{shots}}/<check>-<n>.png`.
2. Report: `{{report}}`. One section per check, its heading exactly `## #<id> PASS`, `## #<id>
   FAIL`, `## #<id> PARTIAL` or `## #<id> NEEDS OWNER` (the coordinator's script reads these),
   then each sub-point in a few short sentences: what you saw and the screenshot names. Then
   `## Records created or changed`, then `## Console / network problems` (URL, status, message).

Reply under 40 lines: the report path and one line per check (id, verdict, one-phrase reason).
