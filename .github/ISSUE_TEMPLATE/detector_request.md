---
name: Detector request
about: Propose a deterministic check for `acc doctor`
labels: doctor
---

## The check

<!-- One sentence: what should `acc doctor` flag? -->

## Why it matters

<!-- What goes wrong in a repo when this is missing — what a reader or reviewer
     would otherwise overlook. -->

## How to detect it deterministically

`acc doctor` findings must be reproducible: same repo in, same findings out, no
network, no time-of-day dependence. Describe the rule in those terms.

- Inputs: <!-- which files or scanned facts the check looks at -->
- Rule: <!-- the exact condition that makes it fire -->
- Level: <!-- warning or info -->
- Suggested code: <!-- a short stable string, e.g. stale-dashboard, weak-metadata -->

## False positives to avoid

<!-- Cases where a naive version of this rule would fire wrongly.
     Existing checks stay conservative on purpose (e.g. broken-link detection). -->

<!-- For reference, checks today include: stale-dashboard, missing/unreadable/
     truncated dashboard, generator-version drift, weak-metadata, near-empty
     instruction files, large files, broken relative-markdown-link (conservative),
     redaction count, and open-TODO count. -->
