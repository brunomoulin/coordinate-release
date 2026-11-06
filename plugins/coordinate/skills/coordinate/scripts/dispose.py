"""Fill the blank Disposition cells of a review file's findings table.

  dispose.py <review file> <default disposition> [<n>=<disposition> ...]

Only blank cells are written; a filled one is never overwritten. Then every "Not doing" in the
file whose reason defers ("when", "if", "later", "revisit", "none needed") is printed as a
WARN: a deferral is a task, so give it a Task N, or reword the reason if the decline is final.
Exit 1 when any such WARN is printed, or when the file has no findings row at all (a table in
another shape would otherwise fill 0 in silence).
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import findings as fd


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    path, default, overrides = args[0], args[1], args[2:]
    special = dict(o.split('=', 1) for o in overrides)
    lines = open(path).read().split('\n')
    if not fd.rows(path):
        print(f'WARN: no findings rows in {path}: expected `| <id> | {"|".join(fd.SEVERITIES)} | ... | <Disposition> |`')
        sys.exit(1)
    filled = 0
    for i, n, _, c in fd.rows(path):
        if fd.classify(c[-1]) != 'blank':
            continue
        d = special.get(n, default).replace('|', '/')
        lines[i] = re.sub(r'\|[^|]*\|\s*$', f'| {d} |', lines[i].rstrip())
        filled += 1
    open(path, 'w').write('\n'.join(lines))
    print(f'filled {filled}')
    warned = 0
    for _, n, sev, c in fd.rows(path):
        if fd.defers(c[-1]):
            print(f'WARN #{n} ({sev}): a decline that defers needs a Task N: {c[-1][:140]}')
            warned += 1
    sys.exit(1 if warned else 0)


if __name__ == '__main__':
    main()
