"""Keep-both resolver for append-only files (handoff logs, constant lists, runbooks).

  resolve_append.py [--first ours|theirs] <file>...

Every conflict hunk becomes both sides, one after the other (default: ours first, which is main
when merging a branch into main). diff3 base sections are dropped. Markdown files get a blank
line between the two sides. Refuses to write a file that still has markers afterwards.

Keep-both is right only when each side ADDS whole entries. If a hunk edits the same lines on both
sides, or a side opens a block the other closes (a JSDoc, a table), fix that file by hand; the
merged-tree gates catch what this misses.
"""
import re, sys

HUNK = re.compile(r'<<<<<<< [^\n]*\n(.*?)(?:\|\|\|\|\|\|\| [^\n]*\n.*?)?=======\n(.*?)>>>>>>> [^\n]*\n', re.S)


def resolve(path, first):
    s = open(path).read()
    md = path.endswith('.md')
    n = [0]

    def rep(m):
        ours, theirs = m.group(1), m.group(2)
        a, b = (ours, theirs) if first == 'ours' else (theirs, ours)
        sep = '\n' if md and a and not a.endswith('\n\n') else ''
        n[0] += 1
        return a + sep + b

    s = HUNK.sub(rep, s)
    if re.search(r'^(<<<<<<<|=======$|>>>>>>>)', s, re.M):
        sys.exit(f'{path}: markers remain after {n[0]} hunks; resolve by hand')
    open(path, 'w').write(s)
    print(f'{path}: {n[0]} hunks kept both')


if __name__ == '__main__':
    args = sys.argv[1:]
    first = 'ours'
    if args[:1] == ['--first']:
        first = args[1]
        args = args[2:]
    if not args or first not in ('ours', 'theirs'):
        sys.exit(__doc__)
    for p in args:
        resolve(p, first)
