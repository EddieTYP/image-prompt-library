export type ViewMode = 'explore' | 'cards';
export type UploadImageRole = 'result_image' | 'reference_image';
export type UiLanguage = 'zh_hant' | 'zh_hans' | 'en';
export interface PromptRecord { id: string; item_id: string; language: string; text: string; is_primary: boolean; is_original?: boolean; provenance?: Record<string, unknown> }
export interface ImageRecord { id: string; item_id: string; original_path: string; thumb_path?: string; preview_path?: string; width?: number; height?: number; role?: UploadImageRole }
export interface ClusterRecord { id: string; name: string; names?: Partial<Record<UiLanguage, string>>; description?: string; count: number; preview_images: string[] }
export interface TagRecord { id: string; name: string; kind: string; count: number }
export interface AppConfig { version: string; library_path: string; database_path: string; preferred_prompt_language?: string; features?: { camelot?: { percival?: boolean } } }
export interface AppUpdateStatus { current_version: string; latest_version?: string | null; update_available: boolean; release_url?: string | null; update_command?: string | null; checked_at: string; error?: string | null; service_mode: string; active_generation_jobs: { running: number; queued: number }; can_restart: boolean; requires_manual_restart: boolean }
export interface AppUpdateRequest { target_version?: string | null; cancel_active_generation_jobs: boolean }
export interface AppUpdateResult { status: string; target_version: string; cancelled_generation_jobs: number; restart_mode: string; requires_manual_restart: boolean; message: string; stdout?: string; stderr?: string }
export interface CleanupFileRecord { path: string; bytes: number; reason: string }
export interface CleanupImageRecord { image_id: string; item_id: string; path?: string | null; reason: string }
export interface CleanupPreview { broken_image_records: CleanupImageRecord[]; unreferenced_files: CleanupFileRecord[]; total_bytes: number; preview_token: string }
export interface CleanupApplyRequest { preview_token: string; remove_broken_image_records: boolean; remove_unreferenced_files: boolean }
export interface CleanupApplyResult extends CleanupPreview { removed_broken_image_records: number; removed_unreferenced_files: number }
export interface GenerationProviderFeatures { text_to_image?: boolean; text_reference_to_image?: boolean; image_edit?: boolean; manual_result_upload?: boolean }
export interface GenerationProviderStatus { provider: string; display_name: string; auth_mode?: string; optional: boolean; configured: boolean; authenticated: boolean; available: boolean; state: string; status?: 'ready' | 'unavailable' | 'login_required' | 'auth_error'; message?: string | null; can_generate?: boolean; reason?: string | null; features: GenerationProviderFeatures; token_present?: boolean; account_id?: string | null; auth_store_path?: string; orchestrator_models?: string[]; default_orchestrator_model?: string; image_models?: string[]; default_image_model?: string }
export interface CodexNativeAuthStart { device_auth_id: string; user_code: string; verification_url: string; verification_uri?: string; verification_uri_complete?: string; expires_in?: number; interval?: number }
export interface CodexNativeAuthPending { provider: string; auth_mode?: string; status: 'pending' }
export type CodexNativeAuthPollResponse = GenerationProviderStatus | CodexNativeAuthPending
export interface CodexNativeAuthPollRequest { device_auth_id: string; user_code: string }
export interface GenerationJobCreate { source_item_id?: string; mode?: string; provider: string; model?: string | null; prompt_language?: string | null; prompt_text: string; edited_prompt_text?: string | null; reference_image_ids?: string[]; parameters?: Record<string, unknown> }
export interface GenerationJobRecord extends GenerationJobCreate { id: string; status: string; result_path?: string | null; result_width?: number | null; result_height?: number | null; result_sha256?: string | null; metadata?: Record<string, unknown>; error?: string | null; accepted_image_id?: string | null; created_at: string; updated_at: string; started_at?: string | null; completed_at?: string | null; accepted_at?: string | null; discarded_at?: string | null; cancelled_at?: string | null }
export interface GenerationJobList { jobs: GenerationJobRecord[]; total: number; limit: number; offset: number }
export interface GenerationJobAcceptAsNewItemPayload { title?: string; cluster_name?: string; tags?: string[]; prompts?: Array<{language: string; text: string; is_primary?: boolean; is_original?: boolean; provenance?: Record<string, unknown>}>; model?: string; source_name?: string; source_url?: string; author?: string; notes?: string }
export interface GenerationJobAcceptResult { job: GenerationJobRecord; item: ItemDetail }
export interface GenerationJobRetryResult { discarded_job: GenerationJobRecord; retry_job: GenerationJobRecord }
export interface ItemSummary { id: string; title: string; demo_titles?: Partial<Record<UiLanguage, string>>; slug: string; model: string; source_name?: string; source_url?: string; cluster?: ClusterRecord; tags: TagRecord[]; prompts: PromptRecord[]; prompt_snippet?: string; first_image?: ImageRecord; rating: number; favorite: boolean; archived: boolean; updated_at: string; created_at: string }
export interface ItemDetail extends ItemSummary { images: ImageRecord[]; notes?: string; author?: string }
export interface ItemList { items: ItemSummary[]; total: number; limit: number; offset: number }
export type ItemBatchAction = 'delete' | 'archive' | 'unarchive' | 'favorite' | 'unfavorite' | 'add_tags' | 'remove_tags' | 'move_collection'
export interface ItemBatchRequest { item_ids: string[]; action: ItemBatchAction; tags?: string[]; cluster_id?: string; cluster_name?: string }
export interface ItemBatchResult { requested: number; changed: number; skipped: number; failed: number; item_ids: string[]; errors: Record<string, string> }
export type ItemSortMode = 'updated_desc' | 'created_desc' | 'created_asc' | 'title_asc' | 'title_desc' | 'source_asc' | 'model_asc'
export interface ItemCreate { title: string; cluster_name?: string; tags?: string[]; prompts: Array<{language: string; text: string; is_primary?: boolean; is_original?: boolean; provenance?: Record<string, unknown>}>; model?: string; source_name?: string; source_url?: string; author?: string; notes?: string }
export interface ImportPrompt { language: string; text: string; is_primary?: boolean; is_original?: boolean; provenance?: Record<string, unknown> }
export interface ImportDraftCreate { source_type: string; source_name?: string; source_url?: string; source_ref?: string; source_path?: string; title: string; model?: string; author?: string; suggested_cluster_name?: string; suggested_tags: string[]; prompts: ImportPrompt[]; media: Array<Record<string, unknown>>; warnings: string[]; confidence?: number }
export interface ImportDraftRecord extends ImportDraftCreate { id: string; status: string; duplicate_of_item_id?: string; accepted_item_id?: string; created_at: string; updated_at: string; accepted_at?: string }
export interface ImportDraftAcceptResult { draft: ImportDraftRecord; item: ItemDetail }
