from pathlib import Path
from acc.generate import generate, detect_out_dir


def _make_repo(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n\nA demo repo.")
    (tmp_path / "PLAN.md").write_text("- [ ] build the thing\ntoken ghp_0123456789abcdefghij")
    return tmp_path


def test_generate_writes_dashboard(tmp_path):
    out = generate(_make_repo(tmp_path))
    assert out.exists()
    assert out.name == "dashboard.html"
    assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")


def test_generate_is_deterministic(tmp_path):
    _make_repo(tmp_path)
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_generate_redacts_secrets_from_output(tmp_path):
    out = generate(_make_repo(tmp_path))
    assert "ghp_0123456789abcdefghij" not in out.read_text(encoding="utf-8")


def test_generate_escapes_hostile_markdown(tmp_path):
    (tmp_path / "evil.md").write_text("# Evil\n\n<img src=x onerror=alert(1)>")
    out = generate(tmp_path)
    html = out.read_text(encoding="utf-8")
    assert "onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_detect_out_dir_prefers_provider_folder(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert detect_out_dir(tmp_path) == (tmp_path / ".claude").resolve()


def test_detect_out_dir_falls_back(tmp_path):
    assert detect_out_dir(tmp_path) == (tmp_path / ".ai-control-center").resolve()
