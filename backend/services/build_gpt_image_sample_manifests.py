from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.services.import_gpt_image_2_skill import SOURCE_LICENSE, SOURCE_NAME, load_full_gallery_records

COLLECTIONS = [
    {"id": "cinematic-storytelling", "names": {"en": "Cinematic Storytelling", "zh_hans": "电影叙事", "zh_hant": "電影敘事"}},
    {"id": "characters-anime", "names": {"en": "Characters & Anime", "zh_hans": "角色与动漫", "zh_hant": "角色與動畫"}},
    {"id": "art-illustration", "names": {"en": "Art & Illustration", "zh_hans": "艺术与插画", "zh_hant": "藝術與插畫"}},
    {"id": "design-typography", "names": {"en": "Design, Posters & Typography", "zh_hans": "设计、海报与字体", "zh_hant": "設計、海報與字體"}},
    {"id": "education-infographics", "names": {"en": "Education & Infographics", "zh_hans": "教育与信息图", "zh_hant": "教育與資訊圖表"}},
    {"id": "technical-research", "names": {"en": "Technical & Research Diagrams", "zh_hans": "技术与研究图解", "zh_hant": "技術與研究圖解"}},
    {"id": "ui-brand-product", "names": {"en": "UI, Brand & Product", "zh_hans": "界面、品牌与产品", "zh_hant": "介面、品牌與產品"}},
    {"id": "fashion-lifestyle", "names": {"en": "Fashion, Beauty & Lifestyle", "zh_hans": "时尚、美容与生活风格", "zh_hant": "時尚、美容與生活風格"}},
    {"id": "architecture-interiors", "names": {"en": "Architecture & Interiors", "zh_hans": "建筑与室内", "zh_hant": "建築與室內"}},
    {"id": "photo-real-world", "names": {"en": "Photography & Real-world Screens", "zh_hans": "摄影与真实屏幕", "zh_hant": "攝影與真實屏幕"}},
]


def collection_for(record: dict[str, Any]) -> str:
    category = f"{record.get('category', '')} {record.get('title', '')}".lower()
    if any(token in category for token in ["research", "data visualization", "technical", "scientific", "field guide"]):
        return "technical-research" if "research" in category or "technical" in category or "data visualization" in category else "education-infographics"
    if any(token in category for token in ["infographic", "educational"]):
        return "education-infographics"
    if any(token in category for token in ["typography", "poster", "tattoo", "brand systems", "identity"]):
        return "design-typography"
    if any(token in category for token in ["anime", "manga", "character", "gaming", "pixel art"]):
        return "characters-anime"
    if any(token in category for token in ["cinematic", "film", "animation", "retro", "cyberpunk", "event", "experience"]):
        return "cinematic-storytelling"
    if any(token in category for token in ["ui/ux", "product", "food", "brand"]):
        return "ui-brand-product"
    if any(token in category for token in ["fashion", "beauty", "lifestyle"]):
        return "fashion-lifestyle"
    if any(token in category for token in ["architecture", "interior", "isometric"]):
        return "architecture-interiors"
    if any(token in category for token in ["photography", "screen", "openai cookbook", "edit endpoint"]):
        return "photo-real-world"
    return "art-illustration"


def prompts_for(record: dict[str, Any], language: str) -> list[dict[str, Any]]:
    en = record.get("prompt_en")
    zh_hans = record.get("prompt_zh_hans")
    zh_hant = record.get("prompt_zh_hant")
    if language == "en":
        return [{"language": "en", "text": en, "is_primary": True}] if en else []
    if language == "zh_hans" and zh_hans:
        return [{"language": "zh_hans", "text": zh_hans, "is_primary": True}]
    if language == "zh_hant" and zh_hant:
        return [{"language": "zh_hant", "text": zh_hant, "is_primary": True}]
    return [{"language": "en", "text": en, "is_primary": True}] if en else []


def build_manifest(source_root: Path, language: str) -> dict[str, Any]:
    records = load_full_gallery_records(source_root)
    collection_lookup = {collection["id"]: collection for collection in COLLECTIONS}
    manifest_collections = [
        {"id": collection["id"], "name": collection["names"][language], "names": collection["names"]}
        for collection in COLLECTIONS
    ]
    items = []
    for record in records:
        collection_id = collection_for(record)
        items.append(
            {
                "id": record["id"],
                "number": record["number"],
                "title": record["title"],
                "slug": f"sample-gpt-image-2-skill-{record['id']}-{language.replace('_', '-')}",
                "collection_id": collection_id,
                "collection_name": collection_lookup[collection_id]["names"][language],
                "image": record["file"],
                "source_file": record["file"],
                "source_title": record["source_title"],
                "source_name": SOURCE_NAME,
                "source_url": record["source_url"],
                "author": SOURCE_NAME,
                "license": SOURCE_LICENSE,
                "model": "GPT Image 2 sample",
                "tags": ["sample", "gpt_image_2_skill", "full_catalog", collection_id],
                "prompts": prompts_for(record, language),
            }
        )
    return {
        "schema_version": 1,
        "id": f"gpt-image-2-skill-v1-{language}",
        "language": language,
        "title": f"GPT Image 2 Skill sample data ({language})",
        "source": {
            "name": SOURCE_NAME,
            "url": "https://github.com/wuyoscar/gpt_image_2_skill",
            "commit": None,
            "license": SOURCE_LICENSE,
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "note": "Prompt patterns are curated from ZeroLu/awesome-gpt-image under CC BY 4.0; individual attributions are preserved in upstream entries where present.",
        },
        "collections": manifest_collections,
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal builder for curated GPT Image 2 sample-data manifests.")
    parser.add_argument("--source", required=True, help="Path to local wuyoscar/gpt_image_2_skill clone")
    parser.add_argument("--out", default="sample-data/manifests", help="Manifest output directory")
    parser.add_argument("--commit", default=None, help="Source commit hash to record in manifests")
    args = parser.parse_args()
    source_root = Path(args.source).resolve()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for language in ("en", "zh_hans", "zh_hant"):
        manifest = build_manifest(source_root, language)
        if args.commit:
            manifest["source"]["commit"] = args.commit
        path = out_dir / f"{language}.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}: {len(manifest['items'])} items, {len(manifest['collections'])} collections")


if __name__ == "__main__":
    main()
