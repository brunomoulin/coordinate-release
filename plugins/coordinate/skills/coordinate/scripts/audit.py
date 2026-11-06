"""Set up the blind disposition audit: a fresh Opus judges the coordinator's "Not doing" calls.

  audit.py <repo> --release R

Collects every finding disposed "Not doing" in the release's review files
(`<briefs_dir>/<R>/*-{code-review,rereview,critique}.md`) and writes `<briefs_dir>/<R>/audit/`:
  audit-blind.md    the findings with the reasons removed (phase 1)
  audit-reasons.md  the same findings with the coordinator's reasons (phase 2)
  audit-brief.md    the auditor's brief, from references/audit-brief-template.md
Then: `Agent` (model opus, background) with audit-brief.md as the prompt; when it replies "phase 1
written", SendMessage it to start phase 2. Overturned declines become tasks. 2.10.0: 4 of 13
overturned, every one a deferral written as a decline.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter as ad
import closeout
import findings as fd

HERE = os.path.dirname(os.path.abspath(__file__))


def collect(a, lf, release):
    out = []
    for p in closeout.review_files(a, release):
        route = closeout.review_route(lf, release, p) if os.path.exists(lf) else 'unmatched'
        lines = open(p).read().split('\n')
        for i, n, sev, c in fd.rows(p):
            if fd.classify(c[-1]) != 'overruled':
                continue
            # The column names come from the table's own header (critiques add Task and Where).
            hdr = next((fd.cells(lines[j]) for j in range(i, -1, -1)
                        if lines[j].lstrip().startswith('| #')), None)
            names = hdr[2:-1] if hdr and len(hdr) == len(c) else [f'column {k}' for k in range(3, len(c))]
            out.append({'file': os.path.basename(p), 'route': route, 'n': n, 'sev': sev,
                        'fields': list(zip(names, c[2:-1])), 'reason': c[-1]})
    return out


def block(i, f, with_reason):
    s = [f'## A{i} (review {f["file"]}, finding {f["n"]}, route {f["route"]})', '',
         f'- **Severity:** {f["sev"]}']
    s += [f'- **{k}:** {v}' for k, v in f['fields']]
    if with_reason:
        s.append(f'- **Coordinator\'s disposition:** {f["reason"]}')
    return '\n'.join(s) + '\n'


def main():
    args = sys.argv[1:]
    if len(args) < 3 or '--release' not in args:
        sys.exit(__doc__)
    repo = args.pop(0)
    release = ad.opt(args, '--release')
    a, main_ = ad.load(repo)
    release = ad.resolve_release(a, release)
    found = collect(a, ad.ledger_file(a, release), release)
    if not found:
        print(f'no "Not doing" dispositions in the {release} review files: nothing to audit')
        return
    d = os.path.join(ad.briefs_path(a, release), 'audit')
    os.makedirs(d, exist_ok=True)
    for name, title, with_reason in (('audit-blind.md', 'reasons removed', False),
                                     ('audit-reasons.md', 'with the coordinator\'s reasons', True)):
        body = '\n'.join(block(i, f, with_reason) for i, f in enumerate(found, 1))
        open(os.path.join(d, name), 'w').write(f'# {release} overruled findings, {title}\n\n{body}')
    tpl = open(os.path.join(HERE, '..', 'references', 'audit-brief-template.md')).read()
    brief = tpl.split('```markdown\n', 1)[1].rsplit('\n```', 1)[0].format(
        release=release, n=len(found), repo=main_, dir=os.path.relpath(d, main_),
        rules=a.get('repo_rules') or 'AGENTS.md')
    open(os.path.join(d, 'audit-brief.md'), 'w').write(brief + '\n')
    print(f'{len(found)} declines -> {d}/audit-blind.md, audit-reasons.md, audit-brief.md')
    print('Next: Agent (model opus, run_in_background) with audit-brief.md as the prompt; on '
          '"phase 1 written", SendMessage it to start phase 2. Overturned declines become tasks.')


if __name__ == '__main__':
    main()
