from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .config import APP_VERSION, resolve_library_path
from .db import get_db_path, init_db
from .routers import clusters, images, importers, items, tags

def create_app(library_path: Path | str | None = None) -> FastAPI:
    library = resolve_library_path(library_path)
    init_db(library)
    app = FastAPI(title="Image Prompt Library", version=APP_VERSION)
    app.state.library_path = library
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5177", "http://localhost:5177"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(items.router, prefix="/api")
    app.include_router(images.router, prefix="/api")
    app.include_router(clusters.router, prefix="/api")
    app.include_router(tags.router, prefix="/api")
    app.include_router(importers.router, prefix="/api")
    @app.get("/api/health")
    def health(): return {"ok": True, "version": APP_VERSION}
    @app.get("/api/config")
    def config(): return {"version": APP_VERSION, "library_path": str(library), "database_path": str(get_db_path(library)), "preferred_prompt_language": "zh_hant"}
    @app.get("/media/{media_path:path}")
    def media(media_path: str):
        safe_roots = {"originals", "thumbs", "previews"}
        parts = Path(media_path).parts
        if not parts or parts[0] not in safe_roots:
            raise HTTPException(status_code=404)
        candidate = (library / media_path).resolve()
        allowed_root = (library / parts[0]).resolve()
        try:
            candidate.relative_to(allowed_root)
        except ValueError as exc:
            raise HTTPException(status_code=404) from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(candidate)
    return app

app = create_app()
