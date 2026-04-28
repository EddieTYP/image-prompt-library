from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

try:
    from deep_translator import GoogleTranslator
except ImportError as exc:  # pragma: no cover - optional curation dependency
    raise SystemExit(
        "Missing optional curation dependency: deep-translator. "
        "Install it with `python -m pip install deep-translator` before running this script."
    ) from exc

try:
    from opencc import OpenCC
except ImportError as exc:  # pragma: no cover - optional curation dependency
    raise SystemExit(
        "Missing optional curation dependency: opencc. "
        "Install it with `python -m pip install opencc-python-reimplemented` before running this script."
    ) from exc

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / ".local-work" / "prompt_translation_cache.json"
MAX_CHARS = 3600
GPT_IMAGE_MANIFESTS = [
    "sample-data/manifests/en.json",
    "sample-data/manifests/zh_hans.json",
    "sample-data/manifests/zh_hant.json",
]
AWESOME_MANIFEST = "sample-data/manifests/awesome-gpt-image-2/zh_hant.json"
GOOGLE_METHOD = "google-translate-via-deep-translator"
OPENCC_METHOD = "opencc-s2twp-after-google-translate"


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def split_text(text: str) -> list[str]:
    parts = re.split(r"(\n\s*\n)", text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= MAX_CHARS:
            current += part
            continue
        if current.strip():
            chunks.append(current)
        if len(part) <= MAX_CHARS:
            current = part
            continue
        sentences = re.split(r"(?<=[.!?。！？])\s+", part)
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= MAX_CHARS:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
    if current.strip():
        chunks.append(current)
    return chunks


def translate(text: str, source: str, target: str, cache: dict[str, str]) -> str:
    key = f"{source}:{target}:{text}"
    if key in cache:
        return cache[key]
    translator = GoogleTranslator(source=source, target=target)
    out_parts: list[str] = []
    for chunk in split_text(text):
        for attempt in range(5):
            try:
                out_parts.append(translator.translate(chunk))
                time.sleep(0.25)
                break
            except Exception as exc:  # pragma: no cover - network/service failure path
                if attempt == 4:
                    raise RuntimeError(f"translate failed {source}->{target}: {exc}\nChunk: {chunk[:300]}") from exc
                time.sleep(1.5 * (attempt + 1))
    result = "".join(out_parts).strip()
    cache[key] = result
    save_cache(cache)
    return result


def prompt_map(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {prompt["language"]: prompt for prompt in item.get("prompts", [])}


def append_prompt(item: dict[str, Any], language: str, text: str, source_language: str, method: str) -> None:
    item.setdefault("prompts", []).append(
        {
            "language": language,
            "text": text,
            "is_primary": False,
            "is_original": False,
            "provenance": {
                "kind": "conversion" if method.startswith("opencc") else "translation",
                "source_language": source_language,
                "derived_from": source_language,
                "method": method,
            },
        }
    )


def fill_gpt_image_manifests(cache: dict[str, str]) -> int:
    changed = 0
    s2t = OpenCC("s2twp").convert
    for rel in GPT_IMAGE_MANIFESTS:
        path = ROOT / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data["items"]:
            prompts = prompt_map(item)
            en = prompts.get("en", {}).get("text")
            if not en or {"zh_hans", "zh_hant"} <= set(prompts):
                continue
            zh_hans = prompts.get("zh_hans", {}).get("text") or translate(en, "en", "zh-CN", cache)
            zh_hant = prompts.get("zh_hant", {}).get("text") or s2t(zh_hans)
            if "zh_hant" not in prompts:
                append_prompt(item, "zh_hant", zh_hant, "en", OPENCC_METHOD if "zh_hans" not in prompts else GOOGLE_METHOD)
                changed += 1
            if "zh_hans" not in prompts:
                append_prompt(item, "zh_hans", zh_hans, "en", GOOGLE_METHOD)
                changed += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def fill_awesome_manifest(cache: dict[str, str]) -> int:
    changed = 0
    path = ROOT / AWESOME_MANIFEST
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data["items"]:
        prompts = prompt_map(item)
        if "en" in prompts:
            continue
        source_text = prompts.get("zh_hans", prompts.get("zh_hant", {})).get("text")
        if not source_text:
            continue
        en = translate(source_text, "zh-CN", "en", cache)
        append_prompt(item, "en", en, "zh_hans", GOOGLE_METHOD)
        changed += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    cache = load_cache()
    changed = fill_gpt_image_manifests(cache) + fill_awesome_manifest(cache)
    print(f"changed prompt records: {changed}")


if __name__ == "__main__":
    main()
