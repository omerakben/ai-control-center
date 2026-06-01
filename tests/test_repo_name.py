"""repoName must be stable across machines.

`source.repoName` used to be `root.name` — the local checkout directory name.
That broke the byte-stable-across-machines guarantee: a repo cloned into `acc`
locally and `ai-control-center` on CI produced different dashboards from
identical content, so the committed dashboard could never satisfy both. These
tests pin repoName to stable repo *content* (an explicit override, then a
project-manifest name), falling back to the directory name only when nothing
better exists.
"""
import json
from acc.generate import _resolve_repo_name, generate_result


def _island(out_path) -> dict:
    html = out_path.read_text(encoding="utf-8")
    raw = html.split('id="acc-data"', 1)[1].split(">", 1)[1].split("</script>", 1)[0]
    return json.loads(raw.replace("<\\/", "</"))


def test_explicit_override_wins_over_everything(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "from-pyproject"\n')
    assert _resolve_repo_name(tmp_path, "explicit") == "explicit"


def test_pyproject_project_name_used_over_directory_name(tmp_path):
    repo = tmp_path / "local-clone-dir"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "canonical-pkg"\n')
    assert _resolve_repo_name(repo) == "canonical-pkg"


def test_package_json_name_used_when_no_pyproject(tmp_path):
    repo = tmp_path / "whatever"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "my-js-pkg", "version": "1.0.0"}')
    assert _resolve_repo_name(repo) == "my-js-pkg"


def test_pyproject_takes_precedence_over_package_json(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "py-name"\n')
    (tmp_path / "package.json").write_text('{"name": "js-name"}')
    assert _resolve_repo_name(tmp_path) == "py-name"


def test_falls_back_to_directory_name_when_no_manifest(tmp_path):
    repo = tmp_path / "plain-repo"
    repo.mkdir()
    assert _resolve_repo_name(repo) == "plain-repo"


def test_nonstring_or_empty_manifest_name_falls_through(tmp_path):
    repo = tmp_path / "dir-name"
    repo.mkdir()
    # malformed: name is a number, and a blank string — neither is a usable name
    (repo / "pyproject.toml").write_text("[project]\nname = 123\n")
    (repo / "package.json").write_text('{"name": "   "}')
    assert _resolve_repo_name(repo) == "dir-name"


def test_repo_name_is_identical_across_differently_named_clones(tmp_path):
    # The actual guarantee: the same content in two differently-named directories
    # yields the same repoName, so a committed dashboard is reproducible on any
    # machine regardless of the clone directory name.
    names = {}
    for clone_dir in ("acc", "ai-control-center"):
        repo = tmp_path / clone_dir
        repo.mkdir()
        (repo / "pyproject.toml").write_text('[project]\nname = "ai-control-center"\n')
        (repo / "README.md").write_text("# Demo\n\nSame content everywhere.\n")
        out = generate_result(repo, out_dir=repo)
        names[clone_dir] = _island(out.path)["source"]["repoName"]
    assert names["acc"] == names["ai-control-center"] == "ai-control-center"


def test_generate_result_honors_repo_name_override(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n")
    out = generate_result(tmp_path, out_dir=tmp_path, repo_name="pinned-name")
    assert _island(out.path)["source"]["repoName"] == "pinned-name"
