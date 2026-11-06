"""v1 lessons, batch 2: a wake that waits for Devin work, and a resume that sees a wake in flight.
Run: python3 -m unittest discover tests"""
import io, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import status
import wake


def A(d):
    return {'_main': '/repo', 'log_dir': d, 'worktree_dir': '/repo-wt'}


class RepoWork(unittest.TestCase):
    def test_counts_this_repos_devins_and_chains_attached_or_not(self):
        devin = [('11', '/repo-wt/t1', 'log', 'm'), ('12', '/other', 'log', 'm')]
        chains = [(21, '/repo'), (22, '/other')]
        with mock.patch.object(wake.status, 'devin_procs', return_value=devin), \
                mock.patch.object(wake, 'chain_procs', return_value=chains), \
                mock.patch.object(wake.ad, 'worktree_path', return_value='/repo-wt/'):
            self.assertEqual(len(wake.repo_work(A('/x'))), 2)


class WaitForWork(unittest.TestCase):
    def run_wait(self, runs, cap=3600):
        clock = [0]
        out = io.StringIO()
        with mock.patch.object(wake, 'repo_work', side_effect=runs), \
                mock.patch.object(wake.time, 'time', side_effect=lambda: clock[0]), \
                mock.patch.object(wake.time, 'sleep', side_effect=lambda s: clock.__setitem__(0, clock[0] + s)):
            f = io.StringIO()
            ok = wake.wait_for_work(f, A('/x'), cap=cap)
        return ok, clock[0], f.getvalue()

    def test_returns_when_the_work_ends(self):
        ok, t, _ = self.run_wait(iter([['d'], ['d'], []]))
        self.assertTrue(ok)
        self.assertEqual(t, 2 * wake.WORK_POLL + wake.GRACE)

    def test_no_work_returns_at_once(self):
        ok, t, _ = self.run_wait(iter([[]]))
        self.assertTrue(ok)
        self.assertEqual(t, 0)

    def test_gives_up_at_the_cap(self):
        ok, _, log = self.run_wait(iter(lambda: ['d'], None), cap=300)
        self.assertFalse(ok)
        self.assertIn('still running', log)


class WakeLines(unittest.TestCase):
    def test_armed_wake_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'wake-R.pid'), 'w').write(str(os.getpid()))
            with mock.patch.object(status, 'agent_rows', return_value=[]):
                lines = status.wake_lines(A(d), 'R')
        self.assertTrue(any('WAKE ARMED' in l for l in lines))

    def test_stale_pidfile_is_not_armed(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'wake-R.pid'), 'w').write('999999999')
            with mock.patch.object(status, 'agent_rows', return_value=[]):
                self.assertEqual(status.wake_lines(A(d), 'R'), [])

    def test_running_woken_session_is_flagged(self):
        rows = [{'id': 'ab12', 'name': 'wake R', 'state': 'busy'},
                {'id': 'cd34', 'name': 'wake R', 'state': 'done'},
                {'id': 'ef56', 'name': 'wake Q', 'state': 'busy'}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(status, 'agent_rows', return_value=rows):
            lines = status.wake_lines(A(d), 'R')
        self.assertEqual(len(lines), 1)
        self.assertIn('WAKE SESSION RUNNING', lines[0])
        self.assertIn('ab12', lines[0])

    def test_no_claude_means_no_lines(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(status, 'agent_rows', return_value=None):
            self.assertEqual(status.wake_lines(A(d), 'R'), [])


class PidFile(unittest.TestCase):
    def test_arming_records_the_worker_pid(self):
        with tempfile.TemporaryDirectory() as d:
            a = A(d)
            argv = ['wake.py', '/repo', '--release', 'R', '--session', 's', '--fresh']
            with mock.patch.object(sys, 'argv', argv), \
                    mock.patch.object(wake.ad, 'load', return_value=(a, '/repo')), \
                    mock.patch.object(wake.ad, 'log_dir', return_value=d), \
                    mock.patch.object(wake, 'live_runs', return_value=[]), \
                    mock.patch.object(wake, 'park_file', return_value=None), \
                    mock.patch.object(wake.subprocess, 'Popen', return_value=mock.Mock(pid=4242)), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(wake.main(), 0)
            self.assertEqual(open(os.path.join(d, 'wake-R.pid')).read(), '4242')


if __name__ == '__main__':
    unittest.main()
