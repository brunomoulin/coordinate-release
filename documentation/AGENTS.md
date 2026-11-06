# Documentation Rules — coordinate

How docs are organised in this repo. Lean by design. Started 2026-11-06.

## Folders

| Folder | Holds | Lifecycle |
|---|---|---|
| `active/` | Change docs for work in progress (see `../AGENTS.md` § Change Docs) | Move to `completed/` when the chain closes |
| `completed/` | Finished change docs (historical record) | Append-only |
| `history/` | Evaluations and decision write-ups worth keeping (e.g. `2026-10-26-release-folders.md`) | Append-only |
| `history/bugfixes/` | One write-up per non-trivial bug fix | Append-only |
| `guides/` | Durable how-tos and templates (`change-doc-template.md`) | Update in place |

`ROADMAP.md` (the plan and task tracker) and `CHANGELOG.md` (what shipped) stay at the repo root.
The skill's own procedure and references live with the plugin, in
`plugins/coordinate/skills/coordinate/`, not here.

## Conventions

- One topic per file. Kebab-case filenames.
- Start each doc with a one-line purpose and a date.
- Convert relative dates to absolute (e.g. "next week" → "2026-11-13").
- Link related docs by relative path.

## When you finish a piece of work

1. Merge the branch to `main` with `--no-ff` (tests green).
2. Move its change doc from `active/` to `completed/`.
3. If it changed a convention, update the relevant file in `guides/`.

## What does NOT belong here

- Secrets or credentials.
- Tool working state (`.coordinate/`, `graphify-out/`, `.remember/`).
- Ledgers of releases coordinated on other repos: those stay in that repo's `.coordinate/`.
