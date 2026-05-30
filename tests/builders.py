import json
from pathlib import Path


def make_claude_repo(root: Path, *, with_secret: bool = False) -> Path:
    (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code for bugs\n"
        "model: opus\ntools: [Read, Grep]\n---\n\n# Reviewer\n\nReviews diffs."
    )
    (root / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "commands" / "ship.md").write_text(
        "---\ndescription: Ship the release\nargument-hint: <version>\n---\n\nShip it."
    )
    (root / ".claude" / "skills" / "pdf").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "skills" / "pdf" / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Process PDF files\n---\n\n# PDF skill"
    )
    settings = {
        "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
        ]},
        "mcpServers": {"local": {"command": "node", "args": ["server.js"]}},
    }
    (root / ".claude" / "settings.json").write_text(json.dumps(settings))
    mcp = {"mcpServers": {"postgres": {
        "command": "npx", "args": ["-y", "pg-mcp"],
        "env": {"PGPASSWORD": "s3cr3tpassword"},
    }}}
    (root / ".mcp.json").write_text(json.dumps(mcp))
    (root / "CLAUDE.md").write_text("# My Project\n\nProject memory and rules.")
    if with_secret:
        (root / ".claude" / "agents" / "leaky.md").write_text(
            "---\nname: leaky\ndescription: uses token ghp_0123456789abcdefghij\n---\n"
        )
    return root


def make_codex_repo(root: Path) -> Path:
    (root / ".codex").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "config.toml").write_text(
        'model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n'
        'sandbox = "workspace-write"\napproval_policy = "on-request"\n\n'
        '[mcp_servers.context7]\ncommand = "npx"\nargs = ["-y", "@upstash/context7-mcp"]\n'
    )
    (root / ".codex" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "prompts" / "refactor.md").write_text("# Refactor\n\nRefactor steps.")
    (root / "AGENTS.md").write_text("# html-dash\n\nGuide.\n\n- [ ] pick a framework")
    return root


def make_cursor_repo(root: Path) -> Path:
    (root / ".cursor" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".cursor" / "rules" / "style.mdc").write_text(
        '---\ndescription: TypeScript style rules\nglobs: ["*.ts"]\nalwaysApply: true\n---\n\nUse const.'
    )
    (root / ".cursorrules").write_text("Legacy single-file Cursor rules.")
    (root / ".cursor" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"figma": {"url": "https://mcp.figma.com"}}})
    )
    return root


def make_multi_provider_repo(root: Path) -> Path:
    make_claude_repo(root)
    make_codex_repo(root)
    make_cursor_repo(root)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "notes.md").write_text("# Notes\n\nLoose project notes.")
    return root


def make_brownfield_repo(root: Path) -> Path:
    (root / "README.md").write_text("# Brownfield\n\nNo AI provider here.")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "guide.md").write_text("# Guide\n\nSome guide text.")
    return root
