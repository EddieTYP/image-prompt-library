import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_scope", ROOT / "scripts" / "ci-scope.py")
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


@pytest.mark.parametrize("paths,expected", [
    (["docs/releases/v0.11.3.md"], True),
    (["README.md", "docs/GENERATION.md", "LICENSE"], True),
    (["docs/nested/notes.md", "backend/config.py"], False),
    ([".github/workflows/ci.yml"], False),
    (["scripts/install.ps1"], False),
    (["package-lock.json"], False),
    (["docs/script.py"], False),
    (["docs/image.png"], False),
    (["unknown.md"], False),
    ([], False),
    # --no-renames exposes both paths, so a code-to-doc rename cannot skip tests.
    (["backend/old.py", "docs/new.md"], False),
])
def test_docs_allowlist_is_conservative(paths, expected):
    assert scope.docs_only(paths) is expected


def test_event_ranges_cover_whole_pr_and_push():
    assert scope.event_range("pull_request", {"pull_request": {"base": {"sha": "a"}, "head": {"sha": "b"}}}) == "a...b"
    assert scope.event_range("push", {"before": "a", "after": "b"}) == "a..b"
    assert scope.event_range("push", {"before": "0" * 40, "after": "b"}) is None
    assert scope.event_range("workflow_dispatch", {}) is None
    assert scope.event_range("unknown", {}) is None


def test_document_checks_local_links_and_allows_deletions(tmp_path):
    (tmp_path / "target.md").write_text("# Target\n", encoding="utf-8")
    doc = tmp_path / "README.md"
    doc.write_text("[local](target.md#heading) [remote](https://example.com) [anchor](#here)\n", encoding="utf-8")
    scope.check_documents(tmp_path, ["README.md", "deleted.md"])
    doc.write_text("[missing](missing.md)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing local link"):
        scope.check_documents(tmp_path, ["README.md"])


def test_ci_preserves_runtime_checks_and_only_cancels_obsolete_pr_runs():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("needs: changes") == 3
    assert workflow.count("if: needs.changes.outputs.full == 'true'") == 3
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "github.event.pull_request.number || github.ref" in workflow
    assert "paths-ignore:" not in workflow
    assert "paths:" not in workflow


@pytest.mark.parametrize("changed,expected", [
    (b"docs/releases/unreleased.md\0", "false"),
    (b"docs/releases/unreleased.md\0backend/main.py\0", "true"),
    (b"", "true"),
    (None, "true"),
])
def test_scope_outputs_and_fallback(tmp_path, monkeypatch, changed, expected):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"base": {"sha": "a"}, "head": {"sha": "b"}}}), encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if changed is None:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, stdout=changed)

    monkeypatch.setattr(scope.subprocess, "run", run)
    scope.main()
    assert output.read_text(encoding="utf-8") == f"full={expected}\n"
    assert "--no-renames" in commands[0]
    assert "a...b" in commands[0]
    assert len(commands) == (2 if expected == "false" else 1)


def test_failed_document_check_does_not_report_success(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": "a", "after": "b"}), encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(scope.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 0, stdout=b"README.md\0"))

    def fail(*args):
        raise ValueError("broken documentation")

    monkeypatch.setattr(scope, "check_documents", fail)
    with pytest.raises(ValueError, match="broken documentation"):
        scope.main()
    assert not output.exists()
