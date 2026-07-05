from fastapi import APIRouter, Request

from backend.schemas import CleanupApplyRequest, CleanupApplyResult, CleanupPreview
from backend.services.library_cleanup import LibraryCleanupService

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


def service(request: Request) -> LibraryCleanupService:
    return LibraryCleanupService(request.app.state.library_path)


@router.get("/preview", response_model=CleanupPreview)
def preview_cleanup(request: Request):
    return service(request).preview()


@router.post("/apply", response_model=CleanupApplyResult)
def apply_cleanup(request: Request, payload: CleanupApplyRequest):
    return service(request).apply(
        remove_broken_image_records=payload.remove_broken_image_records,
        remove_unreferenced_files=payload.remove_unreferenced_files,
    )
