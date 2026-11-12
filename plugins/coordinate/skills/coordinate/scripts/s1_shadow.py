"""Log a System One model's answers about a build brief. Shadow only: nothing is routed by them.

  s1_shadow.py <repo> --release R <task>=<brief>

<brief> is a file name in `<briefs_dir>/<release>/` or a path. Runs only when the adapter's
`system_one.mode` is `shadow` (off by default): it then sends the brief's text to TypeSafe's hosted
Jev with the questions in `references/s1-coordinate-risk.json` and adds one ledger row under the
task, `S1 <set>@<version> <question>=<value> ... model=<id>`. The task's OUTCOME row is the label:
the two are joined later to see whether the answers predict anything.

It never blocks a launch: no key, no network or a refused request gives an `S1 skipped: <reason>`
row and exit 0. A skipped call is not an answer.

Key: `TYPESAFE_API_KEY` in the environment, or a `TYPESAFE_API_KEY=` line in
`~/.config/typesafe/env`. `S1_ENDPOINT` overrides the URL (a local server with the same request
shape, or a test).
"""
import json, os, sys, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import ledger as lg

ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
SET = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'references', 's1-coordinate-risk.json')
KEY_FILE = '~/.config/typesafe/env'


def api_key():
    key = os.environ.get('TYPESAFE_API_KEY')
    path = os.path.expanduser(KEY_FILE)
    if not key and os.path.exists(path):
        for line in open(path):
            if line.strip().startswith('TYPESAFE_API_KEY='):
                key = line.strip().split('=', 1)[1].strip('"\'')
    return key


def ask(brief, qset, key):
    """The answers and the model id, or raises OSError / ValueError with the reason."""
    body = json.dumps({'model': qset.get('model', 'jev-latest'), 'state': {'brief': brief},
                       'questions': qset['questions']}).encode()
    req = urllib.request.Request(os.environ.get('S1_ENDPOINT') or ENDPOINT, data=body, headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
        'User-Agent': 'coordinate-s1-shadow'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise OSError(f'HTTP {e.code}') from e
    return out['answers'], out.get('model', '?')


def value(a):
    v = a.get(a.get('type'))
    return f'{v:.2f}' if isinstance(v, (int, float)) else '?'


def main():
    args = sys.argv[1:]
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    items = [x for x in args if not x.startswith('--')]
    if len(items) != 1 or '=' not in items[0]:
        sys.exit('want one <task>=<brief>\n\n' + __doc__)
    a, _, release = ad.load_release(repo, release)  # release scope overrides the repo's
    if (a.get('system_one') or {}).get('mode') != 'shadow':
        print('system_one.mode is off: nothing sent')
        return
    task, brief = items[0].split('=', 1)
    if not os.path.exists(brief):
        brief = os.path.join(ad.briefs_path(a, release), brief)
    if not os.path.exists(brief):
        sys.exit(f'no brief {brief}')
    qset = json.load(open(SET))
    name = f'{qset["name"]}@{qset["version"]}'
    key = api_key()
    try:
        if not key:
            raise OSError(f'no TYPESAFE_API_KEY (environment or {KEY_FILE})')
        answers, model = ask(open(brief).read(), qset, key)
        event = f'S1 {name} ' + ' '.join(f'{q}={value(answers[q])}' for q in qset['questions']) + f' model={model}'
    except (OSError, ValueError, KeyError, TypeError) as e:
        event = f'S1 skipped: {name}: {type(e).__name__}: {str(e)[:120]}'
    lf = ad.ledger_file(a, release)
    if os.path.exists(lf):
        lg.add(lf, task, 's1', event)
    print(event)


if __name__ == '__main__':
    main()
