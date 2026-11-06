# coordinate

Auto-loaded by Claude Code at session start. See `AGENTS.md` for workflow rules and
`documentation/` for specs.

## What This Is

A Claude Code plugin that runs a software release as a coordinator: it plans, briefs implementers
(Devin CLI or Claude subagents) in their own worktrees, verifies their claims with scripts, routes
reviews and gates every merge. `README.md` has the overview.

## Quick Reference

- **Never commit to `main`**: use `feature/*`/`bugfix/*` branches, each in its own `git worktree`,
  merged with `--no-ff` (see `AGENTS.md` § Parallel Agents)
- **Task tracking**: `ROADMAP.md`
- **Tests**: `python3 -m unittest discover tests` before every merge
- **Library APIs**: verify against current docs or `--help`, not training data alone
- **New specs** → `documentation/active/`; completed → `documentation/completed/`

## Structure

- `plugins/coordinate/skills/coordinate/`: `SKILL.md` (the procedure), `scripts/`, `references/`
- `plugins/coordinator-status/`: the optional command-center mod
- `tests/`: unittest suite for the scripts
- `examples/adapters/`: sample `.claude/coordinate.json` files
- `documentation/`: change docs, guides, history (`documentation/AGENTS.md`)
- `ROADMAP.md` (the plan), `CHANGELOG.md` (what shipped)

## Tech Stack

See `AGENTS.md` §"Tech Stack Quick Reference": single source of truth, don't re-derive it here.
