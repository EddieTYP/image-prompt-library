from fastapi import APIRouter, HTTPException, Query, Request

from backend.schemas import (
    ImportDraftAcceptResult,
    ImportDraftCreate,
    ImportDraftList,
    ImportDraftRecord,
    RepositoryIngestRequest,
    RepositoryIngestResult,
)
from backend.services.import_drafts import ImportDraftConflict, ImportDraftRepository
from backend.services.repository_ingest import ingest_repository_to_drafts

router = APIRouter(prefix="/import-drafts", tags=["import-drafts"])


def repo(request: Request) -> ImportDraftRepository:
    return ImportDraftRepository(request.app.state.library_path)


@router.post("", response_model=ImportDraftRecord)
def create_import_draft(payload: ImportDraftCreate, request: Request):
    return repo(request).create_draft(payload)


@router.get("", response_model=ImportDraftList)
def list_import_drafts(
    request: Request,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return repo(request).list_drafts(status=status, limit=limit, offset=offset)


@router.post("/repository", response_model=RepositoryIngestResult)
def ingest_repository(payload: RepositoryIngestRequest, request: Request):
    try:
        return ingest_repository_to_drafts(payload, request.app.state.library_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{draft_id}", response_model=ImportDraftRecord)
def get_import_draft(draft_id: str, request: Request):
    try:
        return repo(request).get_draft(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc


@router.post("/{draft_id}/accept", response_model=ImportDraftAcceptResult)
def accept_import_draft(draft_id: str, request: Request):
    try:
        return repo(request).accept_draft(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc
    except ImportDraftConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
