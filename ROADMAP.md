# Roadmap

Where coordinate stands and what comes next. What shipped, release by release, is in
`CHANGELOG.md`.

## Where we are

- **Skill 2.30.1, mod `coordinator-status` 0.8.0.** The skill has run several real releases end to
  end: planning waves, Devin and Claude implementers in worktrees, scripted verification, routed
  reviews, gated merges, close-out. Python 3.10+ standard library only; no server.
- The mod is optional. Without it, `budget.py` treats the 5-hour and 7-day signals as unknown.

## Next

1. **CI:** a GitHub Actions workflow that runs `python3 -m unittest discover tests` on every push.
2. **Wake reliability.** `wake.py` skips while the parked session is still open, so a session left
   open overnight never wakes; it should say so when it arms, notify when the work ends, and treat
   a long-idle session as closed. `status.py` should report a wake session that died (no control
   socket) as stale, not running.
3. **Claude builds in auto mode.** A PreToolUse hook that rewrites Agent prompts makes the
   auto-mode classifier refuse the call. Reviews already avoid this through `claude_review.py`
   (`claude -p`); builds need the same path.
4. **`chain.py` and `budget.py` usage lines** that name the task-label rule and the route names.
5. **Optional `hc` runner** (herdr-core): an adapter key `runner: "chain" | "hc"` and
   `scripts/hc_runner.py`, so workers keep running past the coordinator's session and `wake.py`
   can reattach to them. `chain.py` stays the default until `hc` has run a few real releases.

## Later

- **A route recommender** trained on the ledgers' machine-readable `ROUTE` and `OUTCOME` rows. It
  is logged beside the coordinator's own choice for a few releases and adopted only if it matches
  most good outcomes.

## Not yet tested end to end

- `wake.py` against a real parked release (tested with a fake `claude` only). Its open-session
  check matches the session id on a command line, so a session started as plain `claude` is not
  found.
- `eyeball.py checks` inside a real coordinator run, and the mod's 👁 marker on real checks.
- The mod's `turn.step` hook (live context per request); only the last-turn fallback has a test.

## Contributing

Issues and pull requests are welcome. Run `python3 -m unittest discover tests` before opening one;
`AGENTS.md` has the branch and review rules.
