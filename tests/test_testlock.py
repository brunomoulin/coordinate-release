"""testlock.py's worker budget and priority. Run: python3 -m unittest discover tests"""
import os, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import testlock

A = {'test_slots': 2, 'path_prefix': '', 'log_dir': '/tmp'}


class Budget(unittest.TestCase):
    """The owner, 2026-11-10: tests may take ~80% of the machine while it is in use; the whole of it
    in away mode, when nobody is at it."""
    def budget(self, cores, away, slots=2):
        with mock.patch.object(testlock.os, 'cpu_count', return_value=cores), \
                mock.patch.object(testlock, 'away_now', return_value=away):
            return testlock.worker_budget(dict(A, test_slots=slots))

    def test_eighty_percent_split_across_slots(self):
        self.assertEqual(self.budget(24, False), 9)   # 24 * 0.8 = 19 -> 9 per run

    def test_away_uses_the_whole_machine(self):
        self.assertEqual(self.budget(24, True), 12)

    def test_never_below_one(self):
        self.assertEqual(self.budget(1, False, slots=4), 1)

    def test_the_env_carries_the_budget(self):
        with mock.patch.object(testlock, 'worker_budget', return_value=9):
            e = testlock.run_env(A, {'PATH': '/bin'})
        self.assertEqual(e['TEST_WORKER_BUDGET'], '9')
        self.assertEqual(e['PATH'], '/bin')


class Nice(unittest.TestCase):
    def test_a_list_command_runs_niced(self):
        self.assertEqual(testlock.niced(['npm', 'test']), ['nice', '-n', '10', 'npm', 'test'])

    def test_a_shell_command_runs_niced(self):
        self.assertEqual(testlock.niced('cd web && npm test'), 'nice -n 10 sh -c \'cd web && npm test\'')


class Away(unittest.TestCase):
    def test_no_release_is_not_away(self):
        with mock.patch.object(testlock.ad, 'newest_ledger', return_value=None):
            self.assertFalse(testlock.away_now(A))


if __name__ == '__main__':
    unittest.main()
