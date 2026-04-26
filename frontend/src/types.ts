export type ViewMode = 'explore' | 'cards';
export type UploadImageRole = 'result_image' | 'reference_image';
export interface PromptRecord { id: string; item_id: string; language: string; text: string; is_primary: boolean }
export interface ImageRecord { id: string; item_id: string; original_path: string; thumb_path?: string; preview_path?: string; width?: number; height?: number; role?: UploadImageRole }
export interface ClusterRecord { id: string; name: string; description?: string; count: number; preview_images: string[] }
export interface TagRecord { id: string; name: string; kind: string; count: number }
export interface AppConfig { version: string; library_path: string; database_path: string; preferred_prompt_language?: string }
export interface ItemSummary { id: string; title: string; slug: string; model: string; source_name?: string; source_url?: string; cluster?: ClusterRecord; tags: TagRecord[]; prompts: PromptRecord[]; prompt_snippet?: string; first_image?: ImageRecord; rating: number; favorite: boolean; archived: boolean; updated_at: string; created_at: string }
export interface ItemDetail extends ItemSummary { images: ImageRecord[]; notes?: string; author?: string }
export interface ItemList { items: ItemSummary[]; total: number; limit: number; offset: number }
export interface ItemCreate { title: string; cluster_name?: string; tags?: string[]; prompts: Array<{language: string; text: string; is_primary?: boolean}>; model?: string; source_name?: string; source_url?: string; author?: string; notes?: string }
