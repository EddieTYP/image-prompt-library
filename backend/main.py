from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .config import APP_VERSION, resolve_library_path
from .db import get_db_path, init_db
from .routers import clusters, images, items, tags

DEFAULT_FRONTEND_DIST_PATH = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app(library_path: Path | str | None = None, frontend_dist_path: Path | str | None = None) -> FastAPI:
    library = resolve_library_path(library_path)
    frontend_dist = Path(frontend_dist_path).resolve() if frontend_dist_path is not None else DEFAULT_FRONTEND_DIST_PATH.resolve()
    init_db(library)
    app = FastAPI(title="Image Prompt Library", version=APP_VERSION)
    app.state.library_path = library
    app.state.frontend_dist_path = frontend_dist
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5177", "http://localhost:5177"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(items.router, prefix="/api")
    app.include_router(images.router, prefix="/api")
    app.include_router(clusters.router, prefix="/api")
    app.include_router(tags.router, prefix="/api")
    @app.get("/api/health")
    def health(): return {"ok": True, "version": APP_VERSION}
    @app.get("/api/config")
    def config(): return {"version": APP_VERSION, "library_path": str(library), "database_path": str(get_db_path(library)), "preferred_prompt_language": "zh_hant"}
    @app.api_route("/api/{api_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def unknown_api(api_path: str):
        raise HTTPException(status_code=404)
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

    def serve_frontend_path(frontend_path: str = ""):
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = frontend_dist / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="Frontend build not found. Run `npm run build` first, or use `./scripts/dev.sh` for development.")
        candidate = (frontend_dist / frontend_path).resolve() if frontend_path else index.resolve()
        try:
            candidate.relative_to(frontend_dist)
        except ValueError as exc:
            raise HTTPException(status_code=404) from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    @app.get("/")
    def frontend_root():
        return serve_frontend_path()

    @app.get("/{frontend_path:path}")
    def frontend_app(frontend_path: str):
        return serve_frontend_path(frontend_path)
    return app

app = create_app()
