import json

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from PIL import UnidentifiedImageError

from backend.schemas import GenerationJobAcceptResult, GenerationJobCreate, GenerationJobList, GenerationJobRecord
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository
from backend.services.openai_codex_native import CodexNativeAuthError, OpenAICodexNativeProvider

router = APIRouter(prefix="/generation-jobs", tags=["generation-jobs"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def repo(request: Request) -> GenerationJobRepository:
    return GenerationJobRepository(request.app.state.library_path)


@router.post("", response_model=GenerationJobRecord)
def create_generation_job(payload: GenerationJobCreate, request: Request):
    try:
        return repo(request).create_job(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source item not found") from exc


@router.get("", response_model=GenerationJobList)
def list_generation_jobs(
    request: Request,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return repo(request).list_jobs(status=status, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=GenerationJobRecord)
def get_generation_job(job_id: str, request: Request):
    try:
        return repo(request).get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc


@router.post("/{job_id}/result", response_model=GenerationJobRecord)
async def upload_generation_result(
    job_id: str,
    request: Request,
    file: UploadFile = File(...),
    metadata: str = Form("{}"),
):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Generation result upload too large")
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
        if not isinstance(parsed_metadata, dict):
            parsed_metadata = {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    try:
        return repo(request).stage_result(job_id, data, file.filename or "generated.png", parsed_metadata)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc
    except (GenerationJobConflict, ValueError, UnidentifiedImageError) as exc:
        raise HTTPException(status_code=409 if isinstance(exc, GenerationJobConflict) else 400, detail=str(exc)) from exc


@router.post("/{job_id}/run", response_model=GenerationJobRecord)
def run_generation_job(job_id: str, request: Request):
    try:
        return OpenAICodexNativeProvider().run_job(request.app.state.library_path, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc
    except GenerationJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CodexNativeAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/accept", response_model=GenerationJobAcceptResult)
def accept_generation_job(job_id: str, request: Request):
    try:
        return repo(request).accept_result(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc
    except GenerationJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/accept-as-new-item", response_model=GenerationJobAcceptResult)
def accept_generation_job_as_new_item(job_id: str, request: Request):
    try:
        return repo(request).accept_result_as_new_item(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc
    except GenerationJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/discard", response_model=GenerationJobRecord)
def discard_generation_job(job_id: str, request: Request):
    try:
        return repo(request).discard_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404) from exc
    except GenerationJobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
