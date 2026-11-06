# coordinate

A Claude Code plugin for running a software release as a **coordinator**. The coordinator (the
strongest Claude model) plans, asks one batch of questions per wave, briefs implementers, and
dispatches them into their own git worktrees: Devin CLI by default, Claude subagents (Haiku,
Sonnet, Opus) when the weekly budget allows. It verifies every claim with scripts, routes
independent reviews, merges to local main, and gates the merged tree. A human eyeballs UI and does
every push.

## Install

```
/plugin marketplace add brunomoulin/coordinate-release
/plugin install coordinate@coordinate
/plugin install coordinator-status@coordinate   # optional command-center mod
```

The mod is optional: without it `budget.py` treats the 5-hour and 7-day signals as unknown.

From a local checkout: `claude plugin marketplace add /path/to/coordinate`, then
`claude plugin install coordinate@coordinate`.

## Set up a repo

Say `/coordinate init` in the repo. The skill runs `scripts/init.py`, which drafts
`.claude/coordinate.json` (gates, DB tier, handoff file, close-out skill, concurrency) and
gitignores `.coordinate/` (ledgers, briefs, logs). Answer its six questions, commit the adapter,
then say "coordinate <release>".

## What is in it

- `plugins/coordinate/skills/coordinate/SKILL.md`: the procedure.
- `scripts/`: `preflight`, `status`, `budget` (posture from the Claude and Devin weekly quotas),
  `session` (context limits), `worktree`, `gates`, `testlock` (queues test runs so implementers
  work in parallel), `chain` (chained Devin rounds), `db` (shared-DB tier with a guard and a leak
  check), `red_check`, `eyeball` (one preview tree for an unmerged stack), `merge` (gates the
  merged tree, writes the handoff entries), `resolve_append`, `ledger`, `dispose` (fills review
  dispositions), `closeout`, `audit` (the blind disposition audit), `repoint_docs`, `init`;
  `adapter` and `findings` are shared modules. Python 3 standard library only.
- `references/`: routing and posture table, brief templates (implementer, reviewer, disposition
  audit), adapter keys, tooling facts.
- `plugins/coordinator-status/`: the optional command-center mod (TypeScript, loaded by Claude Code):
  status line, `/coord-status` pane (party with per-agent context, cost and time; worktrees that unfold into
  their changed files;
  quest log; 👁 eyeball checks; slots), a band above the prompt, and a `step` tool for subagents.
- `examples/adapters/`: a Node monorepo and a full-stack app with a DB-test tier.

## Developing

Claude Code runs the skill from its plugin cache
(`~/.claude/plugins/cache/coordinate/coordinate/<version>/`), not from this checkout. After a
commit: bump `plugins/coordinate/.claude-plugin/plugin.json`'s version, add a `CHANGELOG.md`
entry, run `claude plugin marketplace update coordinate && claude plugin update
coordinate@coordinate`, then restart the sessions that use it (`/exit`, then `claude`). A
committed rule once never reached a running coordinator because this step was skipped. A parked
release can wake itself after the 5-hour reset: `scripts/wake.py` (see SKILL.md §8).

## Plan

`ROADMAP.md`: where things stand and what comes next. `CHANGELOG.md`: what each version changed.

## Requirements

Claude Code, git, Python 3.10+, and the Devin CLI for Devin routes. The budget posture reads
`~/.claude/coordinate/usage.json`, written by the coordinator-status mod; without it the posture
treats the 7-day window as unknown and asks once a week.

## Credits

The command-center mod adapts code from [Savvy Progress](https://github.com/johnnyvizz/claude-kit/tree/main/plugins/savvy-progress)
(MIT, johnnyvizz): per-agent context, cost and time, the band above the prompt and the `step`
tool. The MAP's worktree trees follow [Filetree](https://github.com/data-goblin/claude-code-filetree)
(MIT, Kurt Buhler).

## License

MIT
