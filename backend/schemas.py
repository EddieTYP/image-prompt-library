from typing import Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict

class PromptIn(BaseModel):
    language: str = "original"
    text: str
    is_primary: bool = False
    is_original: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)

class PromptRecord(PromptIn):
    id: str
    item_id: str
    created_at: str
    updated_at: str

class ImageRecord(BaseModel):
    id: str
    item_id: str
    original_path: str
    thumb_path: Optional[str] = None
    preview_path: Optional[str] = None
    remote_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_sha256: Optional[str] = None
    role: str = "result_image"
    sort_order: int = 0
    created_at: str

class ClusterRecord(BaseModel):
    id: str
    name: str
    names: dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None
    sort_order: int = 0
    count: int = 0
    preview_images: List[str] = Field(default_factory=list)

class TagRecord(BaseModel):
    id: str
    name: str
    kind: str = "general"
    count: int = 0

class ItemCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    model: str = "ChatGPT Image2"
    media_type: str = "image"
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_name: Optional[str] = None
    rating: int = 0
    favorite: bool = False
    archived: bool = False
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    prompts: List[PromptIn] = Field(default_factory=list)

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_name: Optional[str] = None
    rating: Optional[int] = None
    favorite: Optional[bool] = None
    archived: Optional[bool] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    prompts: Optional[List[PromptIn]] = None

class ItemSummary(BaseModel):
    id: str
    title: str
    slug: str
    model: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    cluster: Optional[ClusterRecord] = None
    tags: List[TagRecord] = Field(default_factory=list)
    prompts: List[PromptRecord] = Field(default_factory=list)
    prompt_snippet: Optional[str] = None
    first_image: Optional[ImageRecord] = None
    rating: int = 0
    favorite: bool = False
    archived: bool = False
    updated_at: str
    created_at: str

class ItemDetail(ItemSummary):
    images: List[ImageRecord] = Field(default_factory=list)
    notes: Optional[str] = None
    author: Optional[str] = None

class ItemList(BaseModel):
    items: List[ItemSummary]
    total: int
    limit: int
    offset: int

class ImportResult(BaseModel):
    id: str
    item_count: int
    image_count: int
    status: str
    log: str = ""

class ImportDraftMedia(BaseModel):
    url: Optional[str] = None
    original_path: Optional[str] = None
    staged_path: Optional[str] = None
    role: str = "result_image"
    kind: str = "remote"
    width: Optional[int] = None
    height: Optional[int] = None
    file_sha256: Optional[str] = None

class ImportDraftCreate(BaseModel):
    source_type: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_ref: Optional[str] = None
    source_path: Optional[str] = None
    title: str
    model: str = "ChatGPT Image2"
    author: Optional[str] = None
    suggested_cluster_name: Optional[str] = None
    suggested_tags: List[str] = Field(default_factory=list)
    prompts: List[PromptIn] = Field(default_factory=list)
    media: List[ImportDraftMedia] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None

class ImportDraftRecord(ImportDraftCreate):
    id: str
    status: str
    duplicate_of_item_id: Optional[str] = None
    accepted_item_id: Optional[str] = None
    created_at: str
    updated_at: str
    accepted_at: Optional[str] = None

class ImportDraftList(BaseModel):
    drafts: List[ImportDraftRecord]
    total: int
    limit: int
    offset: int

class ImportDraftAcceptResult(BaseModel):
    draft: ImportDraftRecord
    item: ItemDetail

class RepositoryIngestRequest(BaseModel):
    path: str
    repo_url: Optional[str] = None
    source_ref: Optional[str] = None

class RepositoryIngestResult(BaseModel):
    id: str
    draft_count: int
    status: str
    drafts: List[ImportDraftRecord]
    log: str = ""

class GenerationJobCreate(BaseModel):
    source_item_id: Optional[str] = None
    mode: str = "text_to_image"
    provider: str = "manual_upload"
    model: Optional[str] = None
    prompt_language: Optional[str] = None
    prompt_text: str
    edited_prompt_text: Optional[str] = None
    reference_image_ids: List[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)

class GenerationJobRecord(GenerationJobCreate):
    id: str
    status: str
    result_path: Optional[str] = None
    result_width: Optional[int] = None
    result_height: Optional[int] = None
    result_sha256: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    accepted_image_id: Optional[str] = None
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    accepted_at: Optional[str] = None
    discarded_at: Optional[str] = None

class GenerationJobList(BaseModel):
    jobs: List[GenerationJobRecord]
    total: int
    limit: int
    offset: int

class GenerationJobAcceptResult(BaseModel):
    job: GenerationJobRecord
    item: ItemDetail
