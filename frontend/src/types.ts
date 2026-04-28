export type ViewMode = 'explore' | 'cards';
export type UploadImageRole = 'result_image' | 'reference_image';
export type UiLanguage = 'zh_hant' | 'zh_hans' | 'en';
export interface PromptRecord { id: string; item_id: string; language: string; text: string; is_primary: boolean; is_original?: boolean; provenance?: Record<string, unknown> }
export interface ImageRecord { id: string; item_id: string; original_path: string; thumb_path?: string; preview_path?: string; width?: number; height?: number; role?: UploadImageRole }
export interface ClusterRecord { id: string; name: string; names?: Partial<Record<UiLanguage, string>>; description?: string; count: number; preview_images: string[] }
export interface TagRecord { id: string; name: string; kind: string; count: number }
export interface AppConfig { version: string; library_path: string; database_path: string; preferred_prompt_language?: string }
export interface GenerationProviderFeatures { text_to_image?: boolean; text_reference_to_image?: boolean; image_edit?: boolean; manual_result_upload?: boolean }
export interface GenerationProviderStatus { provider: string; display_name: string; auth_mode?: string; optional: boolean; configured: boolean; authenticated: boolean; available: boolean; state: string; reason?: string | null; features: GenerationProviderFeatures; token_present?: boolean; account_id?: string | null; auth_store_path?: string }
export interface CodexNativeAuthStart { device_auth_id: string; user_code: string; verification_url: string; verification_uri?: string; verification_uri_complete?: string; expires_in?: number; interval?: number }
export interface CodexNativeAuthPending { provider: string; auth_mode?: string; status: 'pending' }
export type CodexNativeAuthPollResponse = GenerationProviderStatus | CodexNativeAuthPending
export interface CodexNativeAuthPollRequest { device_auth_id: string; user_code: string }
export interface ItemSummary { id: string; title: string; slug: string; model: string; source_name?: string; source_url?: string; cluster?: ClusterRecord; tags: TagRecord[]; prompts: PromptRecord[]; prompt_snippet?: string; first_image?: ImageRecord; rating: number; favorite: boolean; archived: boolean; updated_at: string; created_at: string }
export interface ItemDetail extends ItemSummary { images: ImageRecord[]; notes?: string; author?: string }
export interface ItemList { items: ItemSummary[]; total: number; limit: number; offset: number }
export interface ItemCreate { title: string; cluster_name?: string; tags?: string[]; prompts: Array<{language: string; text: string; is_primary?: boolean; is_original?: boolean; provenance?: Record<string, unknown>}>; model?: string; source_name?: string; source_url?: string; author?: string; notes?: string }
