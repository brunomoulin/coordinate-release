"""Run a Claude review as a `claude -p` process. Run it in the background.

  claude_review.py <repo> --release R [--model sonnet|opus] <worktree>=<brief>

<worktree> is a task id (worktree `<parent>/<repo>-<id>`) or a path; <brief> is a review,
re-review or critique brief (`review-T87.md`), a file name in `<briefs_dir>/<release>/` or a path.
The reviewer reads the brief on stdin (`--allowedTools` is variadic and would eat a positional
prompt), works in the worktree with read tools, Write for its findings file and read-only git
(`Bash(rtk git:*)` too: the rtk hook rewrites `git`), and nothing else.

Why not `Agent`: a hook that cuts tool output cuts it for an Agent subagent too. context-mode 2.x
replaces any result over 4 KB with excerpts and a `ctx_search` line: a reviewer got about 12 lines
of a 10 KB `git show` (checked on 2.1.9). This reviewer runs with context-mode off (SETTINGS) and
reads whole diffs. The first reason was context-mode 1.x: its hook rewrote every Agent prompt
after auto mode's classifier checked it, so the classifier refused the call (the second pilot's
v2-perf, review-T87). 2.x leaves Agent alone, and auto mode accepts the call again.

Ledger rows, under the brief's stem (`review-T87`, its own task, never the build's): LAUNCHED with
<who> = the model (the close-out maps it to `sonnet_review` / `opus_review`), then EXITED with the
exit code and `claude_tokens=` / `claude_usd=` from the run's JSON result; the OUTCOME row of the
reviewed task sums those. The JSON result and stderr go to `<brief-stem>.log` beside the brief.
Not detached: like a bare `devin -p`, it dies with the session on `/exit`.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import ledger as lg
import status

MODELS = ('sonnet', 'opus')
TOOLS = ('Read,Grep,Glob,Write,WebFetch,Bash(git diff:*),Bash(git show:*),Bash(git log:*),'
         'Bash(git -C:*),Bash(rtk git:*)')
SETTINGS = json.dumps({'enabledPlugins': {'context-mode@context-mode': False}})
USAGE = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
MODEL_USAGE = ('inputTokens', 'outputTokens', 'cacheReadInputTokens', 'cacheCreationInputTokens')


def cost(out):
    """Tokens (all four input/output/cache fields, as the coordinator-status mod counts them) and
    ≈$ from `claude -p --output-format json` output; '?' when it is not that. `modelUsage` covers
    every model the run called, as `total_cost_usd` does; `usage` (the main model, all turns) is
    the fallback (claude 2.1.318 writes both)."""
    try:
        r = json.loads(out.strip().splitlines()[-1])
        if r.get('modelUsage'):
            tokens = sum(int(m.get(k) or 0) for m in r['modelUsage'].values() for k in MODEL_USAGE)
        else:
            tokens = sum(int(r['usage'].get(k) or 0) for k in USAGE)
        return tokens, f'{float(r["total_cost_usd"]):.2f}'
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return '?', '?'


def main():
    args = sys.argv[1:]
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    model = ad.opt(args, '--model') or 'sonnet'
    items = [x for x in args if not x.startswith('--')]
    if model not in MODELS:
        sys.exit(f'--model {model}: want {" or ".join(MODELS)} (a Haiku review is not a route)')
    if len(items) != 1 or '=' not in items[0]:
        sys.exit('want one <worktree>=<brief>\n\n' + __doc__)
    a, _ = ad.load(repo)
    release = ad.resolve_release(a, release)
    bdir = ad.briefs_path(a, release)
    wt, brief = items[0].split('=', 1)
    wt = wt if os.sep in wt else ad.worktree_path(a, wt)
    brief = brief if os.sep in brief else os.path.join(bdir, brief)
    if not os.path.isdir(wt):
        sys.exit(f'no worktree {wt}: worktree.py first')
    if not os.path.isfile(brief):
        sys.exit(f'no brief {brief}')
    if not status.is_review_brief(brief):
        sys.exit(f'{os.path.basename(brief)} is not a review brief (review-*, rereview-*, critique-*): '
                 'a Claude build goes through Agent (SKILL.md §3)')
    stem = os.path.splitext(os.path.basename(brief))[0]
    log = os.path.splitext(brief)[0] + '.log'
    lf = ad.ledger_file(a, release)
    if os.path.exists(lf):
        lg.add(lf, stem, model, f'LAUNCHED {stem} via claude_review.py ({model}, claude -p); log {log}')
    cmd = ['claude', '-p', '--model', model, '--permission-mode', 'acceptEdits',
           '--output-format', 'json', '--settings', SETTINGS, '--allowedTools', TOOLS]
    with open(brief) as b, open(log, 'a') as L:
        r = subprocess.run(cmd, cwd=wt, stdin=b, stdout=subprocess.PIPE, stderr=L, text=True)
        L.write(r.stdout)
    tokens, usd = cost(r.stdout)
    if os.path.exists(lf):
        lg.add(lf, stem, 'coordinator', f'EXITED {stem} exit {r.returncode} (claude -p) '
               f'claude_tokens={tokens} claude_usd={usd}: verify')
    print(f'end {stem} exit {r.returncode} claude_tokens={tokens} claude_usd={usd}', flush=True)
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
