"""claude_review.py: a Claude reviewer as a `claude -p` process, counted in the OUTCOME row.
Real processes, a fake `claude` on PATH. Run: python3 -m unittest discover tests"""
import json, os, subprocess, sys, tempfile, unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts')
sys.path.insert(0, SCRIPTS)
import adapter as ad
import claude_review as cr
import ledger as lg

TOOL = os.path.join(SCRIPTS, 'claude_review.py')
RESULT = {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'wrote the review',
          'total_cost_usd': 0.4213, 'session_id': 'abc',
          'usage': {'input_tokens': 10, 'output_tokens': 2000, 'cache_read_input_tokens': 300000,
                    'cache_creation_input_tokens': 40000}}
# Records its argv and stdin, prints the JSON result, exits with FAKE_EXIT.
FAKE_CLAUDE = f'''#!{sys.executable}
import json, os, sys
open(os.environ['FAKE_ARGS'], 'w').write(json.dumps({{'argv': sys.argv[1:], 'stdin': sys.stdin.read(), 'cwd': os.getcwd()}}))
print(os.environ.get('FAKE_OUT', {json.dumps(json.dumps(RESULT))}))
sys.exit(int(os.environ.get('FAKE_EXIT', '0')))
'''


class Parse(unittest.TestCase):
    def test_tokens_and_usd(self):
        # Tokens as the mod counts them: all four usage fields.
        self.assertEqual(cr.cost(json.dumps(RESULT)), (342010, '0.42'))

    def test_model_usage_wins(self):
        # Every model the run called (claude 2.1.318 writes modelUsage beside usage).
        r = {**RESULT, 'modelUsage': {
            'claude-sonnet-5-5': {'inputTokens': 6, 'outputTokens': 240, 'cacheReadInputTokens': 78653,
                                  'cacheCreationInputTokens': 24431, 'contextWindow': 1000000},
            'claude-haiku-5-5': {'inputTokens': 100, 'outputTokens': 20, 'cacheReadInputTokens': 0,
                                 'cacheCreationInputTokens': 0}}}
        self.assertEqual(cr.cost(json.dumps(r)), (103450, '0.42'))

    def test_unreadable_output(self):
        self.assertEqual(cr.cost('Error: something broke'), ('?', '?'))


class Run(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.repo = os.path.join(self.root.name, 'repo')
        os.makedirs(os.path.join(self.repo, '.claude'))
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.repo, check=True)
        with open(os.path.join(self.repo, '.claude', 'coordinate.json'), 'w') as f:
            json.dump({}, f)
        self.a, _ = ad.load(self.repo)
        self.lf = os.path.join(ad.release_path(self.a, 'R'), 'timeline.md')
        lg.init_folder(ad.release_path(self.a, 'R'), 'R')
        self.bdir = ad.briefs_path(self.a, 'R')
        os.makedirs(self.bdir, exist_ok=True)
        self.wt = ad.worktree_path(self.a, 'T87')
        os.makedirs(self.wt)
        with open(os.path.join(self.bdir, 'review-T87.md'), 'w') as f:
            f.write('Review T87. Write briefs/R-T87-code-review.md.')
        bin_ = os.path.join(self.root.name, 'bin')
        os.makedirs(bin_)
        with open(os.path.join(bin_, 'claude'), 'w') as f:
            f.write(FAKE_CLAUDE)
        os.chmod(os.path.join(bin_, 'claude'), 0o755)
        self.args = os.path.join(self.root.name, 'args.json')
        self.env = {**os.environ, 'PATH': f'{bin_}:{os.environ["PATH"]}', 'FAKE_ARGS': self.args}

    def run_tool(self, *items, **env):
        return subprocess.run([sys.executable, TOOL, self.repo, '--release', 'R', *items],
                              env={**self.env, **env}, capture_output=True, text=True)

    def rows(self):
        rs = [(k.strip(), w.strip(), ev.strip()) for _, k, w, ev in lg.rows(self.lf)]
        return [next(r for r in rs if r[2].startswith(p)) for p in ('ROUTE', 'LAUNCHED', 'EXITED')]

    def test_launch_and_rows(self):
        r = self.run_tool('T87=review-T87.md')
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.load(open(self.args))
        self.assertEqual(os.path.realpath(got['cwd']), os.path.realpath(self.wt))
        self.assertIn('Review T87', got['stdin'])  # on stdin: --allowedTools would eat a positional prompt
        argv = got['argv']
        self.assertEqual(argv[argv.index('--model') + 1], 'sonnet')
        self.assertEqual(argv[argv.index('--output-format') + 1], 'json')
        tools = argv[argv.index('--allowedTools') + 1]
        self.assertIn('Bash(rtk git:*)', tools)  # rtk rewrites git; without it no git diff
        self.assertIn('Write', tools)
        route, launched, exited = self.rows()
        self.assertIn('ROUTE -> sonnet_review', route[2])  # inferred from who=sonnet, as closeout does
        self.assertEqual(launched[:2], ('review-T87', 'sonnet'))
        self.assertEqual(exited[:2], ('review-T87', 'coordinator'))
        self.assertIn('EXITED review-T87 exit 0', exited[2])
        self.assertIn('claude_tokens=342010 claude_usd=0.42', exited[2])
        log = open(os.path.join(self.bdir, 'review-T87.log')).read()
        self.assertIn('wrote the review', log)

    def test_opus_and_failure(self):
        r = self.run_tool('--model', 'opus', 'T87=review-T87.md', FAKE_EXIT='3', FAKE_OUT='boom')
        self.assertEqual(r.returncode, 3)
        route, launched, exited = self.rows()
        self.assertIn('ROUTE -> opus_review', route[2])
        self.assertEqual(launched[1], 'opus')
        self.assertIn('exit 3', exited[2])
        self.assertIn('claude_tokens=? claude_usd=?', exited[2])

    def test_refuses_a_build_brief(self):
        open(os.path.join(self.bdir, 'T87.md'), 'w').close()
        r = self.run_tool('T87=T87.md')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('not a review', r.stderr + r.stdout)
        self.assertFalse(os.path.exists(self.args))

    def test_refuses_unknown_model(self):
        r = self.run_tool('--model', 'haiku', 'T87=review-T87.md')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.args))


class Outcome(unittest.TestCase):
    """The OUTCOME row counts a claude_review.py run with no coordinator-status mod at all."""
    def test_counts_exited_rows(self):
        d = tempfile.mkdtemp()
        f = os.path.join(d, 'repo', '.coordinate', 'releases', 'R', 'timeline.md')
        os.makedirs(os.path.dirname(f))
        with open(f, 'w') as fh:
            for t, task, ev in (('10-26 10:00', 'T87', 'LAUNCHED T87'),
                                ('10-26 10:40', 'review-T87', 'EXITED review-T87 exit 0 (claude -p) claude_tokens=1000 claude_usd=0.30: verify'),
                                ('10-26 11:00', 'rereview-T87-r2', 'EXITED rereview-T87-r2 exit 0 (claude -p) claude_tokens=500 claude_usd=0.12: verify'),
                                ('10-26 11:05', 'review-T9', 'EXITED review-T9 exit 0 (claude -p) claude_tokens=9 claude_usd=9.00: verify'),
                                ('10-26 12:00', 'T87', 'MERGED feat/T87 into main @ abc')):
                fh.write(f'| {t} | {task} | coordinator | {ev} |\n')
        self.assertEqual(lg.claude_cost(f, 'T87', agents_dir=os.path.join(d, 'none')), (1500, '0.42'))
        self.assertEqual(lg.claude_cost(f, 'T5', agents_dir=os.path.join(d, 'none')), ('?', '?'))


if __name__ == '__main__':
    unittest.main()
