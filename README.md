# coordinate

**Run a software release from one Claude Code session.** You plan the release; the coordinator
(the strongest Claude model) runs it: it breaks the work into tasks, briefs implementers and sends
each into its own git worktree, checks every claim with scripts, routes independent reviews, and
merges to your local `main` behind your gates. Implementers are Devin CLI by default, Claude
subagents (Haiku, Sonnet, Opus) when the weekly budget allows. You answer one batch of questions
per wave, eyeball the UI, and do every push.

<!-- Screenshot: the status pane with several agents running. -->

## Install

```
/plugin marketplace add brunomoulin/coordinate-release
/plugin install coordinate@coordinate
/plugin install coordinator-status@coordinate   # optional: the status pane
```

Restart Claude Code after installing. To update later:

```
claude plugin marketplace update coordinate
claude plugin update coordinate@coordinate
claude plugin update coordinator-status@coordinate
```

then restart the sessions that use it (`/exit`, then `claude --continue`): a running session keeps
the version it loaded.

## Quick start

1. In your repo, say `/coordinate init`. It drafts `.claude/coordinate.json` (gates, DB tier,
   handoff file, concurrency), gitignores `.coordinate/`, and asks a few questions (a re-run asks
   only what is missing). Commit the adapter.
2. Say `coordinate 1.1` (any release name). The coordinator reads your plan, asks its first batch
   of questions, and starts dispatching. With the mod installed, the status pane opens by itself.
3. When it parks (its context is full, or the 5-hour window is near its cap), `/clear` and say
   `resume coordinator on 1.1`.

## Modes and commands

| You say or type | What happens |
| --- | --- |
| `/coordinate init` | Set up a repo: detect gates and tiers, draft the adapter, ask the rest |
| `coordinate <release>` | **Watched mode** (the default): every real choice waits for you, in one batch per wave |
| `/coordinate away <release>` | **Away mode**, for nights and long breaks: the coordinator picks where undoing is cheap and records each pick; schema, deploy, security, product and prod choices wait for you |
| "away mode off" | Back to watched mode; you review the picks it made (ok or override each) |
| `resume coordinator on <release>` | Pick up after a park, `/clear`, a compaction or a usage limit |
| *(automatic)* | **Wake**: a release parked near the 5-hour cap restarts itself after the reset, in a background session you see in the Claude app |
| `/coord-status` | Open the status pane for the newest release |
| `/coord-status <release>` | Open it for a given release |
| `/coord-status close` | Close the pane (or its Close button) |
| ▣ / ✕ on the band | The band above the prompt: ▣ opens or closes the pane, ✕ hides the band |

Away mode is the coordinator's own decision policy. It is not Claude Code's auto permission mode,
and either can be on without the other.

## The status pane

The optional `coordinator-status` mod. The pane opens by itself the first time a coordinator starts
in a session (in a repo with an adapter); once you close it, it stays closed until `/coord-status`.
It shows:

- **Header:** the release, `away mode` when it is on, and HP / MP / XP bars: context used, the
  5-hour window, quests merged.
- **PARTY:** every Devin run and Claude subagent, with model, context, cost, time and its step bar;
  free Devin and test slots; the DB tier's run.
- **MAP:** the worktrees; ▸ unfolds one into its changed files.
- **QUEST LOG:** each task's latest ledger row; 👁 marks UI checks waiting on you.

It also writes the 5-hour and 7-day usage the budget posture reads; without the mod those signals
are unknown and the coordinator asks once a week.

With the [skins](https://github.com/hellosverre/claude-skins) mod on a skin you made (`/skin`), the
pane's status and highlight colours follow it; built-in skins keep the pane's own colours for now.

## What is in it

- `plugins/coordinate/skills/coordinate/SKILL.md`: the procedure.
- `scripts/`: `preflight`, `status`, `budget` (posture from the Claude and Devin weekly quotas),
  `session` (context limits), `worktree`, `gates`, `testlock` (queues test runs so implementers
  work in parallel), `chain` (chained Devin rounds), `db` (shared-DB tier with a guard and a leak
  check), `red_check`, `eyeball` (one preview tree for an unmerged stack), `merge` (gates the
  merged tree, writes the handoff entries), `resolve_append`, `ledger`, `dispose` (fills review
  dispositions), `closeout`, `audit` (the blind disposition audit), `repoint_docs`, `init`,
  `wake` (resumes a parked release after the 5-hour reset), `claude_review`; `adapter` and
  `findings` are shared modules. Python 3 standard library only.
- `references/`: routing and posture table, brief templates (implementer, reviewer, disposition
  audit), adapter keys, tooling facts.
- `plugins/coordinator-status/`: the status pane mod (TypeScript, loaded by Claude Code): the pane,
  a status line, the band above the prompt, and a `step` tool subagents report progress with.
- `examples/adapters/`: a Node monorepo and a full-stack app with a DB-test tier.

## Developing

Claude Code runs the skill from its plugin cache
(`~/.claude/plugins/cache/coordinate/coordinate/<version>/`), not from a checkout. To try a change
from a local checkout: `claude plugin marketplace add /path/to/coordinate`, then
`claude plugin install coordinate@coordinate`. Each change bumps
`plugins/coordinate/.claude-plugin/plugin.json`'s version and adds a `CHANGELOG.md` entry; then
update and restart as above. Tests: `python3 -m unittest discover tests`, and
`claude plugin test plugins/coordinator-status` for the mod.

## Plan

`ROADMAP.md`: where things stand and what comes next. `CHANGELOG.md`: what each version changed.

## Requirements

Claude Code, git, Python 3.10+, and the Devin CLI for Devin routes.

## Credits

The command-center mod adapts code from [Savvy Progress](https://github.com/johnnyvizz/claude-kit/tree/main/plugins/savvy-progress)
(MIT, johnnyvizz): per-agent context, cost and time, the band above the prompt and the `step`
tool. The MAP's worktree trees follow [Filetree](https://github.com/data-goblin/claude-code-filetree)
(MIT, Kurt Buhler).

## License

MIT
