"""init.py: type-check gates found by command, cheapest-first order, and a re-run on an existing
adapter asking only for the keys it lacks. Run: python3 -m unittest discover tests"""
import io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import init


def pkg(d, scripts, sub='.'):
    os.makedirs(os.path.join(d, sub), exist_ok=True)
    with open(os.path.join(d, sub, 'package.json'), 'w') as f:
        json.dump({'scripts': scripts}, f)


def gates(d):
    ranked, _ = init.node_gates(d)
    return [g['name'] for g in init.ordered(ranked + init.other_gates(d))]


class TypeCheckGates(unittest.TestCase):
    def test_compile_running_tsc_is_the_first_gate(self):
        with tempfile.TemporaryDirectory() as d:
            pkg(d, {'build': 'wxt build', 'test': 'vitest run', 'compile': 'tsc --noEmit'})
            self.assertEqual(gates(d), ['compile', 'test', 'build'])

    def test_other_type_checkers_count_whatever_the_name(self):
        for cmd in ('vue-tsc --noEmit', 'svelte-kit sync && svelte-check', 'astro check', 'npx tsc -p .'):
            with self.subTest(cmd=cmd), tempfile.TemporaryDirectory() as d:
                pkg(d, {'types': cmd})
                self.assertEqual(gates(d), ['types'])

    def test_build_running_tsc_stays_a_build_and_watch_or_hooks_are_not_gates(self):
        with tempfile.TemporaryDirectory() as d:
            pkg(d, {'build': 'tsc && vite build', 'dev': 'tsc --watch', 'prebuild': 'tsc', 'tsc-ish': 'tscx'})
            self.assertEqual(gates(d), ['build'])

    def test_cheapest_first_across_packages_and_makefile(self):
        with tempfile.TemporaryDirectory() as d:
            pkg(d, {'build': 'vite build', 'test': 'vitest', 'lint': 'eslint .'})
            pkg(d, {'test': 'vitest', 'typecheck': 'tsc --noEmit'}, sub='web')
            open(os.path.join(d, 'Makefile'), 'w').write('build:\n\ttrue\nlint:\n\ttrue\n')
            self.assertEqual(gates(d), ['web typecheck', 'lint', 'make lint', 'test', 'web test', 'build', 'make build'])


def repo(d):
    subprocess.run(['git', 'init', '-q', d], check=True)
    with open(os.path.join(d, 'AGENTS.md'), 'w') as f:
        f.write('rules\n')
    pkg(d, {'test': 'vitest', 'compile': 'tsc --noEmit'})


def run_init(d):
    out = io.StringIO()
    with mock.patch.object(sys, 'argv', ['init.py', d]), redirect_stdout(out):
        init.main()
    return out.getvalue()


class ReRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.realpath(self.tmp.name)
        repo(self.d)
        self.adapter = os.path.join(self.d, '.claude', 'coordinate.json')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, a):
        with open(self.adapter, 'w') as f:
            json.dump(a, f)

    def test_first_run_writes_the_draft_and_asks_all_seven(self):
        out = run_init(self.d)
        self.assertIn('DRAFT written', out)
        self.assertEqual(sum(out.count(f'\n{n}. ') for n in range(1, 8)), 7)
        self.assertEqual(json.load(open(self.adapter))['gates'][0]['name'], 'compile')

    def test_asks_only_for_missing_keys_and_lists_kept_ones(self):
        run_init(self.d)
        a = json.load(open(self.adapter))
        for k in ('tracker', 'tasks_file'):
            del a[k]
        a['test_slots'], a['ledger_archive'] = 2, 'documentation/ledgers/'
        self.write(a)
        before = open(self.adapter).read()
        out = run_init(self.d)
        self.assertIn('kept (', out)
        self.assertIn('test_slots, ledger_archive', out)
        self.assertIn('"tracker": "markdown"', out)
        self.assertIn('7. Task tracker', out)
        for n in range(1, 7):
            self.assertNotIn(f'\n{n}. ', out)
        self.assertEqual(open(self.adapter).read(), before)  # never rewritten without --force

    def test_up_to_date_adapter_asks_nothing(self):
        run_init(self.d)
        out = run_init(self.d)
        self.assertIn('adapter up to date', out)
        self.assertIn('preflight.py', out)
        self.assertNotIn('AskUserQuestion', out)

    def test_any_tracker_key_counts_as_answered(self):
        run_init(self.d)
        a = json.load(open(self.adapter))
        del a['tasks_file']
        a['tracker'] = 'none'
        self.write(a)
        out = run_init(self.d)
        self.assertIn('adapter up to date', out)
        self.assertIn('kept (', out)


if __name__ == '__main__':
    unittest.main()
