from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel
from backend.db import connect
from backend.services.import_opennana import import_opennana
router = APIRouter()
class OpenNanaImportRequest(BaseModel): path: str
@router.post("/import/opennana")
def run_import(request: Request, payload: OpenNanaImportRequest): return import_opennana(Path(payload.path), request.app.state.library_path)
@router.get("/imports")
def imports(request: Request):
    with connect(request.app.state.library_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM imports ORDER BY started_at DESC").fetchall()]
