from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SOURCE_NAME = "freestylefly/awesome-gpt-image-2"
SOURCE_URL = "https://github.com/freestylefly/awesome-gpt-image-2"
SOURCE_LICENSE = "MIT"

COLLECTIONS = [
    {"id": "ui-interface", "names": {"en": "UI & Interface", "zh_hans": "UI与界面", "zh_hant": "UI 與介面"}},
    {"id": "charts-infographics", "names": {"en": "Charts & Infographics", "zh_hans": "图表与信息可视化", "zh_hant": "圖表與資訊視覺化"}},
    {"id": "poster-typography", "names": {"en": "Posters & Typography", "zh_hans": "海报与排版", "zh_hant": "海報與排版"}},
    {"id": "product-ecommerce", "names": {"en": "Product & E-commerce", "zh_hans": "商品与电商", "zh_hant": "商品與電商"}},
    {"id": "brand-logo", "names": {"en": "Brand & Logo", "zh_hans": "品牌与标志", "zh_hant": "品牌與標誌"}},
    {"id": "architecture-space", "names": {"en": "Architecture & Space", "zh_hans": "建筑与空间", "zh_hant": "建築與空間"}},
    {"id": "photography-realism", "names": {"en": "Photography & Realism", "zh_hans": "摄影与写实", "zh_hant": "攝影與寫實"}},
    {"id": "illustration-art", "names": {"en": "Illustration & Art", "zh_hans": "插画与艺术", "zh_hant": "插畫與藝術"}},
    {"id": "characters-portraits", "names": {"en": "Characters & Portraits", "zh_hans": "人物与角色", "zh_hant": "人物與角色"}},
    {"id": "scenes-storytelling", "names": {"en": "Scenes & Storytelling", "zh_hans": "场景与叙事", "zh_hant": "場景與敘事"}},
    {"id": "historical-chinese", "names": {"en": "Historical & Chinese Style", "zh_hans": "历史与古风题材", "zh_hant": "歷史與古風題材"}},
    {"id": "documents-publishing", "names": {"en": "Documents & Publishing", "zh_hans": "文档与出版物", "zh_hant": "文件與出版物"}},
    {"id": "workflow-templates", "names": {"en": "Workflow Templates", "zh_hans": "工作流模板", "zh_hant": "工作流程模板"}},
]

COLLECTION_KEYWORDS = [
    ("ui-interface", ["user interface", "界面", "介面", "app", "应用", "應用", "交互", "互動", "dashboard", "截图", "截圖", "web", "mobile", "figma", "社媒", "小红书", "小紅書", "tweet", "twitter"]),
    ("charts-infographics", ["信息图", "資訊圖", "infographic", "图表", "圖表", "可视化", "視覺化", "数据", "數據", "diagram", "atlas", "matrix", "矩阵", "矩陣", "学习表", "學習表", "技术详解", "技術詳解", "rag"]),
    ("poster-typography", ["海报", "海報", "poster", "typography", "排版", "字体", "字體", "宣传", "宣傳", "campaign", "封面", "主视觉", "主視覺", "title", "logo text"]),
    ("product-ecommerce", ["商品", "产品", "產品", "电商", "電商", "包装", "包裝", "零食", "饮料", "飲料", "电商", "e-commerce", "product", "packaging", "mockup", "advertisement"]),
    ("brand-logo", ["品牌", "标志", "標誌", "logo", "identity", "视觉识别", "視覺識別", "brand"]),
    ("architecture-space", ["建筑", "建築", "空间", "空間", "interior", "室内", "室內", "house", "building", "city", "城市", "街区", "街區", "isometric"]),
    ("photography-realism", ["摄影", "攝影", "写真", "寫真", "realistic", "photo", "photography", "portrait", "街拍", "镜头", "鏡頭", "cinematic", "film still"]),
    ("characters-portraits", ["人物", "角色", "肖像", "portrait", "美女", "女子", "女孩", "男孩", "model", "character", "avatar", "卡牌", "圣斗士", "聖鬥士"]),
    ("historical-chinese", ["古风", "古風", "国风", "國風", "汉服", "漢服", "襦裙", "赤壁", "诗", "詩", "中式", "宋", "唐", "水墨"]),
    ("scenes-storytelling", ["场景", "場景", "叙事", "敘事", "故事", "电影", "電影", "动画", "動畫", "fictional", "scene", "story", "romantic", "星舰", "星艦"]),
    ("documents-publishing", ["文档", "文件", "出版", "书籍", "書籍", "白皮书", "白皮書", "报告", "報告", "paper", "document", "book", "杂志", "雜誌", "处方", "處方"]),
    ("workflow-templates", ["schema", "json", "模板", "template", "workflow", "argument", "prompt-as-code", "参数", "參數", "变量", "變數", "reference sheet", "analysis sheet"]),
    ("illustration-art", ["插画", "插畫", "illustration", "艺术", "藝術", "art", "水彩", "手绘", "手繪", "刺绣", "刺繡", "像素", "pixel", "漫画", "漫畫"]),
]

TAG_RULES = [
    ("bilingual_prompt", ["[english]", "[中文]", "english]"]),
    ("x_source", ["x.com", "twitter"]),
    ("xiaohongshu_source", ["小红书", "小紅書"]),
    ("prompt_as_code", ["[core task]", "schema", "json", "argument name=", "prompt-as-code"]),
    ("infographic", ["信息图", "資訊圖", "infographic", "diagram", "图表", "圖表"]),
    ("poster", ["海报", "海報", "poster"]),
    ("ui_mockup", ["ui", "界面", "介面", "app", "dashboard", "截图", "截圖"]),
    ("product_design", ["产品", "產品", "商品", "包装", "包裝", "product", "packaging"]),
    ("brand_design", ["品牌", "logo", "brand", "identity"]),
    ("photoreal", ["写实", "寫實", "realistic", "photo", "photography"]),
    ("illustration", ["插画", "插畫", "illustration", "art"]),
    ("chinese_style", ["国风", "國風", "古风", "古風", "汉服", "漢服", "水墨", "中式"]),
    ("character", ["角色", "人物", "肖像", "character", "portrait"]),
    ("sports", ["足球", "运动", "運動", "sports", "tennis", "football"]),
]


def _converter():
    try:
        from opencc import OpenCC  # type: ignore

        return OpenCC("s2twp").convert
    except Exception:
        table = str.maketrans({
            "与": "與", "图": "圖", "报": "報", "设": "設", "计": "計", "画": "畫", "简": "簡", "洁": "潔",
            "创": "創", "视": "視", "觉": "覺", "化": "化", "数": "數", "据": "據", "场": "場", "叙": "敘",
            "题": "題", "风": "風", "体": "體", "应": "應", "用": "用", "产": "產", "品": "品", "标": "標",
            "志": "誌", "筑": "築", "摄": "攝", "实": "實", "插": "插", "艺": "藝", "术": "術", "历": "歷",
            "档": "檔", "书": "書", "现": "現", "层": "層", "级": "級", "术": "術", "发": "發", "转": "轉",
        })
        return lambda text: text.translate(table)


_to_hant = _converter()


def _simplified_converter():
    try:
        from opencc import OpenCC  # type: ignore

        return OpenCC("t2s").convert
    except Exception:
        return lambda text: text


_to_hans = _simplified_converter()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\\_", "_").strip()
    return text or None


def parse_markdown_link(value: str | None) -> tuple[str | None, str | None]:
    """Return a concise label and URL from markdown links such as [@name](https://...)."""
    if not value:
        return None, None
    text = value.strip().replace("\\[", "[").replace("\\]", "]")
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)\s>]+|<https?://[^)>]+>)\)", text)
    if links:
        labels = " / ".join(clean_text(label) or label for label, _url in links)
        return clean_text(labels), clean_text(links[0][1].strip("<>"))
    bare_url = re.search(r"https?://[^\s>)]+", text)
    label = re.sub(r"\([^)]*https?://[^)]*\)", "", text)
    label = re.sub(r"[\[\]\\()<>]", "", label).strip() or None
    return clean_text(label), clean_text(bare_url.group(0)) if bare_url else None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def parse_gallery(source_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for part in (1, 2):
        path = source_root / "docs" / f"gallery-part-{part}.md"
        text = path.read_text(encoding="utf-8")
        headings = list(re.finditer(r"^###\s+例\s*(\d+)[:：](.+)$", text, re.M))
        for index, heading in enumerate(headings):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            block = text[start:end]
            number = int(heading.group(1))
            title = clean_text(heading.group(2)) or f"例 {number}"
            image_match = re.search(r"!\[(.*?)\]\((\.\./data/images/[^)]+)\)", block, re.S)
            source_match = re.search(r"\*\*来源[:：]\*\*\s*(.+)", block)
            prompt_match = re.search(r"\*\*提示词[:：]\*\*\s*\n+```(?:text)?\s*\n(.*?)(?:\n```|\n``\s*\n|\n\*\*\*|\Z)", block, re.S)
            fallback_prompt_match = re.search(r"\*\*提示词[:：]\*\*\s*(.*?)(?:\n\*\*\*|\Z)", block, re.S)
            prompt = clean_text(prompt_match.group(1) if prompt_match else (fallback_prompt_match.group(1) if fallback_prompt_match else None))
            if not prompt:
                continue
            image_path = clean_text(image_match.group(2) if image_match else None)
            source_label, linked_source_url = parse_markdown_link(clean_text(source_match.group(1)) if source_match else None)
            records.append({
                "number": number,
                "id": f"case-{number:03d}",
                "title": _to_hant(title),
                "image_alt": _to_hant(clean_text(image_match.group(1)) or title) if image_match else _to_hant(title),
                "image": image_path.replace("../data/", "") if image_path else f"images/case{number}.jpg",
                "source": source_label or "未提供",
                "prompt_source": prompt,
                "prompt_zh_hant": _to_hant(prompt),
                "part": part,
                "source_url": linked_source_url or f"{SOURCE_URL}/blob/main/docs/gallery-part-{part}.md#case-{number}",
                "source_file_url": f"{SOURCE_URL}/blob/main/docs/gallery-part-{part}.md#case-{number}",
            })
    return records


def split_english_prompt(prompt: str) -> str | None:
    match = re.search(r"\[English\]\s*(.+?)(?:\n\[[^\]]+\]|\Z)", prompt, re.S | re.I)
    if match:
        text = clean_text(match.group(1))
        return text
    # Keep purely/mostly English prompt available in English tab too.
    latin = sum(1 for ch in prompt if "a" <= ch.lower() <= "z")
    cjk = sum(1 for ch in prompt if "\u4e00" <= ch <= "\u9fff")
    return prompt if latin > 40 and latin > cjk * 2 else None


def keyword_in(haystack: str, keyword: str) -> bool:
    keyword_lower = keyword.lower()
    # Latin short keywords like "app" and "web" should not match inside
    # unrelated words such as "appears" or "jewelry".
    if re.fullmatch(r"[a-z0-9][a-z0-9 -]{0,4}", keyword_lower):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword_lower)}(?![a-z0-9])", haystack) is not None
    return keyword_lower in haystack


def collection_for(record: dict[str, Any]) -> str:
    haystack = f"{record['title']} {record['image_alt']} {record['prompt_zh_hant']}".lower()
    for collection_id, keywords in COLLECTION_KEYWORDS:
        if any(keyword_in(haystack, keyword) for keyword in keywords):
            return collection_id
    return "illustration-art"


def tags_for(record: dict[str, Any], collection_id: str) -> list[str]:
    haystack = f"{record['title']} {record['image_alt']} {record['source']} {record['prompt_zh_hant']}".lower()
    tags = ["sample", "sample_package_2", "awesome_gpt_image_2", "full_catalog", collection_id]
    for tag, keywords in TAG_RULES:
        if any(keyword_in(haystack, keyword) for keyword in keywords):
            tags.append(tag)
    return list(dict.fromkeys(tags))


def prompts_for(record: dict[str, Any]) -> list[dict[str, Any]]:
    prompts = [
        {
            "language": "zh_hant",
            "text": record["prompt_zh_hant"],
            "is_primary": True,
            "is_original": False,
            "provenance": {"kind": "conversion", "source_language": "zh_hans", "derived_from": "zh_hans", "method": "opencc-s2twp"},
        },
        {
            "language": "zh_hans",
            "text": _to_hans(record["prompt_source"]),
            "is_primary": False,
            "is_original": True,
            "provenance": {"kind": "source", "source_language": "zh_hans", "derived_from": None, "method": None},
        },
    ]
    en = split_english_prompt(record["prompt_source"])
    if en and en.strip() != record["prompt_source"].strip():
        prompts.append({
            "language": "en",
            "text": en,
            "is_primary": False,
            "is_original": False,
            "provenance": {"kind": "translation", "source_language": "zh_hans", "derived_from": "zh_hans", "method": "upstream-extracted-english-section"},
        })
    elif en and not any("\u4e00" <= ch <= "\u9fff" for ch in en):
        prompts.append({
            "language": "en",
            "text": en,
            "is_primary": False,
            "is_original": False,
            "provenance": {"kind": "translation", "source_language": "zh_hans", "derived_from": "zh_hans", "method": "upstream-english-prompt"},
        })
    return prompts


def build_manifest(source_root: Path, commit: str | None = None) -> dict[str, Any]:
    records = parse_gallery(source_root)
    collection_lookup = {collection["id"]: collection for collection in COLLECTIONS}
    items = []
    for record in records:
        collection_id = collection_for(record)
        item = {
            "id": record["id"],
            "number": record["number"],
            "title": record["title"],
            "slug": f"sample-awesome-gpt-image-2-{record['id']}-zh-hant",
            "collection_id": collection_id,
            "collection_name": collection_lookup[collection_id]["names"]["zh_hant"],
            "image": record["image"],
            "source_file": record["image"],
            "source_title": record["image_alt"],
            "source_name": SOURCE_NAME,
            "source_url": record["source_url"],
            "author": record["source"],
            "license": SOURCE_LICENSE,
            "model": "GPT Image 2 sample",
            "tags": tags_for(record, collection_id),
            "prompts": prompts_for(record),
        }
        items.append(item)
    return {
        "schema_version": 2,
        "id": "awesome-gpt-image-2-v1-zh_hant",
        "language": "zh_hant",
        "title": "Awesome GPT Image 2 second sample package (zh_hant)",
        "source": {
            "name": SOURCE_NAME,
            "url": SOURCE_URL,
            "commit": commit,
            "license": SOURCE_LICENSE,
            "license_url": f"{SOURCE_URL}/blob/main/LICENSE",
            "permission_note": "Upstream author granted permission to include this repository data as an Image Prompt Library sample package; preserve upstream attribution and MIT license notice.",
        },
        "collections": [
            {"id": collection["id"], "name": collection["names"]["zh_hant"], "names": collection["names"]}
            for collection in COLLECTIONS
        ],
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build freestylefly/awesome-gpt-image-2 sample-data manifest.")
    parser.add_argument("--source", required=True, help="Path to a local copy of freestylefly/awesome-gpt-image-2")
    parser.add_argument("--out", default="sample-data/manifests/awesome-gpt-image-2/zh_hant.json")
    parser.add_argument("--commit", default=None)
    args = parser.parse_args()
    manifest = build_manifest(Path(args.source), commit=args.commit)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for item in manifest["items"]:
        counts[item["collection_id"]] = counts.get(item["collection_id"], 0) + 1
    print(json.dumps({"items": len(manifest["items"]), "collections": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
