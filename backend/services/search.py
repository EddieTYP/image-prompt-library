from backend.repositories import ItemRepository

def search_items(library_path, **kwargs):
    return ItemRepository(library_path).list_items(**kwargs)
