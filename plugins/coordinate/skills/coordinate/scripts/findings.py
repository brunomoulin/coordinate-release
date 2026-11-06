"""Read a review file's findings table (references/review-brief-template.md).

A findings row is `| <n> | <severity> | ... | <Disposition> |`, Disposition last; the severities
are SEVERITIES, which the review brief template names.
The coordinator fills it: `To fix in round N`, `Task N`, `Not doing: <why>`, `Fixed ...`.
Used by closeout.py (overrule counts, owed dispositions), dispose.py and audit.py.
"""
import re

# Risk and Nit: a project's own briefs asked for Bug / Risk / Nit and dispose.py found no rows
# (the second pilot's v2-perf). The template names this list, so briefs and this file agree.
SEVERITIES = ('Bug', 'Risk', 'Improvement', 'Suggestion', 'Nit')
# Any id: a re-review numbers its rows R2-1, R2-2 (pilot 2.11.0; `\w+` matched none of them).
ROW = re.compile(r'^\|\s*([^|\s]+)\s*\|\s*(' + '|'.join(SEVERITIES) + r')\s*\|', re.I)
# 2.10.0 disposition audit: all 4 overturned declines were deferrals written as declines
# ("when next touched", "revisit if noisy", "reviewer says none needed").
DEFERS = re.compile(r'(?i)\b(when|if|later|revisit|none needed|until|for now|next time)\b')


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def rows(path):
    """[(line index, number, severity, cells)] for every findings row; the Disposition is cells[-1]."""
    out = []
    for i, line in enumerate(open(path).read().split('\n')):
        m = ROW.match(line)
        if m:
            c = cells(line)
            if len(c) >= 6:
                out.append((i, m.group(1), m.group(2).capitalize(), c))
    return out


CONFIRMS = re.compile(r'(?i)\b(checked|holds|confirms?|verification|result correct)\b')


def classify(d, owner=None):
    """`owner`: the adapter's `owner_name`, matched beside the word "owner"."""
    if not d or set(d) <= set('-: '):
        return 'blank'
    if re.match(r'(?i)(not doing|won.?t|reject|no change)', d):
        # A reviewer's confirmation ("checked, holds") is not a finding the coordinator declined.
        return 'noted' if CONFIRMS.search(d[:80]) else 'overruled'
    names = r'\bowner\b' + (rf'|\b{re.escape(owner)}\b' if owner else '')
    if re.search('(?i)' + names, d) and not re.search(r'(?i)to fix|fixed', d):
        return 'to owner'
    if re.search(r'(?i)\btask\s*\d+|\bfiled\b|->\s*\d{3}', d) and not re.search(r'(?i)to fix|fixed', d):
        return 'filed'
    return 'fixed'


def defers(d):
    """A decline whose reason defers is a task, not a decline: it needs a Task N."""
    return classify(d) == 'overruled' and bool(DEFERS.search(d))
