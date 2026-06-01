import json
from importlib.resources import files
from pathlib import Path

import acc

REPO = Path(__file__).resolve().parents[1]


def test_templates_are_bundled_as_package_data():
    # templates must live inside the installed `acc` package, not at repo root,
    # so a pip-installed CLI can find them.
    root = files("acc").joinpath("templates")
    for name in ("dashboard.html.tmpl", "styles.css", "app.js"):
        assert root.joinpath(name).is_file(), name


def test_main_module_present():
    # `python3 -m acc` is the documented plugin invocation; needs __main__.py.
    assert (REPO / "src" / "acc" / "__main__.py").is_file()


def test_plugin_manifest_is_valid_and_versioned():
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "agent-context-center"
    # the plugin version is the single source of truth and must track the package
    assert manifest["version"] == acc.__version__
    assert manifest["license"] == "MIT"


def test_marketplace_manifest_lists_the_plugin_at_repo_root():
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert isinstance(market["name"], str) and market["name"]
    assert market["owner"]["name"]
    entries = {p["name"]: p for p in market["plugins"]}
    assert "agent-context-center" in entries
    # one repo is both the marketplace and the single plugin -> source is repo root
    assert entries["agent-context-center"]["source"] == "./"


def test_command_and_skill_are_discoverable():
    assert (REPO / "commands" / "dashboard.md").is_file()
    skill = REPO / "skills" / "agent-context-center" / "SKILL.md"
    assert skill.is_file()
    assert skill.read_text().startswith("---")  # has frontmatter


def test_refresh_hooks_are_opt_in_templates_not_active():
    # a plugin hooks/hooks.json activates on enable; the design ships refresh as
    # opt-in templates instead. Guard that no active hook config exists.
    assert not (REPO / "hooks" / "hooks.json").exists()
    tdir = REPO / "templates" / "refresh"
    for name in ("README.md", "git-post-commit", "claude-file-write-hook.json",
                 "ci-drift-check.yml"):
        assert (tdir / name).is_file(), name
    # the pasteable hook snippet must be valid JSON
    json.loads((tdir / "claude-file-write-hook.json").read_text())
