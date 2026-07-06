from fastapi import APIRouter, HTTPException, Request

from backend.schemas import CleanupApplyRequest, CleanupApplyResult, CleanupPreview
from backend.services.library_cleanup import LibraryCleanupService

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


def service(request: Request) -> LibraryCleanupService:
    return LibraryCleanupService(request.app.state.library_path)


@router.get("/preview", response_model=CleanupPreview)
def preview_cleanup(request: Request):
    preview = service(request).preview()
    request.app.state.cleanup_preview = preview
    return preview


@router.post("/apply", response_model=CleanupApplyResult)
def apply_cleanup(request: Request, payload: CleanupApplyRequest):
    preview = getattr(request.app.state, "cleanup_preview", None)
    if preview is None or preview.preview_token != payload.preview_token:
        raise HTTPException(409, "Preview cleanup before applying changes")
    result = service(request).apply(
        preview,
        remove_broken_image_records=payload.remove_broken_image_records,
        remove_unreferenced_files=payload.remove_unreferenced_files,
    )
    request.app.state.cleanup_preview = result
    return result
