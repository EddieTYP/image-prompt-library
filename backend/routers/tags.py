from fastapi import APIRouter, Request
from backend.repositories import ItemRepository
router = APIRouter()
@router.get("/tags")
def tags(request: Request): return ItemRepository(request.app.state.library_path).list_tags()
