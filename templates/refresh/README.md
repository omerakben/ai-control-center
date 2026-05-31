# Refresh templates (opt-in)

Refresh is manual by default: a static `file://` page cannot detect that it is stale.
The active tiers are the `/dashboard` command and the agent re-stamping after it edits AI
markdown. These three templates add automatic refresh — none is active until you install
it yourself.

They are shipped as files (not as a plugin `hooks/hooks.json`) on purpose: a plugin hook
would activate on enable and regenerate the dashboard on every edit. Auto-installed hooks
are a v2 item; v1 keeps them opt-in.

| Template | What it does | Install |
| --- | --- | --- |
| `git-post-commit` | Re-stamps and stages the dashboard after each commit | `cp templates/refresh/git-post-commit .git/hooks/post-commit && chmod +x .git/hooks/post-commit` |
| `claude-file-write-hook.json` | Re-stamps after the agent edits a file | Paste its `hooks` block into your `.claude/settings.json` |
| `ci-drift-check.yml` | Fails CI if the committed dashboard is stale | `cp templates/refresh/ci-drift-check.yml .github/workflows/acc-drift.yml` |

## The generator must be available

The `/dashboard` command finds the generator inside the installed plugin automatically.
These templates run **outside** Claude Code's plugin context, so they need the `acc`
generator reachable on their own. Pick one:

- Install it (stdlib-only, no third-party deps):
  `pip install "git+https://github.com/omerakben/ai-control-center"` — gives you `acc`.
- Or point at a checkout without installing: set `ACC="python3 -m acc.cli"` and export
  `PYTHONPATH=/path/to/ai-control-center/src` for the git hook; use the same form in the
  Claude Code hook command.

The `git-post-commit` hook reads `ACC` (default `acc`) and no-ops with a message if the
command is missing, so a teammate without the generator is never blocked from committing.

## Notes

- All three are safe to run repeatedly: the generator is deterministic, so an unchanged
  repo regenerates byte-identical output and produces no diff.
- The git hook stages the refreshed dashboard for the **next** commit (a post-commit hook
  cannot amend the commit in progress). The CI drift check is the backstop that catches
  any lag on shared repos.
- Prefer keeping the dashboard in the same commit? Use the same body as a `pre-commit`
  hook instead, which re-stamps and `git add`s before the commit is created.
