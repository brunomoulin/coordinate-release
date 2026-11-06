"""chain.py outlives the Claude session that started it. Real processes, a fake `devin` on PATH.
Run: python3 -m unittest discover tests"""
import json, os, signal, subprocess, sys, tempfile, time, unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts')
sys.path.insert(0, SCRIPTS)
import adapter as ad
import wake

CHAIN = os.path.join(SCRIPTS, 'chain.py')
FAKE_DEVIN = '#!/bin/sh\necho started\nsleep "${FAKE_DEVIN_SECONDS:-0}"\necho finished\n'


def git(cwd, *args):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)


def until(cond, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        if v := cond():
            return v
        time.sleep(0.05)
    return None


def read(path):
    try:
        return open(path).read()
    except OSError:
        return ''


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.repo = os.path.join(self.root.name, 'repo')
        os.makedirs(os.path.join(self.repo, '.claude'))
        git(self.repo, 'init', '-q', '-b', 'main')
        with open(os.path.join(self.repo, '.claude', 'coordinate.json'), 'w') as f:
            json.dump({'concurrency': {'devin': 99}, 'env_files': ['need.env']}, f)
        self.a, _ = ad.load(self.repo)
        self.bdir = ad.briefs_path(self.a, 'R')
        os.makedirs(self.bdir)
        self.qlog = os.path.join(self.bdir, 'queue.log')
        bin_ = os.path.join(self.root.name, 'bin')
        os.makedirs(bin_)
        devin = os.path.join(bin_, 'devin')
        with open(devin, 'w') as f:
            f.write(FAKE_DEVIN)
        os.chmod(devin, 0o755)
        self.env = {**os.environ, 'PATH': f'{bin_}:{os.environ["PATH"]}'}
        self.procs = []
        self.addCleanup(self.stop_all)

    def stop_all(self):
        for p in subprocess.run(['pgrep', '-f', self.root.name], capture_output=True, text=True).stdout.split():
            if int(p) != os.getpid():
                try:
                    os.kill(int(p), signal.SIGKILL)
                except OSError:
                    pass
        for p in self.procs:
            p.wait()
            p.stdout.close()

    def item(self, stem, env_file=True):
        wt = os.path.join(self.root.name, f'wt-{stem}')
        os.makedirs(wt)
        if env_file:
            open(os.path.join(wt, 'need.env'), 'w').close()
        brief = os.path.join(self.bdir, f'{stem}.md')
        open(brief, 'w').close()
        return f'{wt}={brief}'

    def launch(self, *items, seconds=0):
        """As the Bash tool does: a background command in its own session."""
        p = subprocess.Popen([sys.executable, CHAIN, self.repo, '--release', 'R', *items],
                             start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env={**self.env, 'FAKE_DEVIN_SECONDS': str(seconds)})
        self.procs.append(p)
        return p

    def worker(self):
        for pid, repo in wake.chain_procs():
            if repo == self.repo:
                return int(pid)
        return None

    def session_kill(self, p):
        """What /exit does to a background shell: its process group and every child, by SIGKILL."""
        kids = subprocess.run(['pgrep', '-P', str(p.pid)], capture_output=True, text=True).stdout.split()
        os.killpg(p.pid, signal.SIGKILL)
        for k in kids:
            try:
                os.kill(int(k), signal.SIGKILL)
            except OSError:
                pass
        p.wait()


class Detached(Fixture):
    def test_the_run_outlives_the_session_that_started_it(self):
        # second pilot v1: four chains running at the park, so no wake was armed and the
        # coordinator sat out a reset it could have woken from.
        p = self.launch(self.item('t1'), seconds=2)
        log = os.path.join(self.bdir, 't1.log')
        self.assertTrue(until(lambda: 'started' in read(log)))
        self.session_kill(p)
        self.assertTrue(until(lambda: 'end t1' in read(self.qlog).splitlines()),
                        f'no marker after the session went: {read(self.qlog)!r}')
        self.assertIn('finished', read(log))

    def test_the_session_still_hears_how_the_chain_ended(self):
        p = self.launch(self.item('t1'))
        out, _ = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 0)
        self.assertIn('end t1 exit 0', out)

    def test_a_stopped_queue_still_fails_for_the_session(self):
        p = self.launch(self.item('t1'), self.item('t2', env_file=False))
        out, _ = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 1)
        self.assertIn('queue stopped before t2', out)

    def test_a_worker_killed_midway_is_a_failure_for_the_session(self):
        p = self.launch(self.item('t1'), seconds=30)
        self.assertTrue(until(lambda: 'started' in read(os.path.join(self.bdir, 't1.log'))))
        os.kill(self.worker(), signal.SIGKILL)
        p.communicate(timeout=20)
        self.assertEqual(p.returncode, 1)

    def test_a_bad_item_is_refused_before_anything_detaches(self):
        p = self.launch(f'{self.root.name}/nope={self.bdir}/x.md')
        out, _ = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 1)
        self.assertIn('no worktree', out)
        self.assertIsNone(self.worker())

    def test_arming_the_wake_passes_a_detached_chain(self):
        p = self.launch(self.item('t1'), seconds=30)
        self.assertTrue(until(self.worker))
        self.assertTrue(until(lambda: '--follow' in read(f'/proc/{p.pid}/cmdline')),
                        'the launcher should end up as the follower')
        self.assertEqual([pid for pid, _ in wake.chain_procs() if int(pid) == p.pid], [])
        self.assertFalse(wake.attached(self.worker()))
        self.assertEqual(wake.live_runs(self.a), [])


if __name__ == '__main__':
    unittest.main()
