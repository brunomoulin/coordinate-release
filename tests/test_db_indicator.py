"""The DB tier's run in status.py, beside the test slots. Run: python3 -m unittest discover tests"""
import fcntl, os, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import status
import testlock


class DbRun(unittest.TestCase):
    def setUp(self):
        self.a = {'log_dir': tempfile.mkdtemp(), 'db_test': {'cmd': 'npm run test:db'}, 'test_slots': 1}

    def test_free_when_nobody_holds_the_lock(self):
        with mock.patch.object(status, 'queued', return_value=0):
            self.assertEqual(status.db_run(self.a), {'holder': None, 'waiting': 0})

    def test_the_holder_line_while_a_run_holds_it(self):
        # A separate open file description: flock refuses it as it would another process.
        f = open(testlock.db_lock_path(self.a), 'a+')
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write('901 17:09:52 db app\n')
        f.flush()
        try:
            with mock.patch.object(status, 'queued', return_value=1) as q:
                self.assertEqual(status.db_run(self.a), {'holder': '901 17:09:52 db app', 'waiting': 1})
            self.assertEqual(q.call_args[0], ('db.py', {'901'}, '--wait'))
        finally:
            f.close()

    def test_a_line_left_by_a_finished_run_is_not_a_holder(self):
        with open(testlock.db_lock_path(self.a), 'w') as f:
            f.write('901 17:09:52 db app\n')
        with mock.patch.object(status, 'queued', return_value=0):
            self.assertIsNone(status.db_run(self.a)['holder'])

    def test_no_db_tier_no_entry(self):
        self.assertIsNone(status.db_run({**self.a, 'db_test': None}))


if __name__ == '__main__':
    unittest.main()
