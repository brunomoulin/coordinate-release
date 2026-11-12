"""s1_shadow.py: the System One shadow log. A local HTTP server stands in for the hosted model."""
import http.server, json, os, subprocess, sys, tempfile, threading, unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts')
sys.path.insert(0, SCRIPTS)
import adapter as ad
import ledger as lg

TOOL = os.path.join(SCRIPTS, 's1_shadow.py')
QSET = json.load(open(os.path.join(SCRIPTS, '..', 'references', 's1-coordinate-risk.json')))


class Fake(http.server.BaseHTTPRequestHandler):
    seen, status = [], 200

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Fake.seen.append((dict(self.headers), body))
        answers = {q: ({'type': 'score', 'score': 1.5} if d['type'] == 'score' else {'type': 'noul', 'noul': 0.25})
                   for q, d in body['questions'].items()}
        out = json.dumps({'model': 'jev-test', 'answers': answers}).encode()
        self.send_response(Fake.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class Shadow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.srv.server_address[1]}/v1/systemone'

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        Fake.seen, Fake.status = [], 200
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.repo = os.path.join(self.root.name, 'repo')
        os.makedirs(os.path.join(self.repo, '.claude'))
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.repo, check=True)
        self.mode('shadow')
        a, _ = ad.load(self.repo)
        self.lf = os.path.join(ad.release_path(a, 'R'), 'timeline.md')
        lg.init_folder(ad.release_path(a, 'R'), 'R')
        os.makedirs(ad.briefs_path(a, 'R'), exist_ok=True)
        with open(os.path.join(ad.briefs_path(a, 'R'), 'T5.md'), 'w') as f:
            f.write('Task T5: add a retry to the sync job.')
        self.env = {**os.environ, 'S1_ENDPOINT': self.url, 'TYPESAFE_API_KEY': 'k-test',
                    'HOME': self.root.name}

    def mode(self, m):
        with open(os.path.join(self.repo, '.claude', 'coordinate.json'), 'w') as f:
            json.dump({'system_one': {'mode': m}} if m else {}, f)

    def run_tool(self, **env):
        return subprocess.run([sys.executable, TOOL, self.repo, '--release', 'R', 'T5=T5.md'],
                              env={**self.env, **env}, capture_output=True, text=True)

    def s1_rows(self):
        return [(k.strip(), w.strip(), ev.strip()) for _, k, w, ev in lg.rows(self.lf) if ev.strip().startswith('S1')]

    def test_shadow_logs_answers(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        headers, body = Fake.seen[0]
        self.assertEqual(headers['Authorization'], 'Bearer k-test')
        self.assertEqual(body['state'], {'brief': 'Task T5: add a retry to the sync job.'})
        self.assertEqual(set(body['questions']), set(QSET['questions']))
        (task, who, ev), = self.s1_rows()
        self.assertEqual((task, who), ('T5', 's1'))
        self.assertTrue(ev.startswith(f'S1 {QSET["name"]}@{QSET["version"]} '), ev)
        self.assertIn('db_schema=0.25', ev)
        self.assertIn('size=1.50', ev)
        self.assertIn('model=jev-test', ev)

    def test_off_by_default_sends_nothing(self):
        self.mode(None)
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Fake.seen, [])
        self.assertEqual(self.s1_rows(), [])

    def test_release_scope_turns_it_on(self):
        self.mode(None)
        subprocess.run([sys.executable, os.path.join(SCRIPTS, 'settings.py'), 'set', self.repo, '--release', 'R',
                        'system_one.mode=shadow'], env=self.env, capture_output=True, check=True)
        self.assertEqual(self.run_tool().returncode, 0)
        self.assertEqual(len(Fake.seen), 1)
        self.assertEqual(len(self.s1_rows()), 1)

    def test_refused_request_is_a_skipped_row(self):
        Fake.status = 500
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        (_, _, ev), = self.s1_rows()
        self.assertIn('S1 skipped', ev)
        self.assertIn('HTTP 500', ev)
        self.assertNotIn('db_schema=', ev)  # a failed call is not an answer

    def test_no_key_is_a_skipped_row(self):
        r = self.run_tool(TYPESAFE_API_KEY='')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Fake.seen, [])
        (_, _, ev), = self.s1_rows()
        self.assertIn('no TYPESAFE_API_KEY', ev)

    def test_question_set_shape(self):
        self.assertIsInstance(QSET['version'], int)
        for q, d in QSET['questions'].items():
            self.assertIn(d['type'], ('noul', 'score'), q)
            if d['type'] == 'score':
                self.assertIsInstance(d['criteria'], list, q)  # the API refuses a dict


if __name__ == '__main__':
    unittest.main()
