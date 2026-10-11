"""Conservatively select docs-only CI using the complete event diff."""

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlsplit


def docs_only(paths):
    return bool(paths) and all(
        path in {"README.md", "CHANGELOG.md", "LICENSE"}
        or (path.startswith("docs/") and PurePosixPath(path).suffix == ".md"
            and not path.startswith(("docs/plans/", "docs/qa/", "docs/superpowers/"))
            and path not in {"docs/PROJECT_STATUS.md", "docs/README_SCREENSHOT_AUDIT.md"})
        for path in paths
    )


def event_range(event_name, event):
    if event_name == "pull_request":
        pr = event["pull_request"]
        return pr["base"]["sha"] + "..." + pr["head"]["sha"]
    if event_name == "push" and event.get("before", "").strip("0"):
        return event["before"] + ".." + event["after"]
    return None  # Manual runs and unknown/new-branch events always run everything.


def inline_link_targets(text):
    """Read inline destinations, including balanced/escaped parentheses and <...>."""
    for match in re.finditer(r"\]\(\s*", text):
        start = index = match.end()
        if index >= len(text):
            continue
        angle = text[index] == "<"
        if angle:
            start = index = index + 1
        depth = 0
        while index < len(text):
            char = text[index]
            if char == "\\" and index + 1 < len(text):
                index += 2
                continue
            if angle:
                if char == ">":
                    break
            elif char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            elif char.isspace():
                break
            index += 1
        if index == len(text) or depth:
            continue
        suffix = text[index + 1:] if angle else text[index:]
        # A destination must end the link, optionally followed by a title.
        if re.match(r'''\s*(?:"[^"\n]*"|'[^'\n]*'|\([^\n]*?\))?\s*\)''', suffix):
            yield re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])", r"\1", text[start:index])


def check_documents(root, paths):
    for name in paths:
        path = root / name
        if not path.exists():
            continue  # Deleted documentation is allowed.
        text = path.read_text(encoding="utf-8")
        if "\0" in text:
            raise ValueError(f"Unexpected binary content: {name}")
        # Check ordinary inline local links, not remote URLs or heading anchors.
        text = re.sub(r"```.*?```|~~~.*?~~~", "", text, flags=re.S)
        text = re.sub(r"(`+).*?\1", "", text, flags=re.S)
        for target in inline_link_targets(text):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
                continue
            if not (path.parent / unquote(url.path)).exists():
                raise ValueError(f"Missing local link in {name}: {target}")


def main():
    root = Path(__file__).resolve().parents[1]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    revision_range = event_range(os.environ["GITHUB_EVENT_NAME"], event)
    full = True
    if revision_range:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--no-renames", "-z", revision_range, "--"],
                cwd=root, check=True, capture_output=True,
            )
            paths = [path for path in result.stdout.decode("utf-8").split("\0") if path]
        except (subprocess.CalledProcessError, UnicodeError):
            print("Could not classify the complete diff; running full CI.")
        else:
            full = not docs_only(paths)
            if not full:
                # Ignored paths can occur inside docs too (for example backups/).
                # Force the full suite, including repository hygiene, in that case.
                ignored = subprocess.run(
                    ["git", "check-ignore", "--no-index", "-z", "--stdin"],
                    input=result.stdout, cwd=root, capture_output=True,
                )
                full = ignored.returncode != 1
            if not full:
                subprocess.run(["git", "diff", "--check", revision_range, "--"], cwd=root, check=True)
                check_documents(root, paths)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"full={str(full).lower()}\n")
    print("Full CI required." if full else "Documentation checks passed; runtime jobs are skipped.")


if __name__ == "__main__":
    main()
