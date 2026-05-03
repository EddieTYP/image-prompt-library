from __future__ import annotations
import json, re, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from contextlib import suppress
from .db import connect, init_db
from .schemas import ClusterRecord, ImageRecord, ItemCreate, ItemDetail, ItemList, ItemSummary, ItemUpdate, PromptIn, PromptRecord, TagRecord
from .services.text_normalize import to_traditional

TEMPLATE_TAG_NAME = "template"
_PROMPT_TEMPLATE_RE = re.compile(r"{{([^{}]*)}}")


def prompt_has_template_variables(text: str) -> bool:
    for match in _PROMPT_TEMPLATE_RE.finditer(text or ""):
        if match.start() > 0 and text[match.start() - 1] == "\\":
            continue
        previous_open = text.rfind("{{", 0, match.start())
        previous_close = text.rfind("}}", 0, match.start())
        if previous_open > previous_close:
            continue
        if match.group(1).strip():
            return True
    return False


def _sync_template_tag_names(tags: list[str], prompts: list[PromptIn]) -> list[str]:
    clean_tags = [tag.strip() for tag in tags if tag and tag.strip() and tag.strip() != TEMPLATE_TAG_NAME]
    if any(prompt_has_template_variables(prompt.text) for prompt in prompts):
        clean_tags.append(TEMPLATE_TAG_NAME)
    return list(dict.fromkeys(clean_tags))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]

@dataclass
class StoredImageInput:
    original_path: str
    thumb_path: str | None = None
    preview_path: str | None = None
    remote_url: str | None = None
    width: int | None = None
    height: int | None = None
    file_sha256: str | None = None
    role: str = "result_image"

class ItemRepository:
    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        init_db(self.library_path)

    def _unique_slug(self, conn, base: str, current_id: str | None = None) -> str:
        slug = slugify(base)
        candidate = slug
        i = 2
        while True:
            row = conn.execute("SELECT id FROM items WHERE slug=?", (candidate,)).fetchone()
            if not row or row["id"] == current_id:
                return candidate
            candidate = f"{slug}-{i}"
            i += 1

    def ensure_cluster(self, conn, name: str | None, cluster_id: str | None = None):
        if cluster_id:
            return cluster_id
        if not name:
            return None
        existing = conn.execute("SELECT id FROM clusters WHERE name=?", (name,)).fetchone()
        if existing:
            return existing["id"]
        cid = new_id("clu")
        ts = now()
        conn.execute("INSERT INTO clusters(id,name,created_at,updated_at) VALUES(?,?,?,?)", (cid, name, ts, ts))
        return cid

    def update_cluster_names(self, cluster_id: str | None, names: dict[str, str] | None) -> None:
        if not cluster_id or not names:
            return
        clean = {str(key): str(value).strip() for key, value in names.items() if str(value).strip()}
        if not clean:
            return
        with connect(self.library_path) as conn:
            conn.execute("UPDATE clusters SET names=?, updated_at=? WHERE id=?", (json.dumps(clean, ensure_ascii=False), now(), cluster_id))
            conn.commit()

    def _cluster_names_from_row(self, row) -> dict[str, str]:
        raw = row["cluster_names"] if "cluster_names" in row.keys() else row["names"] if "names" in row.keys() else None
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return {str(key): str(value) for key, value in parsed.items() if str(value).strip()}
            except json.JSONDecodeError:
                return {}
        return {}

    def ensure_tag(self, conn, name: str, kind: str = "general") -> str:
        clean = name.strip()
        row = conn.execute("SELECT id FROM tags WHERE name=?", (clean,)).fetchone()
        if row:
            return row["id"]
        tid = new_id("tag")
        conn.execute("INSERT INTO tags(id,name,kind,created_at) VALUES(?,?,?,?)", (tid, clean, kind, now()))
        return tid

    def delete_empty_clusters(self, conn):
        rows = conn.execute("""
            SELECT c.id
            FROM clusters c
            LEFT JOIN items active_items ON active_items.cluster_id = c.id AND active_items.archived = 0
            GROUP BY c.id
            HAVING COUNT(active_items.id) = 0
        """).fetchall()
        cluster_ids = [row["id"] for row in rows]
        if not cluster_ids:
            return
        placeholders = ",".join("?" for _ in cluster_ids)
        conn.execute(f"UPDATE items SET cluster_id=NULL, updated_at=? WHERE cluster_id IN ({placeholders})", (now(), *cluster_ids))
        conn.execute(f"DELETE FROM clusters WHERE id IN ({placeholders})", cluster_ids)

    def _normalized_prompts(self, prompts: list[PromptIn], *, strict_original: bool = False) -> list[PromptIn]:
        normalized = list(prompts)
        languages = {p.language for p in normalized}
        if strict_original:
            self._validate_explicit_original(normalized)
        zh_hans = next((p for p in normalized if p.language == "zh_hans" and p.text.strip()), None)
        if zh_hans and "zh_hant" not in languages:
            provenance = {
                "kind": "conversion",
                "source_language": zh_hans.language,
                "derived_from": zh_hans.language,
                "method": "opencc-s2t",
            }
            normalized.insert(0, PromptIn(
                language="zh_hant",
                text=to_traditional(zh_hans.text),
                is_primary=zh_hans.is_primary,
                is_original=False,
                provenance=provenance,
            ))
            if zh_hans.is_primary:
                zh_hans.is_primary = False
        return self._with_single_original(normalized)

    def _validate_explicit_original(self, prompts: list[PromptIn]) -> None:
        usable = [prompt for prompt in prompts if prompt.text.strip()]
        has_explicit_provenance = any(bool(prompt.provenance) for prompt in usable)
        has_explicit_original_marker = any("is_original" in getattr(prompt, "model_fields_set", set()) for prompt in usable)
        if not (has_explicit_provenance or has_explicit_original_marker):
            return
        if sum(1 for prompt in usable if prompt.is_original) != 1:
            raise ValueError("Exactly one prompt must be marked as source/original")

    def _with_single_original(self, prompts: list[PromptIn]) -> list[PromptIn]:
        usable = [prompt for prompt in prompts if prompt.text.strip()]
        if not usable:
            return prompts
        originals = [prompt for prompt in usable if prompt.is_original]
        source_language = (originals[0] if originals else next((p for p in usable if p.is_primary), usable[0])).language
        original_assigned = False
        for prompt in usable:
            is_original = bool(prompt.is_original and prompt.language == source_language and not original_assigned)
            if not originals and prompt.language == source_language and not original_assigned:
                is_original = True
            prompt.is_original = is_original
            if is_original:
                original_assigned = True
                prompt.provenance = {
                    **({} if not prompt.provenance else prompt.provenance),
                    "kind": prompt.provenance.get("kind") or "manual",
                    "source_language": prompt.provenance.get("source_language") or prompt.language,
                    "derived_from": prompt.provenance.get("derived_from"),
                    "method": prompt.provenance.get("method"),
                }
            else:
                prompt.provenance = {
                    **({} if not prompt.provenance else prompt.provenance),
                    "kind": prompt.provenance.get("kind") or "manual",
                    "source_language": prompt.provenance.get("source_language") or source_language,
                    "derived_from": prompt.provenance.get("derived_from") or source_language,
                    "method": prompt.provenance.get("method"),
                }
        return prompts

    def _insert_prompt(self, conn, item_id: str, prompt: PromptIn, is_primary: bool, timestamp: str) -> None:
        conn.execute(
            """INSERT INTO prompts(id,item_id,language,text,is_primary,is_original,provenance,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                new_id("prm"),
                item_id,
                prompt.language,
                prompt.text,
                int(is_primary),
                int(prompt.is_original),
                json.dumps(prompt.provenance or {}, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )

    def create_item(self, payload: ItemCreate, imported: bool = False, forced_id: str | None = None) -> ItemDetail:
        with connect(self.library_path) as conn:
            iid = forced_id or new_id("itm")
            ts = now()
            cluster_id = self.ensure_cluster(conn, payload.cluster_name, payload.cluster_id)
            slug = self._unique_slug(conn, payload.slug or payload.title)
            conn.execute("""INSERT INTO items(id,title,slug,model,media_type,source_name,source_url,author,cluster_id,rating,favorite,archived,notes,created_at,updated_at,imported_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (iid, payload.title, slug, payload.model, payload.media_type, payload.source_name, payload.source_url, payload.author, cluster_id, payload.rating, int(payload.favorite), int(payload.archived), payload.notes, ts, ts, ts if imported else None))
            normalized_prompts = self._normalized_prompts(payload.prompts, strict_original=not imported)
            for idx, prompt in enumerate(normalized_prompts):
                self._insert_prompt(conn, iid, prompt, prompt.is_primary or idx == 0, ts)
            for tag in _sync_template_tag_names(payload.tags, normalized_prompts):
                if tag.strip():
                    tid = self.ensure_tag(conn, tag)
                    conn.execute("INSERT OR IGNORE INTO item_tags(item_id,tag_id) VALUES(?,?)", (iid, tid))
            self.rebuild_search(conn, iid)
            conn.commit()
        return self.get_item(iid)

    def update_item(self, item_id: str, payload: ItemUpdate) -> ItemDetail:
        data = payload.model_dump(exclude_unset=True)
        scalar = {k:v for k,v in data.items() if k in {"title","model","source_name","source_url","author","rating","notes"}}
        with connect(self.library_path) as conn:
            existing_item = conn.execute("SELECT cluster_id FROM items WHERE id=?", (item_id,)).fetchone()
            if existing_item is None:
                raise KeyError(item_id)
            previous_cluster_id = existing_item["cluster_id"]
            if "cluster_name" in data or "cluster_id" in data:
                scalar["cluster_id"] = self.ensure_cluster(conn, data.get("cluster_name"), data.get("cluster_id"))
            for bool_key in ("favorite","archived"):
                if bool_key in data: scalar[bool_key] = int(data[bool_key])
            if scalar:
                scalar["updated_at"] = now()
                sets = ", ".join(f"{k}=?" for k in scalar)
                conn.execute(f"UPDATE items SET {sets} WHERE id=?", (*scalar.values(), item_id))
            prompts_for_template_tag = None
            if "prompts" in data and data["prompts"] is not None:
                raw_prompts = [PromptIn.model_validate(prompt) if isinstance(prompt, dict) else prompt for prompt in (payload.prompts or [])]
                prompts_for_template_tag = self._normalized_prompts(raw_prompts, strict_original=True)
            if prompts_for_template_tag is None:
                prompts_for_template_tag = self._prompts(conn, item_id)
            if "tags" in data and data["tags"] is not None:
                conn.execute("DELETE FROM item_tags WHERE item_id=?", (item_id,))
                for tag in _sync_template_tag_names(data["tags"], prompts_for_template_tag):
                    if tag.strip():
                        conn.execute("INSERT OR IGNORE INTO item_tags(item_id,tag_id) VALUES(?,?)", (item_id, self.ensure_tag(conn, tag)))
            elif "prompts" in data and data["prompts"] is not None:
                existing_tags = [row["name"] for row in conn.execute("SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id=t.id WHERE it.item_id=?", (item_id,)).fetchall()]
                conn.execute("DELETE FROM item_tags WHERE item_id=?", (item_id,))
                for tag in _sync_template_tag_names(existing_tags, prompts_for_template_tag):
                    conn.execute("INSERT OR IGNORE INTO item_tags(item_id,tag_id) VALUES(?,?)", (item_id, self.ensure_tag(conn, tag)))
            if "prompts" in data and data["prompts"] is not None:
                conn.execute("DELETE FROM prompts WHERE item_id=?", (item_id,))
                ts = now()
                for idx, prompt in enumerate(prompts_for_template_tag):
                    self._insert_prompt(conn, item_id, prompt, prompt.is_primary or idx == 0, ts)
            self.rebuild_search(conn, item_id)
            if ("cluster_id" in scalar and scalar["cluster_id"] != previous_cluster_id) or scalar.get("archived") == 1:
                self.delete_empty_clusters(conn)
            conn.commit()
        return self.get_item(item_id)

    def set_archived(self, item_id: str, archived: bool=True) -> ItemDetail:
        return self.update_item(item_id, ItemUpdate(archived=archived))

    def _safe_library_file(self, rel_path: str | None) -> Path | None:
        if not rel_path:
            return None
        candidate = (self.library_path / rel_path).resolve()
        library = self.library_path.resolve()
        try:
            if not candidate.is_relative_to(library):
                return None
        except AttributeError:
            if library not in candidate.parents and candidate != library:
                return None
        return candidate

    def _remove_unreferenced_media_files(self, paths: set[str]) -> None:
        for rel_path in sorted(path for path in paths if path):
            file_path = self._safe_library_file(rel_path)
            if not file_path or not file_path.is_file():
                continue
            with suppress(OSError):
                file_path.unlink()

    def delete_item(self, item_id: str) -> ItemDetail:
        detail = self.get_item(item_id)
        candidate_paths = {
            path
            for image in detail.images
            for path in (image.original_path, image.thumb_path, image.preview_path)
            if path
        }
        with connect(self.library_path) as conn:
            if conn.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone() is None:
                raise KeyError(item_id)
            conn.execute("DELETE FROM item_search WHERE item_id=?", (item_id,))
            conn.execute("DELETE FROM items WHERE id=?", (item_id,))
            self.delete_empty_clusters(conn)
            still_used = set()
            for rel_path in candidate_paths:
                row = conn.execute(
                    """SELECT 1 FROM images
                       WHERE original_path=? OR thumb_path=? OR preview_path=?
                       LIMIT 1""",
                    (rel_path, rel_path, rel_path),
                ).fetchone()
                if row is not None:
                    still_used.add(rel_path)
            conn.commit()
        self._remove_unreferenced_media_files(candidate_paths - still_used)
        return detail

    def toggle_favorite(self, item_id: str) -> ItemDetail:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT favorite FROM items WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        return self.update_item(item_id, ItemUpdate(favorite=not bool(row["favorite"])))

    def add_image(self, item_id: str, image: StoredImageInput) -> ImageRecord:
        if image.role not in {"result_image", "reference_image"}:
            raise ValueError("Invalid image role")
        with connect(self.library_path) as conn:
            iid = new_id("img")
            ts = now()
            order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM images WHERE item_id=?", (item_id,)).fetchone()[0]
            conn.execute("""INSERT INTO images(id,item_id,original_path,thumb_path,preview_path,remote_url,width,height,file_sha256,role,sort_order,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (iid,item_id,image.original_path,image.thumb_path,image.preview_path,image.remote_url,image.width,image.height,image.file_sha256,image.role,order,ts))
            conn.commit()
        return self._image_by_id(iid)

    def _cluster_from_row(self, row) -> ClusterRecord | None:
        if not row or not row["cluster_id"]: return None
        return ClusterRecord(id=row["cluster_id"], name=row["cluster_name"], names=self._cluster_names_from_row(row), description=row["cluster_description"], sort_order=row["cluster_sort_order"] or 0)

    def _image_by_id(self, image_id: str) -> ImageRecord:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
            return ImageRecord(**dict(row))

    def _tags(self, conn, item_id: str) -> list[TagRecord]:
        rows = conn.execute("SELECT t.id,t.name,t.kind,0 as count FROM tags t JOIN item_tags it ON it.tag_id=t.id WHERE it.item_id=? ORDER BY t.name", (item_id,)).fetchall()
        return [TagRecord(**dict(r)) for r in rows]

    def _prompts(self, conn, item_id: str) -> list[PromptRecord]:
        rows = conn.execute("SELECT * FROM prompts WHERE item_id=? ORDER BY is_primary DESC, created_at", (item_id,)).fetchall()
        prompts: list[PromptRecord] = []
        for row in rows:
            data = dict(row)
            provenance = data.get("provenance")
            if isinstance(provenance, str) and provenance.strip():
                try:
                    data["provenance"] = json.loads(provenance)
                except json.JSONDecodeError:
                    data["provenance"] = {}
            else:
                data["provenance"] = {}
            data["is_primary"] = bool(data.get("is_primary"))
            data["is_original"] = bool(data.get("is_original"))
            prompts.append(PromptRecord(**data))
        return prompts

    def _images(self, conn, item_id: str) -> list[ImageRecord]:
        return [ImageRecord(**dict(r)) for r in conn.execute("""SELECT * FROM images WHERE item_id=?
            ORDER BY CASE role WHEN 'result_image' THEN 0 ELSE 1 END, sort_order, created_at""", (item_id,)).fetchall()]

    def _summary_from_row(self, conn, row) -> ItemSummary:
        prompts = self._prompts(conn, row["id"])
        images = self._images(conn, row["id"])
        return ItemSummary(id=row["id"], title=row["title"], slug=row["slug"], model=row["model"], source_name=row["source_name"], source_url=row["source_url"], cluster=self._cluster_from_row(row), tags=self._tags(conn,row["id"]), prompts=prompts, prompt_snippet=(prompts[0].text[:220] if prompts else None), first_image=(images[0] if images else None), rating=row["rating"], favorite=bool(row["favorite"]), archived=bool(row["archived"]), updated_at=row["updated_at"], created_at=row["created_at"])

    def get_item(self, item_id: str) -> ItemDetail:
        with connect(self.library_path) as conn:
            row = conn.execute("""SELECT i.*, c.id cluster_id, c.name cluster_name, c.names cluster_names, c.description cluster_description, c.sort_order cluster_sort_order FROM items i LEFT JOIN clusters c ON c.id=i.cluster_id WHERE i.id=?""", (item_id,)).fetchone()
            if not row: raise KeyError(item_id)
            summary = self._summary_from_row(conn, row)
            return ItemDetail(**summary.model_dump(), images=self._images(conn,item_id), notes=row["notes"], author=row["author"])

    def list_items(self, q: str | None=None, cluster: str | None=None, tag: str | None=None, favorite: bool | None=None, archived: bool | None=False, sort: str="updated_desc", limit: int=100, offset: int=0) -> ItemList:
        where=[]; params=[]
        if archived is not None: where.append("i.archived=?"); params.append(int(archived))
        if cluster: where.append("(i.cluster_id=? OR c.name=?)"); params += [cluster, cluster]
        if tag: where.append("EXISTS (SELECT 1 FROM item_tags it JOIN tags t ON t.id=it.tag_id WHERE it.item_id=i.id AND (t.id=? OR t.name=?))"); params += [tag, tag]
        if favorite is not None: where.append("i.favorite=?"); params.append(int(favorite))
        if q:
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", q)
            like = f"%{q}%"
            if tokens:
                where.append("i.id IN (SELECT item_id FROM item_search WHERE item_search MATCH ? UNION SELECT i2.id FROM items i2 LEFT JOIN prompts p2 ON p2.item_id=i2.id LEFT JOIN item_tags it2 ON it2.item_id=i2.id LEFT JOIN tags t2 ON t2.id=it2.tag_id LEFT JOIN clusters c2 ON c2.id=i2.cluster_id WHERE (i2.title LIKE ? OR p2.text LIKE ? OR t2.name LIKE ? OR c2.name LIKE ? OR i2.notes LIKE ?))")
                match = ' '.join(part + '*' for part in tokens)
                params += [match, like, like, like, like, like]
            else:
                where.append("i.id IN (SELECT i2.id FROM items i2 LEFT JOIN prompts p2 ON p2.item_id=i2.id LEFT JOIN item_tags it2 ON it2.item_id=i2.id LEFT JOIN tags t2 ON t2.id=it2.tag_id LEFT JOIN clusters c2 ON c2.id=i2.cluster_id WHERE (i2.title LIKE ? OR p2.text LIKE ? OR t2.name LIKE ? OR c2.name LIKE ? OR i2.notes LIKE ?))")
                params += [like, like, like, like, like]
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        order = {"created_desc":"i.created_at DESC", "title_asc":"i.title COLLATE NOCASE ASC", "rating_desc":"i.rating DESC, i.updated_at DESC"}.get(sort, "i.updated_at DESC")
        with connect(self.library_path) as conn:
            total = conn.execute(f"SELECT COUNT(DISTINCT i.id) FROM items i LEFT JOIN clusters c ON c.id=i.cluster_id {where_sql}", params).fetchone()[0]
            rows = conn.execute(f"""SELECT i.*, c.id cluster_id, c.name cluster_name, c.names cluster_names, c.description cluster_description, c.sort_order cluster_sort_order FROM items i LEFT JOIN clusters c ON c.id=i.cluster_id {where_sql} GROUP BY i.id ORDER BY {order} LIMIT ? OFFSET ?""", (*params, limit, offset)).fetchall()
            return ItemList(items=[self._summary_from_row(conn,r) for r in rows], total=total, limit=limit, offset=offset)

    def list_clusters(self) -> list[ClusterRecord]:
        with connect(self.library_path) as conn:
            self.delete_empty_clusters(conn)
            conn.commit()
            rows = conn.execute("""SELECT c.*, COUNT(i.id) count FROM clusters c LEFT JOIN items i ON i.cluster_id=c.id AND i.archived=0 GROUP BY c.id HAVING count > 0 ORDER BY c.sort_order, c.name""").fetchall()
            out=[]
            for r in rows:
                previews = [x[0] for x in conn.execute("""SELECT COALESCE(img.thumb_path,img.preview_path,img.original_path)
                    FROM images img JOIN items i ON i.id=img.item_id
                    WHERE i.cluster_id=? AND i.archived=0
                      AND NOT EXISTS (
                        SELECT 1 FROM images better
                        WHERE better.item_id=img.item_id AND (
                          CASE better.role WHEN 'result_image' THEN 0 ELSE 1 END < CASE img.role WHEN 'result_image' THEN 0 ELSE 1 END
                          OR (CASE better.role WHEN 'result_image' THEN 0 ELSE 1 END = CASE img.role WHEN 'result_image' THEN 0 ELSE 1 END AND better.sort_order < img.sort_order)
                          OR (CASE better.role WHEN 'result_image' THEN 0 ELSE 1 END = CASE img.role WHEN 'result_image' THEN 0 ELSE 1 END AND better.sort_order = img.sort_order AND better.created_at < img.created_at)
                        )
                      )
                    ORDER BY CASE img.role WHEN 'result_image' THEN 0 ELSE 1 END, img.sort_order LIMIT 4""",(r["id"],)).fetchall() if x[0]]
                out.append(ClusterRecord(id=r["id"], name=r["name"], names=self._cluster_names_from_row(r), description=r["description"], sort_order=r["sort_order"], count=r["count"], preview_images=previews))
            return out

    def list_tags(self) -> list[TagRecord]:
        with connect(self.library_path) as conn:
            rows = conn.execute("""SELECT t.id,t.name,t.kind,COUNT(i.id) count FROM tags t LEFT JOIN item_tags it ON it.tag_id=t.id LEFT JOIN items i ON i.id=it.item_id AND i.archived=0 GROUP BY t.id ORDER BY t.name""").fetchall()
            return [TagRecord(**dict(r)) for r in rows]

    def rebuild_search(self, conn, item_id: str):
        conn.execute("DELETE FROM item_search WHERE item_id=?", (item_id,))
        row = conn.execute("SELECT i.title,i.source_name,i.source_url,i.notes,c.name cluster FROM items i LEFT JOIN clusters c ON c.id=i.cluster_id WHERE i.id=?", (item_id,)).fetchone()
        if not row: return
        prompts = "\n".join(r[0] for r in conn.execute("SELECT text FROM prompts WHERE item_id=?", (item_id,)).fetchall())
        tags = " ".join(r[0] for r in conn.execute("SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id=t.id WHERE it.item_id=?", (item_id,)).fetchall())
        source = " ".join(x or "" for x in (row["source_name"], row["source_url"]))
        conn.execute("INSERT INTO item_search(item_id,title,prompts,tags,cluster,source,notes) VALUES(?,?,?,?,?,?,?)", (item_id,row["title"],prompts,tags,row["cluster"] or "",source,row["notes"] or ""))
