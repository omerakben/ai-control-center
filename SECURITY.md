# Security

Agent Context Center (`ai-control-center`, CLI `acc`) generates a static, offline
`dashboard.html` from a repo's AI context files. The dashboard makes no network calls,
runs no server, and ships no tracking. The renderer writes repo content with `textContent`
only, so content from the scanned repo cannot inject script into the committed file.

## Redaction is a safety layer, not a secret scanner

Before anything is written into the dashboard, the generator:

- allowlists structured provider config, so only known-safe fields pass through, and
- runs free-form prose through a high-precision secret-shaped-string scanner, then
  re-scans the assembled output with a tripwire.

This favors precision over recall. It catches common secret shapes (tokens with telltale
prefixes, structured config values that are not on the allowlist). It is not a full
entropy scanner. A high-entropy value with no recognizable prefix can slip through.

Do not treat the dashboard as proof that a repo is free of secrets.

Advice:

- Keep running dedicated secret scanning in your pipeline. This tool does not replace it.
- Review a generated dashboard before you commit or publish one from a repo that holds
  sensitive content. The output is static and offline, so a review is a plain file read.
- The dashboard is meant to be committed. Treat it like any other artifact built from your
  source: if the source has a secret problem, the dashboard can inherit it.

## Reporting a vulnerability

Please do not file public issues for security problems.

- Open a private security advisory on GitHub: the repository's **Security** tab →
  **Report a vulnerability**.
- Or email the maintainer (Omer Akben) through the contact on the GitHub profile at
  https://github.com/omerakben.

Include the version, a description, and steps to reproduce. We will confirm receipt and
work with you on a fix and disclosure timeline.
