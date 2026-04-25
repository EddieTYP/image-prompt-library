from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from PIL import UnidentifiedImageError
from backend.repositories import ItemRepository, StoredImageInput
from backend.services.image_store import store_image
router = APIRouter()

MAX_UPLOAD_BYTES = 30 * 1024 * 1024

@router.post("/items/{item_id}/images")
async def upload_image(request: Request, item_id: str, file: UploadFile = File(...), role: str = Form("result_image")):
    if role not in {"result_image", "reference_image"}:
        raise HTTPException(400, "Invalid image role")
    repository = ItemRepository(request.app.state.library_path)
    try:
        repository.get_item(item_id)
    except KeyError as exc:
        raise HTTPException(404, "Item not found") from exc
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image upload too large")
    try:
        stored = store_image(request.app.state.library_path, data, file.filename or "image.png")
    except (ValueError, UnidentifiedImageError) as exc:
        raise HTTPException(400, str(exc)) from exc
    rec = repository.add_image(item_id, StoredImageInput(stored.original_path, stored.thumb_path, stored.preview_path, width=stored.width, height=stored.height, file_sha256=stored.file_sha256, role=role))
    return rec
