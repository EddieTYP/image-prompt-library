from fastapi import APIRouter, HTTPException, Request
from backend.repositories import ItemRepository
from backend.schemas import ItemCreate, ItemDetail, ItemList, ItemUpdate
router = APIRouter()

def repo(request: Request): return ItemRepository(request.app.state.library_path)

def not_found(exc: KeyError):
    raise HTTPException(404, "Item not found") from exc

@router.get("/items", response_model=ItemList)
def list_items(request: Request, q: str | None=None, cluster: str | None=None, tag: str | None=None, favorite: bool | None=None, archived: bool | None=False, sort: str="updated_desc", limit: int=100, offset: int=0):
    return repo(request).list_items(q=q, cluster=cluster, tag=tag, favorite=favorite, archived=archived, sort=sort, limit=min(limit,1000), offset=offset)

@router.post("/items", response_model=ItemDetail)
def create_item(request: Request, payload: ItemCreate): return repo(request).create_item(payload)

@router.get("/items/{item_id}", response_model=ItemDetail)
def get_item(request: Request, item_id: str):
    try: return repo(request).get_item(item_id)
    except KeyError as exc: not_found(exc)

@router.patch("/items/{item_id}", response_model=ItemDetail)
def update_item(request: Request, item_id: str, payload: ItemUpdate):
    try: return repo(request).update_item(item_id, payload)
    except KeyError as exc: not_found(exc)

@router.delete("/items/{item_id}", response_model=ItemDetail)
def delete_item(request: Request, item_id: str):
    try: return repo(request).set_archived(item_id, True)
    except KeyError as exc: not_found(exc)

@router.post("/items/{item_id}/favorite", response_model=ItemDetail)
def favorite_item(request: Request, item_id: str):
    try: return repo(request).toggle_favorite(item_id)
    except KeyError as exc: not_found(exc)
