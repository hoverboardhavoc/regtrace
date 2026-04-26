---
regtrace_version: vX.Y
date: YYYY-MM-DD
peripheral: NAME
decision: share          # share | share-with-shim | share-with-macro | split
confidence: empirical    # empirical | partial | inferred
libraries_compared:
  - name: <library>
    rev: <tag-or-commit>
    target: <target>
  - name: <library>
    rev: <tag-or-commit>
    target: <target>
evidence:
  - golden/<library>/<rev>/<target>/<vector>.trace
  - golden/<library>/<rev>/<target>/<vector>.trace
draft_pr: TBD            # path to .patch in draft-prs/<regtrace-version>/, or TBD
---

# <PERIPHERAL> share-or-split decision

## Summary
One paragraph: what was compared, what was found, what was recommended.

## Method
Vectors used, comparison modes, anything notable about the methodology.

## Diff outcome
Map onto the four-level scale:

| level | meaning | applies here? |
|---|---|---|
| bit-identical | silicon really is the same at register level | yes/no/partial |
| identical structure, different reset values or default bits | functionally compatible, vendor differs on initial state | … |
| identical mostly, divergent on one or two bit-fields | mostly shared, vendor-specific carve-out | … |
| diverges fundamentally | parallel design that happens to look similar | … |

## Recommended action
Share / Share with reset shim / Share with parameterised macro / Split — and why.

## Implementation sketch
What code change in libopencm3 (or wherever) the recommendation translates into.

## Open questions
What this analysis didn't cover; what would change the recommendation.
