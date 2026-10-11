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
    (["docs/plans/private.md"], False),
    (["docs/qa/private.md"], False),
    (["docs/superpowers/private.md"], False),
    (["docs/PROJECT_STATUS.md"], False),
    (["docs/README_SCREENSHOT_AUDIT.md"], False),
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


@pytest.mark.parametrize("destination", [
    "guide(v2).md",
    "guide(v(2)).md",
    r"guide\(v2\).md",
    "<guide(v2).md>",
    "<guide (v2).md>",
    'guide(v2).md "Guide title"',
    "guide(v2).md 'Guide title'",
    "guide(v2).md (Guide title)",
    "guide%28v2%29.md#heading",
])
def test_document_links_with_parentheses(tmp_path, destination):
    from urllib.parse import unquote, urlsplit
    text = f"[guide]({destination})"
    targets = list(scope.inline_link_targets(text))
    assert len(targets) == 1
    filename = unquote(urlsplit(targets[0]).path)
    assert filename in {"guide(v2).md", "guide(v(2)).md", "guide (v2).md"}
    (tmp_path / filename).write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    scope.check_documents(tmp_path, ["README.md"])
    # Missing targets must still fail, even with balanced parentheses.
    (tmp_path / "README.md").write_text("[missing](missing(v2).md)", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing local link"):
        scope.check_documents(tmp_path, ["README.md"])


def test_link_examples_in_code_are_not_checked(tmp_path):
    (tmp_path / "README.md").write_text(
        '`[inline](missing(v2).md)`\n```md\n[example](missing.md)\n```\n', encoding="utf-8",
    )
    scope.check_documents(tmp_path, ["README.md"])


def test_ci_preserves_runtime_checks_and_only_cancels_obsolete_pr_runs():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("needs: changes") == 3
    assert workflow.count("if: needs.changes.outputs.full == 'true'") == 3
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "github.event.pull_request.number || github.run_id" in workflow
    assert "github.ref" not in workflow
    assert "paths-ignore:" not in workflow
    assert "paths:" not in workflow


@pytest.mark.parametrize("changed,expected", [
    (b"docs/releases/unreleased.md\0", "false"),
    (b"docs/releases/unreleased.md\0backend/main.py\0", "true"),
    (b"docs/plans/private.md\0", "true"),
    (b"docs/qa/private.md\0", "true"),
    (b"docs/superpowers/private.md\0", "true"),
    (b"docs/PROJECT_STATUS.md\0", "true"),
    (b"docs/README_SCREENSHOT_AUDIT.md\0", "true"),
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
        if "check-ignore" in command:
            return subprocess.CompletedProcess(command, 1, stdout=b"")
        return subprocess.CompletedProcess(command, 0, stdout=changed)

    monkeypatch.setattr(scope.subprocess, "run", run)
    scope.main()
    assert output.read_text(encoding="utf-8") == f"full={expected}\n"
    assert "--no-renames" in commands[0]
    assert "a...b" in commands[0]
    assert len(commands) == (3 if expected == "false" else 1)


@pytest.mark.parametrize("ignore_status", [0, 2])
def test_ignored_docs_or_failed_ignore_check_require_full_ci(tmp_path, monkeypatch, ignore_status):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": "a", "after": "b"}), encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def run(command, **kwargs):
        if "check-ignore" in command:
            assert kwargs["input"] == b"docs/backups/private.md\0"
            return subprocess.CompletedProcess(command, ignore_status, stdout=b"docs/backups/private.md\0")
        return subprocess.CompletedProcess(command, 0, stdout=b"docs/backups/private.md\0")

    monkeypatch.setattr(scope.subprocess, "run", run)
    scope.main()
    assert output.read_text(encoding="utf-8") == "full=true\n"


def test_failed_document_check_does_not_report_success(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": "a", "after": "b"}), encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(scope.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 1 if "check-ignore" in command else 0, stdout=b"README.md\0"))

    def fail(*args):
        raise ValueError("broken documentation")

    monkeypatch.setattr(scope, "check_documents", fail)
    with pytest.raises(ValueError, match="broken documentation"):
        scope.main()
    assert not output.exists()
