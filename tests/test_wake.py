"""wake.py command and arm checks. Run: python3 -m unittest discover tests"""
import io, os, sys, unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import wake

MAIN = '/w/app'
A = {'_main': MAIN, 'worktree_parent': '..', 'log_dir': '/tmp', 'release_dir': '/w/app/.coordinate/releases',
     'ledger_dir': '/w/app/.coordinate/ledgers'}


SUMMARY = '.coordinate/releases/2.11.0/now.md'


class Command(unittest.TestCase):
    def test_fresh_starts_a_new_session(self):
        # pilot 2.11.0 wave 4: -r woke a coordinator parked at ~280k against a 340k TIGHT limit.
        cmd = wake.command('2.11.0', 'abc', fresh=True, fork=False, park=SUMMARY)
        self.assertNotIn('-r', cmd)
        p = cmd[cmd.index('-n') + 2]
        self.assertTrue(p.startswith('resume coordinator on 2.11.0. '))
        self.assertIn('eyeball checks', p)

    def test_resume_keeps_the_session(self):
        cmd = wake.command('2.11.0', 'abc', fresh=False, fork=True, park=SUMMARY)
        self.assertEqual(cmd[cmd.index('-r') + 1], 'abc')
        self.assertIn('--fork-session', cmd)

    def test_a_background_session_the_owner_sees_on_their_phone(self):
        # 2026-10-26: the `claude -p` wake never showed in the Claude app; a `--bg` session
        # connects to Remote Control (remoteControlAtStartup) and is listed there.
        cmd = wake.command('2.11.0', 'abc', fresh=True, fork=False, park=SUMMARY)
        self.assertNotIn('-p', cmd)
        self.assertIn('--bg', cmd)
        self.assertEqual(cmd[cmd.index('-n') + 1], 'wake 2.11.0')

    def test_it_ends_with_its_park_sent_to_the_owner(self):
        # One path (the owner, 2026-10-26 19:47): the last park is the summary; no second file.
        p = wake.prompt('2.11.0', SUMMARY)
        self.assertIn(f'send {SUMMARY} with SendUserFile', p)
        self.assertIn('ledger.py park', p)
        self.assertIn('For you', p)
        self.assertIn('PushNotification', p)
        self.assertNotIn('wake-summary', p)

    def test_a_one_file_ledger_sends_the_park_file_it_gave(self):
        p = wake.prompt('2.11.0', None)
        self.assertIn('send the file you gave `ledger.py park` with SendUserFile', p)

    def test_the_park_file_is_now_md_in_a_release_folder(self):
        import tempfile
        d = tempfile.mkdtemp()
        a = {**A, 'release_dir': d, 'ledger_dir': os.path.join(d, 'ledgers')}
        os.makedirs(os.path.join(d, '2.12.0'))
        open(os.path.join(d, '2.12.0', 'timeline.md'), 'w').close()
        self.assertEqual(wake.park_file(a, '2.12.0'), os.path.join(d, '2.12.0', 'now.md'))
        os.makedirs(a['ledger_dir'])
        open(os.path.join(a['ledger_dir'], '2.11.0.md'), 'w').close()
        self.assertIsNone(wake.park_file(a, '2.11.0'))


class Watch(unittest.TestCase):
    """After `claude --bg` returns: working, or refused at the limit (then stopped and retried)."""
    def run_watch(self, states, logs):
        states, logs = iter(states), iter(logs)
        clock = [0.0]
        with mock.patch.object(wake, 'agent_state', side_effect=lambda i: next(states)), \
                mock.patch.object(wake, 'session_logs', side_effect=lambda i: next(logs)), \
                mock.patch.object(wake.subprocess, 'run') as run, \
                mock.patch.object(wake.time, 'time', side_effect=lambda: clock[0]), \
                mock.patch.object(wake.time, 'sleep', side_effect=lambda s: clock.__setitem__(0, clock[0] + s)):
            got = wake.watch(io.StringIO(), 'da1c')
        return got, run

    def test_busy_after_the_first_minute_is_awake(self):
        got, run = self.run_watch(['busy', 'busy', 'busy'], [])
        self.assertEqual(got, 'woke')
        run.assert_not_called()

    def test_a_limit_message_on_an_idle_session_is_a_refusal_and_stops_it(self):
        got, run = self.run_watch(['busy', 'idle', 'done'], ["\x1b[2m  You've hit your limit · resets 7pm\x1b[0m"])
        self.assertEqual(got, 'limit')
        self.assertEqual(run.call_args[0][0], ['claude', 'stop', 'da1c'])

    def test_a_turn_that_ended_without_a_limit_is_awake(self):
        got, _ = self.run_watch(['busy', 'idle', 'done'], ['Merged 466. Waiting on the owner for checks 7-18.'])
        self.assertEqual(got, 'woke')

    def test_a_session_that_vanished_is_a_failure(self):
        got, _ = self.run_watch(['busy', None], [])
        self.assertEqual(got, 'gone')

    def test_background_id_from_the_launch_line(self):
        self.assertEqual(wake.bg_id('\x1b[1mbackgrounded · da1c7991 · wake 2.11.0\n  claude agents ...'), 'da1c7991')
        self.assertIsNone(wake.bg_id('Workspace not trusted.'))


class Attached(unittest.TestCase):
    TREE = {31: (30, 'devin'), 30: (29, 'bash'), 29: (28, 'claude'), 28: (1, 'fish'),
            41: (1, 'python3'), 51: (50, 'devin'), 50: (2000, 'python3'), 2000: (1, 'systemd')}

    def ask(self, pid):
        with mock.patch.object(wake, 'parent', side_effect=lambda p: self.TREE.get(p)):
            return wake.attached(pid)

    def test_a_run_under_a_claude_process_dies_with_it(self):
        self.assertTrue(self.ask(31))

    def test_a_run_reparented_to_init_does_not(self):
        self.assertFalse(self.ask(41))
        self.assertFalse(self.ask(51))

    def test_a_run_that_just_ended_does_not_block(self):
        self.assertFalse(self.ask(99))

    def test_parent_reads_a_name_with_spaces_and_parens(self):
        stat = '7 (a) b (c)) S 6 7 7 0 -1'
        with mock.patch('builtins.open', mock.mock_open(read_data=stat)):
            self.assertEqual(wake.parent(7), (6, 'a) b (c)'))


class LiveRuns(unittest.TestCase):
    def test_only_this_repos_runs_count(self):
        devin = [('11', '/w/app-466', '/l/466.log', 'swe-2-high'),
                 ('12', '/w/app', '/l/main.log', 'swe-2-high'),
                 ('13', '/w/other-466', '/l/x.log', 'swe-2-high')]
        chains = [('21', '/w/app'), ('22', '/w/other')]
        with mock.patch.object(wake.status, 'devin_procs', return_value=devin), \
                mock.patch.object(wake, 'chain_procs', return_value=chains), \
                mock.patch.object(wake, 'attached', return_value=True):
            live = wake.live_runs(A)
        self.assertEqual([l.split()[0] for l in live], ['devin', 'devin', 'chain.py'])
        self.assertIn('pid 11', live[0])
        self.assertNotIn('pid 13', ' '.join(live))

    def test_a_run_outside_any_claude_session_does_not_block_arming(self):
        devin = [('11', '/w/app-466', '/l/466.log', 'swe-2-high'), ('12', '/w/app-467', '/l/467.log', 'swe-2-high')]
        chains = [('21', '/w/app'), ('22', '/w/app')]
        with mock.patch.object(wake.status, 'devin_procs', return_value=devin), \
                mock.patch.object(wake, 'chain_procs', return_value=chains), \
                mock.patch.object(wake, 'attached', side_effect=lambda pid: pid in (11, 22)):
            live = wake.live_runs(A)
        self.assertEqual([l.split()[:3] for l in live], [['devin', 'pid', '11'], ['chain.py', 'pid', '22']])

    def test_arm_refuses_while_runs_are_live(self):
        # /exit kills the coordinator's background children; a parked run would die unreported.
        argv = ['wake.py', MAIN, '--release', 'R', '--session', 'abc', '--fresh']
        with mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(wake.ad, 'load', return_value=(A, MAIN)), \
                mock.patch.object(wake, 'live_runs', return_value=['devin pid 11 in app-466']), \
                mock.patch.object(wake.subprocess, 'Popen') as popen, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(wake.main(), 2)
        popen.assert_not_called()
        self.assertIn('not armed', out.getvalue())

    def test_armed_says_the_exit_dialog_stops_only_the_followers(self):
        # The dialog lists every chain as a shell that "will stop": only its follower does.
        argv = ['wake.py', MAIN, '--release', 'R', '--session', 'abc', '--fresh']
        with mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(wake.ad, 'load', return_value=(A, MAIN)), \
                mock.patch.object(wake, 'live_runs', return_value=[]), \
                mock.patch.object(wake.subprocess, 'Popen'), redirect_stdout(io.StringIO()) as out:
            wake.main()
        self.assertIn('Exit and stop tasks', out.getvalue())

    def test_arm_detaches_into_its_own_session(self):
        argv = ['wake.py', MAIN, '--release', 'R', '--session', 'abc', '--fresh']
        with mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(wake.ad, 'load', return_value=(A, MAIN)), \
                mock.patch.object(wake, 'live_runs', return_value=[]), \
                mock.patch.object(wake.subprocess, 'Popen') as popen, redirect_stdout(io.StringIO()):
            self.assertEqual(wake.main(), 0)
        args, kw = popen.call_args
        self.assertTrue(kw['start_new_session'])
        self.assertIn('--foreground', args[0])
        self.assertIn('--fresh', args[0])


class OpenSession(unittest.TestCase):
    """2026-11-10: a parked session's leftover bash child carried the id and blocked 8 tries."""
    def held(self, out):
        with mock.patch.object(wake.subprocess, 'run', return_value=mock.Mock(stdout=out)):
            return wake.open_session('60c3ef0d')

    def test_a_claude_process_holds_the_session(self):
        self.assertTrue(self.held('42 claude -r 60c3ef0d-aa\n'))
        self.assertTrue(self.held('43 /home/u/.local/bin/claude --resume 60c3ef0d-aa\n'))

    def test_a_shell_whose_command_line_carries_the_id_does_not(self):
        self.assertEqual(self.held('2488206 /bin/bash -c source snap.sh && claude stop 60c3ef0d\n'), [])


class StopSelf(unittest.TestCase):
    """A woken session ends itself after its park, so the next wake is not blocked by it."""
    def stop(self, rows, env):
        with mock.patch.object(wake.status, 'agent_rows', return_value=rows), \
                mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(wake.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            code = wake.stop_self()
        return code, run

    def test_a_background_session_stops_itself(self):
        rows = [{'pid': 7, 'sessionId': 'da1c7991-aaaa', 'kind': 'background', 'status': 'idle'}]
        code, run = self.stop(rows, {'CLAUDE_CODE_SESSION_ID': 'da1c7991-aaaa', 'CLAUDE_PID': '7'})
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args[0][0], ['claude', 'stop', 'da1c7991'])

    def test_an_interactive_session_is_never_stopped(self):
        rows = [{'pid': 7, 'sessionId': 'da1c7991-aaaa', 'kind': 'interactive', 'status': 'busy'}]
        code, run = self.stop(rows, {'CLAUDE_CODE_SESSION_ID': 'da1c7991-aaaa', 'CLAUDE_PID': '7'})
        run.assert_not_called()

    def test_the_prompt_ends_with_the_stop(self):
        p = wake.prompt('2.11.0', SUMMARY)
        self.assertIn('--stop-self', p)
        self.assertGreater(p.index('--stop-self'), p.index('PushNotification'))


class GiveUp(unittest.TestCase):
    def test_a_wake_that_gives_up_tells_the_desktop(self):
        with mock.patch.object(wake.shutil, 'which', return_value='/usr/bin/notify-send'), \
                mock.patch.object(wake.subprocess, 'run') as run:
            wake.notify('wake 2.12.0 gave up')
        self.assertEqual(run.call_args[0][0][0], 'notify-send')
        self.assertIn('wake 2.12.0 gave up', run.call_args[0][0])

    def test_no_notify_send_is_not_an_error(self):
        with mock.patch.object(wake.shutil, 'which', return_value=None), \
                mock.patch.object(wake.subprocess, 'run') as run:
            wake.notify('x')
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
