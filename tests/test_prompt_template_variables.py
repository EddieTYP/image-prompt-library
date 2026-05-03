import json
import subprocess
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import resolve_hidden_features
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def run_ts_expression(expression: str) -> str:
    script = textwrap.dedent(
        f"""
        import {{ extractPromptTemplateVariables }} from './frontend/src/utils/promptTemplateVariables.ts';
        const result = {expression};
        console.log(JSON.stringify(result));
        """
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_camelot_percival_feature_flag_defaults_off(monkeypatch, tmp_path):
    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_CAMELOT_PERCIVAL", raising=False)
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "missing-config.json"))

    assert resolve_hidden_features()["camelot"]["percival"] is False

    client = TestClient(create_app(tmp_path / "library"))
    config = client.get("/api/config").json()
    assert config["features"]["camelot"]["percival"] is False


def test_camelot_percival_feature_flag_can_be_enabled_from_local_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"camelot": {"percival": True}}), encoding="utf-8")
    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_CAMELOT_PERCIVAL", raising=False)
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(config_path))

    assert resolve_hidden_features()["camelot"]["percival"] is True


def test_camelot_percival_feature_flag_can_be_enabled_from_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"camelot": {"percival": False}}), encoding="utf-8")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CAMELOT_PERCIVAL", "true")

    assert resolve_hidden_features()["camelot"]["percival"] is True


def test_extract_prompt_template_variables_supports_braces_dedupe_chinese_and_whitespace():
    output = run_ts_expression(
        "extractPromptTemplateVariables('A {{ subject }} in {{style-name}} and {{主體}} then {{subject}} again')"
    )

    assert json.loads(output) == ["subject", "style-name", "主體"]


def test_extract_prompt_template_variables_ignores_escaped_empty_and_malformed_placeholders():
    output = run_ts_expression(
        r"extractPromptTemplateVariables('Literal \\{{subject}}, empty {{   }}, malformed {{a{{b}}}, valid {{style_name}}')"
    )

    assert json.loads(output) == ["style_name"]


def test_resolve_prompt_template_variables_substitutes_values_and_preserves_escaped_literals():
    script = textwrap.dedent(
        r"""
        import { resolvePromptTemplate } from './frontend/src/utils/promptTemplateVariables.ts';
        const result = resolvePromptTemplate(String.raw`A \{{literal}} of {{ subject }} in {{風格}} and {{missing}}`, { subject: 'red panda', '風格': 'ink wash' });
        console.log(JSON.stringify(result));
        """
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(result.stdout) == "A {{literal}} of red panda in ink wash and "
