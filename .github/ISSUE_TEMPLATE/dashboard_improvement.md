---
name: Dashboard improvement
about: Suggest a change to the rendered dashboard.html (layout, readability, navigation)
labels: dashboard
---

## What part of the dashboard

<!-- Which section or affordance: a provider section, the reading pane, the
     cross-references view, truncation behavior, search/filter, the trust footer. -->

## What's hard right now

<!-- The friction you hit when reading or reviewing the dashboard. -->

## Proposed change

<!-- What you'd like instead. A sketch or screenshot helps. -->

## Constraints to keep

The dashboard is a single offline file with a few hard rules. A change here needs to
hold these:

- No network, no CDN, no build step — one self-contained file
- Deterministic, byte-stable output across runs
- textContent-only rendering (no `innerHTML`) so repo content cannot inject script
- Reviewable and committable as plain HTML
