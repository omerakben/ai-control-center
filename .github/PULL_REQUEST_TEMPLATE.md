<!-- Agent Context Center — pull request -->

## What changed

<!-- One or two sentences. What does this PR do and why? -->

## Screenshots (if the dashboard changed)

<!-- If this PR changes the rendered dashboard.html, drop a before/after screenshot.
     Delete this section if the dashboard output is unchanged. -->

## Tests run

```
python -m pytest
```

<!-- Paste the summary line (e.g. "261 passed"). Note any tests added. -->

## Generated dashboard updated?

<!-- yes / no -->

- [ ] yes — I ran `acc --root .` and committed the regenerated dashboard.html
- [ ] no — this PR does not change scanner, adapter, schema, or renderer output

## Risk notes

<!-- Anything a reviewer should watch: behavior changes, new file types scanned,
     redaction edge cases, performance on large repos, output format changes. -->

## Checklist

- [ ] Determinism preserved — output is byte-stable; new lists are explicitly sorted
- [ ] Redaction runs before render — secret-shaped values are scrubbed at extraction, and the output tripwire still holds
- [ ] No `innerHTML` in `app.js` — renderer stays textContent-only (the `test_appjs_guard` check passes)
- [ ] Docs updated — README / CONTRIBUTING / inline comments reflect the change
