"""Repoint links after close-out moves docs from one folder to another (e.g. active/ -> completed/).

  repoint_docs.py <root> --from documentation/active --to documentation/completed [--register <file>] <name>...

In .md/.ts/.tsx/.js/.json files under <root>, rewrites `<from>/<name>` to `<to>/<name>`, then the
relative form `<from-leaf>/<name>` to `<to-leaf>/<name>`. Skips verbatim records: history/
folders, the handoff file (--skip-file, repeatable; default agent-handoff.md), and
node_modules/.git/dist/.taskmaster. `--register` (the adapter's `taskmaster` file) also rewrites
the full paths inside the task register, as raw text so its formatting is untouched: archiving
2.10.0's review files left 29 register paths pointing at `.coordinate/briefs/`.
Prints each changed file and its count.
"""
import os, re, sys

SKIP_DIRS = {'node_modules', '.git', 'dist', 'history', '.taskmaster'}
EXT = ('.md', '.ts', '.tsx', '.js', '.json')


def rewrite(p, pats):
    try:
        s = open(p, encoding='utf-8').read()
    except (UnicodeDecodeError, OSError):
        return 0
    total = 0
    for pat, repl in pats:
        s, k = pat.subn(repl, s)
        total += k
    if total:
        open(p, 'w', encoding='utf-8').write(s)
    return total


def main():
    args = sys.argv[1:]
    if len(args) < 6 or '--from' not in args or '--to' not in args:
        sys.exit(__doc__)
    root = args.pop(0)
    skip_files = {'agent-handoff.md'}
    while '--skip-file' in args:
        i = args.index('--skip-file')
        skip_files.add(args[i + 1])
        del args[i:i + 2]
    register = None
    if '--register' in args:
        i = args.index('--register'); register = args[i + 1]; del args[i:i + 2]
    i = args.index('--from'); src = args[i + 1].rstrip('/'); del args[i:i + 2]
    i = args.index('--to'); dst = args[i + 1].rstrip('/'); del args[i:i + 2]
    names = '(' + '|'.join(re.escape(n) for n in args) + ')'
    full = (re.compile(re.escape(src) + '/' + names), dst + r'/\1')
    leaf = (re.compile(re.escape(os.path.basename(src)) + '/' + names), os.path.basename(dst) + r'/\1')
    changed = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(EXT) or fn in skip_files:
                continue
            p = os.path.join(dp, fn)
            k = rewrite(p, [full, leaf])
            if k:
                changed[os.path.relpath(p, root)] = k
    if register:
        p = register if os.path.isabs(register) else os.path.join(root, register)
        k = rewrite(p, [full])
        if k:
            changed[os.path.relpath(p, root)] = k
    for p, k in sorted(changed.items()):
        print(k, p)
    print(f'{len(changed)} files changed')


if __name__ == '__main__':
    main()
