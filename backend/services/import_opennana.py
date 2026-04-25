from __future__ import annotations
import argparse, json, re
from pathlib import Path
from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import ImportResult, ItemCreate, PromptIn
from backend.services.image_store import store_image

def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".js":
        m = re.search(r"(?:const|let|var)\s+\w+\s*=\s*(.*?);?\s*$", text, re.S)
        if m: text = m.group(1)
    return json.loads(text)

def _items(data):
    if isinstance(data, list): return data
    for key in ("items", "nodes", "gallery", "data"):
        if isinstance(data, dict) and isinstance(data.get(key), list): return data[key]
    return []

def _nodes_by_slug(data):
    grouped = {}
    if isinstance(data, dict):
        for node in data.get("nodes") or []:
            slug = node.get("slug") or node.get("id")
            if slug:
                grouped.setdefault(str(slug), []).append(node)
    return grouped

def _first(item, keys, default=None):
    for k in keys:
        v = item.get(k)
        if v not in (None, "", []): return v
    return default

def import_opennana(source: Path | str, library: Path | str) -> ImportResult:
    source = Path(source); library = Path(library); init_db(library)
    repo = ItemRepository(library)
    batch_id = new_id("imp"); started = now(); log=[]; item_count=0; image_count=0
    with connect(library) as conn:
        conn.execute("INSERT INTO imports(id,source_name,source_path,status,started_at,log) VALUES(?,?,?,?,?,?)", (batch_id,"OpenNana",str(source),"running",started,"")); conn.commit()
    data = _load(source)
    image_nodes = _nodes_by_slug(data)
    for raw in _items(data):
        title = _first(raw, ["title", "name", "label"], "Untitled prompt")
        slug = _first(raw, ["slug", "id"])
        source_url = _first(raw, ["source_url", "url", "link"])
        existing = False
        if slug:
            with connect(library) as conn:
                existing = conn.execute("SELECT 1 FROM items WHERE slug=?", (str(slug),)).fetchone() is not None
        elif source_url:
            existing = repo.list_items(q=source_url, archived=None, limit=1).total > 0
        if existing:
            continue
        prompts=[]
        mapping=[("zh_hant", ["prompt_zh_tw","prompt_zh_hant","zh_hant"]), ("zh_hans", ["prompt_zh_cn","prompt_zh_hans","zh_hans"]), ("en", ["prompt_en","en"]), ("original", ["prompt","description"])]
        for lang, keys in mapping:
            txt = _first(raw, keys)
            if txt: prompts.append(PromptIn(language=lang, text=str(txt), is_primary=(len(prompts)==0)))
        if not prompts: prompts.append(PromptIn(language="original", text=title, is_primary=True))
        tags = _first(raw, ["tags", "keywords"], []) or []
        if isinstance(tags, str): tags=[t.strip() for t in re.split(r"[,，#]", tags) if t.strip()]
        tags = list(dict.fromkeys([*tags, *(_first(raw, ["styles"], []) or [])]))
        topics = _first(raw, ["topics"], []) or []
        cluster_name = _first(raw,["topic","cluster","category"]) or (topics[0] if topics else None)
        created = repo.create_item(ItemCreate(title=title, slug=slug, model=_first(raw,["model"], "ChatGPT Image2"), cluster_name=cluster_name, tags=tags, prompts=prompts, source_name=_first(raw,["source_name"], "OpenNana"), source_url=source_url), imported=True)
        item_count += 1
        imgs = _first(raw, ["images", "image_urls"], None) or _first(raw, ["image", "image_url", "src"], None)
        if imgs and not isinstance(imgs, list): imgs=[imgs]
        node_imgs = [n.get("image") for n in image_nodes.get(str(slug), []) if n.get("image")]
        imgs = [*(imgs or []), *node_imgs]
        for img in imgs:
            img_path = Path(str(img))
            candidates = [img_path]
            if not img_path.is_absolute():
                candidates = [source.parent / img_path, source.parent.parent / img_path, source.parent.parent / "html-gallery" / img_path]
            found = next((p for p in candidates if p.exists()), None)
            if found:
                stored = store_image(library, found.read_bytes(), found.name)
                repo.add_image(created.id, StoredImageInput(stored.original_path, stored.thumb_path, stored.preview_path, width=stored.width, height=stored.height, file_sha256=stored.file_sha256))
                image_count += 1
    with connect(library) as conn:
        conn.execute("UPDATE imports SET status=?, item_count=?, image_count=?, finished_at=?, log=? WHERE id=?", ("completed", item_count, image_count, now(), "\n".join(log), batch_id)); conn.commit()
    return ImportResult(id=batch_id, item_count=item_count, image_count=image_count, status="completed", log="\n".join(log))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--source", required=True); p.add_argument("--library", default="library")
    args=p.parse_args(); print(import_opennana(args.source,args.library).model_dump_json(indent=2))
if __name__ == "__main__": main()
