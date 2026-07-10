from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_windows_runtime_setup_is_local_and_never_installs_python():
    path = ROOT / "scripts" / "setup-runtime.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    assert "Set-StrictMode -Version Latest" in script
    assert "sys.version_info >= (3, 10)" in script
    assert 'Join-Path $AppRoot ".venv\\Scripts\\python.exe"' in script
    assert "-m venv" in script
    assert "-m pip install" in script
    assert "import backend.main, uvicorn" in script
    assert "image-prompt-library-runtime-probe-" in script
    assert "IMAGE_PROMPT_LIBRARY_PATH" in script
    assert "https://www.python.org/downloads/windows/" in script
    assert not re.search(r"(?i)winget\s+install", script)
    assert "npm" not in script.lower()
    assert "node" not in script.lower()
    assert "Start-Process" not in script
