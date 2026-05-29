# AI control center dashboard — design spec

Date: 2026-05-29
Status: approved for planning
Project: html-dash

## Problem

Markdown is the right format for AI agents in a repo. Config, intent, decisions, and capability definitions all live there: `CLAUDE.md`, `AGENTS.md`, Cursor rules, skills, agents, hooks, commands, MCP config, PRDs, ADRs. Agents read and write it well.

For a human it gets hard fast. Once a repo holds twenty-plus markdown files spread across `.claude/`, `docs/`, and the tree, a person loses the thread: what exists, how pieces connect, what was decided and why, where the project stands. The information is all there and none of it is navigable.

## Goal

Keep markdown as the source of truth for the machine. Add a second layer for the human: one self-contained HTML file that is the read-oriented control center for everything AI in the project. The human opens one file and sees scope, the inventory of skills/agents/hooks/commands/MCP/rules, PRDs, decisions, doc index, project state, and how things relate. Markdown for the machine, HTML for the human.

The product ships as a public skill plus a marketplace plugin. The skill, the bundled generator, and the HTML it produces are the entire product.

## Hard constraints

These are the point of the product, not preferences.

- One standalone HTML file. Self-contained, opens from `file://` with no server, no build step, no framework, and nothing added to the user's repo at runtime.
- Lives under the AI-provider folder (`.claude/`, `.codex/`, `.cursor/`), never in the source tree. A loose `.html` in the repo root or `src/` collides with web-framework globs (Vite `**/*.html`, Angular and Next entry points). Under the provider folder it is inert to any build.
- Works on greenfield and brownfield repos, and on repos that are not under git.
- Init-triggered: provider init produces the markdown and the HTML together; later markdown changes re-stamp the HTML.

## Decisions and rationale

These were resolved during design. Each one closes off an alternative on purpose.

1. Committed and shared. The HTML is checked in and travels with the repo, treated like `CLAUDE.md` and `AGENTS.md`. Consequence: output must be deterministic or every re-stamp churns the diff, and redaction is mandatory because the file can be pushed to a public remote.
2. Project-level state, not personal. "Where we left off" is reframed as shared, derivable facts: current milestone, last decision, open TODOs found in docs, recently touched docs. No per-user or session data, and no live repo state (branch, dirty tree, mtimes) in a committed artifact, since those churn or go stale the instant they are written.
3. Hybrid generation, deterministic extractor first. A bundled deterministic scanner is the canonical extractor that produces the committed JSON. The model is demoted to an optional layer that only writes summaries over already-redacted text, and that powers the generic fallback on repos with no known structure. The model never emits canonical structure. This keeps diffs stable and redaction enforceable while preserving flexibility on messy repos.
4. Multi-provider in v1, inventory-first. First-class adapters for Claude Code, Codex, and Cursor; a generic fallback adapter covers everything else and bare repos. Thin per-provider adapters map native conventions into one superset schema. Items keep their native type label (a Cursor rule shows as a Cursor rule, never a fake "skill"). The renderer and schema stay provider-agnostic; sections with no data hide. v1 shows native inventory, paths, links, and relationships, and defers deep workflow interpretation.
5. Lean ambition. Build a trusted inventory and map first. Nail refresh, redaction, stable diffs, links, and provider-native inventory before adding interpretation.

## Architecture

### Components

- Generator: a bundled `python3` script (present on macOS and most Linux, no install). It is the canonical deterministic extractor and the thing that writes the HTML. It lives in the plugin and is never copied into the user's repo.
- Adapters: `claude`, `codex`, `cursor`, and `generic`. Each maps one provider's files into the superset schema.
- Renderer: a bundled HTML template plus classic inline JavaScript (no ES modules, since they fail over `file://`; no CDN). It builds the DOM from the inlined JSON island and provides client-side search.
- Skill (`SKILL.md`): the agent's entry point. The agent runs the generator, optionally adds summaries over redacted text, and re-stamps.
- Plugin: packages the skill, generator, renderer, a `/dashboard` command, and opt-in hook templates. Offline by default.

### Generation pipeline

```text
scan sorted files
  -> adapter extract (allowlisted config fields only)
  -> redact prose and structured values
  -> optional model summaries over redacted text only
  -> schema validate (reject secret-shaped values)
  -> canonical sort and stringify
  -> render static HTML template
  -> inline JSON island
  -> write dashboard.html under the owning provider folder
```

Determinism rules: derived stable IDs of the form `sha256(provider + type + relativePath + heading)[:12]`, repo-relative POSIX paths, sorted collections, and no timestamps, branch names, dirty-tree state, or mtimes in the committed region. `sourceDigest` is a hash of the scanned inputs, so it changes only when source content changes, never on unrelated commits. Two fields need care because they can churn: `vcs.head` is informational and is not written to the committed region (only `vcs.kind` is). `recentDocs` is derived from git history, bounded to the most recent few changed docs, and omitted entirely on non-git repos — never derived from filesystem mtimes. That keeps every committed field content-derived, so a re-stamp with no content change produces no diff.

### Normalized JSON shape (top level)

The JSON ships inlined in the HTML as a `<script type="application/json">` island. The view builds itself from it, and the same island is the client-side search index.

```ts
type DashboardData = {
  schemaVersion: "1.0";
  generator: { name: "ai-control-center"; version: string; rendererDigest: string };
  source: {
    repoName: string;
    dashboardPath: string;       // repo-relative
    sourceDigest: string;        // hash of scanned inputs
    vcs: { kind: "git" | "none"; head?: string };
  };
  providers: ProviderSummary[];  // which adapters fired, and their roots
  project: {
    title: string;
    summary?: string;
    currentMilestone?: Ref;
    lastDecision?: Ref;
    openTodos: Todo[];
    recentDocs: Ref[];
    warnings: Warning[];         // staleness, skipped files, redactions applied
  };
  inventory: {
    agents: Item[]; skills: Item[]; hooks: Item[];
    commands: Item[]; mcpServers: Item[]; rules: Item[];
  };
  docs: { prds: Doc[]; adrs: Doc[]; decisions: Doc[]; workflows: Doc[]; references: Doc[] };
  relationships: Relationship[]; // v1 Map stub: flat, deterministic cross-references
  search: SearchRecord[];
};
```

Every `Item` carries its provider-native type label, a repo-relative source path, and a short redacted summary. `Ref` is a `{ id, title, path }` pointer. The v1 Map is `relationships` — a flat list such as "skill X references command Y" or "agent Z uses MCP `postgres`", derived from cross-references already present in the markdown. The interactive node graph is deferred to v2.

### Adapter interface

```ts
type ProviderAdapter = {
  id: "claude" | "codex" | "cursor" | "generic";
  displayName: string;
  detect(ctx: ScanContext): ProviderRoot[];
  extract(ctx: ScanContext, root: ProviderRoot): ProviderExtract;
  normalize(extract: ProviderExtract): Partial<DashboardData>;
  redactPolicy: RedactPolicy;
};
```

The generic fallback adapter inventories markdown files, headings, front-matter, and folder structure, plus git-derived facts when git is present. It guarantees the dashboard is never empty, which is also how greenfield and brownfield support is met.

### Refresh

Refresh is a first-class workflow, not a caveat. A static `file://` page cannot reliably detect that it is stale, so the design is honest about it.

- Required: an explicit `/dashboard` command from the skill or plugin.
- Default: the agent re-stamps after it edits markdown.
- Optional: an opt-in file-write hook, a git post-commit hook, or a CI check that recomputes `sourceDigest` and flags drift.

The HTML displays its `sourceDigest`, scanned file count, and provider roots, and states "freshness is manual" when no hook is installed.

### Multiple provider folders

One merged dashboard, never parallel copies.

```text
If one dashboard exists, update it.
If none exists, create it under the currently running provider folder.
If multiple dashboards exist, stop and ask which is the owner.
The owner dashboard includes all detected providers.
```

## User interface

Single scrolling page with a sticky jump-nav, chosen for the strongest "repo Confluence" feel and because it needs no routing under `file://`. Section order:

1. Sticky header: title, current milestone, search box, freshness marker (`sourceDigest`, file count, refresh command).
2. Sticky jump-nav: Overview, Inventory, Docs, Map.
3. Overview, rendered as a bento grid: providers detected, inventory counts, current milestone, last decision, open TODOs, recently touched docs.
4. Inventory: grouped lists (Agents, Skills, Commands, Hooks, MCP, Rules). Each row is name, native-type badge, path link, and summary. MCP rows show name and status with auth redacted.
5. Docs: PRDs, ADRs and decisions, workflows, references. Each links out to the raw markdown.
6. Map: the v1 stub relationship list.
7. Footer: freshness notice plus exactly what the generator reads and excludes.

Sections with no data hide. The provider's root markdown links to the dashboard so a human finds it despite the dot-folder location.

## Security

- Redaction at extraction, not after. Two tiers with different guarantees. Structured provider config (MCP servers, settings) is allowlisted: only known-safe fields pass, everything else is dropped, so this tier fails closed. Free-form prose (docs, PRDs, ADRs) is run through a high-precision secret-shaped-string scanner that masks bearer headers, keyword assignments, provider-prefixed keys, and credential URLs; this tier is best-effort by design (it favors precision over recall to avoid mangling normal prose, so high-entropy secrets with no telltale prefix can slip through). Phase 1 ships only the generic prose scanner; the allowlist path is exercised when the provider adapters land. Neither tier emits a value it recognized as secret.
- The dashboard is committed, executable HTML, so it is treated as a stored-XSS surface. The renderer builds text with `textContent` and only injects a sanitized markdown subset (headings, paragraphs, lists, code, links). No raw HTML passthrough from repo content.
- The generator runs offline by default and states what it reads, which matters for public distribution trust.

## Edge cases

- Non-git repos are first-class (`vcs.kind: "none"`); no feature depends on git.
- Root-level `AGENTS.md` is mirrored by link; the dashboard stays under the provider folder.
- Monorepos use scoped roots to avoid an oversized file.
- Scan exclusions: `node_modules`, `.git`, vendored folders, submodules, symlinks, generated docs.
- Size budget: target under 500 KB, warn over 1 MB, switch to summary-only over 2 MB.

## Testing

- Fixture repos for each first-class provider, plus a brownfield fixture and a non-git fixture.
- Determinism test: run the generator twice on a fixture and assert byte-identical output.
- Redaction test: fixtures with realistic MCP config shapes holding fake-but-real-looking secrets; assert nothing leaks into the HTML, JSON island, or search index.
- XSS test: a fixture with hostile markdown (script tags, `onerror` images, raw HTML); assert the rendered output is sanitized.
- Size-budget test: a large fixture; assert the warn and summary-only thresholds behave.

## v1 boundary

In scope: deterministic inventory, doc index, Map stub, project facts, three-tier refresh, redaction, sanitized render, three first-class adapters, generic fallback, the `/dashboard` command, project level only.

Deferred to v2: global cross-repo view at `~/.claude/dashboard.html`, the interactive relationship graph, live git state, smart interpretation of workflows, and auto-installed hooks (shipped as opt-in templates in v1).
