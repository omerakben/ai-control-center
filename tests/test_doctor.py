import json

from acc.cli import main
from acc.doctor import collect_findings, run_doctor
from acc.generate import generate
from tests.builders import make_claude_repo


def _codes(findings):
    return {f.code for f in findings}


def _agent(root, name, desc=""):
    ag = root / ".claude" / "agents"
    ag.mkdir(parents=True, exist_ok=True)
    fm = f"---\nname: {name}\n" + (f"description: {desc}\n" if desc else "") + "---\n# body\n"
    (ag / f"{name}.md").write_text(fm)


def test_doctor_report_is_deterministic_doctor_v1(tmp_path):
    make_claude_repo(tmp_path)
    _, r1 = collect_findings(tmp_path)
    _, r2 = collect_findings(tmp_path)
    assert r1["schemaVersion"] == "doctor.v1"
    assert r1 == r2  # no git/mtime/network -> identical every run


def test_doctor_clean_repo_has_no_warnings(tmp_path):
    _agent(tmp_path, "rev", "Reviews diffs for correctness and style.")
    (tmp_path / "CLAUDE.md").write_text(
        "# Project\n\n" + "Substantial project rules and real guidance here. " * 3)
    generate(tmp_path)  # fresh dashboard -> not stale
    findings, _ = collect_findings(tmp_path)
    assert [f.message for f in findings if f.level == "warn"] == []
    assert run_doctor(tmp_path, strict=True) == 0


def test_doctor_flags_weak_metadata(tmp_path):
    _agent(tmp_path, "nodesc")  # no description
    assert "weak-metadata" in _codes(collect_findings(tmp_path)[0])


def test_doctor_flags_stale_dashboard_after_edit(tmp_path):
    make_claude_repo(tmp_path)
    generate(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# Changed\n\nentirely different content now")
    assert "stale-dashboard" in _codes(collect_findings(tmp_path)[0])


def test_doctor_flags_near_empty_instruction(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# x")  # < 40 chars
    assert "near-empty-instruction" in _codes(collect_findings(tmp_path)[0])


def test_doctor_broken_link_detection_is_conservative(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text(
        "# A\n\nSee [missing](./gone.md), [ok](./b.md), "
        "[site](https://x.test), [mail](mailto:a@b.c), [anchor](#sec).\n")
    (docs / "b.md").write_text("# B")
    findings = collect_findings(tmp_path)[0]
    broken = [f for f in findings if f.code == "broken-link"]
    assert len(broken) == 1                      # only ./gone.md
    assert "gone.md" in broken[0].message
    # external schemes, anchors, and existing targets are never flagged


def test_doctor_strict_exit_codes(tmp_path):
    _agent(tmp_path, "nodesc")  # produces a weak-metadata warning
    assert run_doctor(tmp_path, strict=True) == 1
    assert run_doctor(tmp_path, strict=False) == 0


def test_doctor_json_output_shape(tmp_path, capsys):
    make_claude_repo(tmp_path)
    assert run_doctor(tmp_path, as_json=True) in (0, 1)
    out = json.loads(capsys.readouterr().out)
    assert out["schemaVersion"] == "doctor.v1"
    assert {"root", "dashboardPath", "sourceDigest", "providers", "findings", "status"} <= set(out)
    for f in out["findings"]:
        assert set(f) == {"level", "code", "message"}
        assert f["level"] in ("warn", "info")


def test_cli_backcompat_bare_flags_still_generate(tmp_path):
    make_claude_repo(tmp_path)
    assert main(["--root", str(tmp_path)]) == 0           # leading flag -> generate
    assert (tmp_path / ".claude" / "dashboard.html").exists()


def test_cli_doctor_subcommand_runs(tmp_path):
    make_claude_repo(tmp_path)
    assert main(["doctor", "--root", str(tmp_path)]) in (0, 1)


def test_cli_repo_name_flag_pins_repo_name(tmp_path):
    make_claude_repo(tmp_path)
    assert main(["generate", "--root", str(tmp_path), "--repo-name", "pinned-cli-name"]) == 0
    html = (tmp_path / ".claude" / "dashboard.html").read_text(encoding="utf-8")
    assert '"repoName":"pinned-cli-name"' in html


def test_dashboard_is_branded_agent_context_center(tmp_path):
    make_claude_repo(tmp_path)
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "<title>Agent Context Center</title>" in html
    assert "Generated offline by Agent Context Center (acc)" in html
    assert "no telemetry" in html


def test_doctor_ignores_links_inside_inline_code(tmp_path):
    # `[x](path)` written as inline code is an example of link syntax, not a live link
    (tmp_path / "spec.md").write_text(
        "# Spec\n\nThe link `[x](.claude/agents/x.md)` is an example, not a broken link.\n")
    assert "broken-link" not in {f.code for f in collect_findings(tmp_path)[0]}


def test_doctor_link_target_is_url_decoded(tmp_path):
    # A percent-encoded space and a query string must resolve to the real file,
    # otherwise --strict CI fails on links that are perfectly valid.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# A\n\nSee [spaces](./a%20b.md) and [query](./b.md?v=1).\n")
    (docs / "a b.md").write_text("# spaces")
    (docs / "b.md").write_text("# B")
    assert "broken-link" not in {f.code for f in collect_findings(tmp_path)[0]}


def _two_provider_dashboards(root):
    for d in (".claude", ".codex"):
        (root / d).mkdir(parents=True, exist_ok=True)
        (root / d / "dashboard.html").write_text("<html>")


def test_doctor_without_owner_fails_on_multi_dashboard(tmp_path):
    _two_provider_dashboards(tmp_path)
    assert run_doctor(tmp_path) == 2                          # OwnerAmbiguousError -> exit 2


def test_doctor_owner_disambiguates_multi_dashboard(tmp_path):
    _two_provider_dashboards(tmp_path)
    # --owner gives doctor the same recovery `generate` already has.
    assert run_doctor(tmp_path, owner=".codex") in (0, 1)
    _, report = collect_findings(tmp_path, owner=".codex")
    assert report["dashboardPath"] == ".codex/dashboard.html"


def test_cli_doctor_owner_flag(tmp_path):
    _two_provider_dashboards(tmp_path)
    assert main(["doctor", "--root", str(tmp_path)]) == 2     # ambiguous, no flag
    assert main(["doctor", "--root", str(tmp_path), "--owner", ".codex"]) in (0, 1)


def test_doctor_links_cannot_escape_the_repo_or_crash(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    # Encoded absolute, parent-traversal, and NUL targets must be skipped — never
    # probed outside the repo and never crash doctor. A naive decode-then-stat would
    # flag the escaping paths as broken (leaking them) and raise ValueError on %00.
    (docs / "evil.md").write_text(
        "# Evil\n\n"
        "[abs](%2Fno%2Fsuch%2Fzz.md) "
        "[trav](..%2F..%2F..%2F..%2Fnope-zz.md) "
        "[nul](file%00.md)\n")
    findings = collect_findings(tmp_path)[0]                 # must not raise (NUL guard)
    assert [f for f in findings if f.code == "broken-link"] == []
    assert run_doctor(tmp_path, strict=True) != 2            # no execution-error crash


def test_doctor_validates_in_repo_parent_links(tmp_path):
    # `../` links that stay inside the repo are still resolved and validated, so the
    # escape guard does not blanket-skip legitimate parent-directory references.
    (tmp_path / "top.md").write_text("# Top")
    sub = tmp_path / "docs" / "specs"
    sub.mkdir(parents=True)
    (sub / "x.md").write_text(
        "# X\n\nUp to [top](../../top.md), and [gone](../../missing-zz.md).\n")
    broken = [f for f in collect_findings(tmp_path)[0] if f.code == "broken-link"]
    assert len(broken) == 1                                  # top.md valid; missing-zz.md broken
    assert "missing-zz.md" in broken[0].message


def test_doctor_non_dict_island_is_unreadable_not_a_crash(tmp_path):
    make_claude_repo(tmp_path)
    dash = tmp_path / ".claude" / "dashboard.html"
    dash.parent.mkdir(parents=True, exist_ok=True)
    # A valid-JSON-but-not-object island (a list from a corrupted file) must read
    # as unreadable, never crash collect_findings with an AttributeError.
    dash.write_text(
        '<script id="acc-data" type="application/json">[1, 2, 3]</script>',
        encoding="utf-8")
    assert "unreadable-dashboard" in {f.code for f in collect_findings(tmp_path)[0]}
    assert run_doctor(tmp_path) == 0                          # warn only -> clean exit
