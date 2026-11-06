"""RED-check by script: neuter the guard, run the test, restore, always.

  red_check.py <spec.json>

spec.json (write it with the Write tool, not a heredoc):
  {"cwd": "<worktree>/backend",
   "cmd": "npm run test:db -- src/tests/db/x.dbtest.ts",
   "checks": [{"name": "guard-removed", "file": "src/services/x.ts",
               "old": "<exact text, must occur once>", "new": "<neutered text>"}]}

For each check: patch, run, record, restore from the in-memory original (never `git restore`).
A check passes when the run FAILS (the test sees the missing guard). Exit 1 if any check stayed
green or a restore did not come back byte-identical. For DB tests, prefer running `cmd` through
db.py so the leak check and the lock apply.
"""
import json, os, subprocess, sys


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    spec = json.load(open(sys.argv[1]))
    cwd = spec['cwd']
    env = dict(os.environ)
    if spec.get('path_prefix'):
        env['PATH'] = spec['path_prefix'] + ':' + env['PATH']
    bad = 0
    for c in spec['checks']:
        path = os.path.join(cwd, c['file'])
        orig = open(path).read()
        n = orig.count(c['old'])
        if n != 1:
            print(f"=== {c['name']}: 'old' occurs {n} times in {c['file']}; skipped")
            bad += 1
            continue
        try:
            open(path, 'w').write(orig.replace(c['old'], c['new']))
            r = subprocess.run(spec['cmd'], shell=True, cwd=cwd, env=env, capture_output=True, text=True)
        finally:
            open(path, 'w').write(orig)
        restored = open(path).read() == orig
        out = (r.stdout + r.stderr).splitlines()
        keep = [l for l in out if any(s in l for s in ('×', '✓', 'Tests ', 'FAIL', 'AssertionError', 'Expected', 'Received'))]
        red = r.returncode != 0
        print(f"=== {c['name']}: exit {r.returncode} -> {'RED as expected' if red else 'STILL GREEN: the test does not see the guard'}"
              f" · restored {'yes' if restored else 'NO'}")
        print('\n'.join(keep[:14]))
        if not red or not restored:
            bad += 1
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
