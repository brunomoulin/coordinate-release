"""fusion_review in every posture; Claude tokens and ≈$ per task in the OUTCOME row. Run: python3 -m unittest discover tests"""
import json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'coordinate', 'skills', 'coordinate', 'scripts'))
import budget
import ledger as lg


class FusionReview(unittest.TestCase):
    def test_every_posture(self):
        # It spends the paid Devin quota, not Claude's: an agreed review trial needed --override.
        for p in budget.ROUTES:
            self.assertIn('fusion_review', budget.ROUTES[p]['review'], p)


def unix(t):
    return int(time.mktime(time.strptime(f'{time.strftime("%Y")}-{t}', '%Y-%m-%d %H:%M')))


class OutcomeCost(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.repo = os.path.join(self.root, 'app')
        self.f = os.path.join(self.repo, '.coordinate', 'releases', '2.12.0', 'now.md')
        os.makedirs(os.path.dirname(self.f))
        with open(self.f, 'w') as fh:
            for t, task, ev in (('10-26 10:00', '501', 'LAUNCHED feat/501'),
                                ('10-26 10:50', 'review-501', 'DONE bugs=2'),
                                ('10-26 12:00', '501', 'MERGED feat/501 into main @ abc')):
                fh.write(f'| {t} | {task} | coordinator | {ev} |\n')
        self.agents = os.path.join(self.root, 'agents')
        os.makedirs(self.agents)

    def write(self, name, cwd, agents):
        with open(os.path.join(self.agents, name), 'w') as fh:
            json.dump({'session': name, 'cwd': cwd, 'agents': agents}, fh)

    def a(self, desc, t, tokens, usd):
        return {'id': desc, 'description': desc, 'model': 'claude-opus-5-5', 'status': 'done',
                'started': unix(t) - 600, 'ended': unix(t), 'tokens': tokens, 'usd': usd}

    def test_sums_the_task_and_its_reviews_in_this_repo_and_window(self):
        self.write('s1.json', self.repo, [
            self.a('501 login fix', '10-26 10:30', 1_000_000, 3.0),
            self.a('review-501 opus', '10-26 10:50', 400_000, 1.25),
            self.a('5010 other task', '10-26 10:30', 9, 9.0),       # another task id
            self.a('501 last week', '10-19 10:30', 9, 9.0),         # outside launch..merge
        ])
        self.write('s2.json', os.path.join(self.root, 'other-repo'), [self.a('501 elsewhere', '10-26 10:30', 9, 9.0)])
        ev = lg.outcome(self.f, '501', agents_dir=self.agents)
        self.assertTrue(ev.endswith(' claude_tokens=1400000 claude_usd=4.25'), ev)

    def test_unknown_without_the_mod(self):
        ev = lg.outcome(self.f, '501', agents_dir=os.path.join(self.root, 'none'))
        self.assertTrue(ev.endswith(' claude_tokens=? claude_usd=?'), ev)

    def test_zero_for_a_devin_only_task(self):
        self.write('s1.json', self.repo, [])
        self.assertTrue(lg.outcome(self.f, '501', agents_dir=self.agents).endswith(' claude_tokens=0 claude_usd=0.00'))


if __name__ == '__main__':
    unittest.main()
