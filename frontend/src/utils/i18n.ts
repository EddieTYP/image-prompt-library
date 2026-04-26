export type UiLanguage = 'zh_hant' | 'zh_hans' | 'en';

type TranslationKey =
  | 'filters' | 'searchAria' | 'searchPlaceholder' | 'config' | 'referencesShown' | 'searchChip' | 'collectionChip'
  | 'explore' | 'cards' | 'uiLanguage' | 'promptCopyLanguage' | 'promptCopyLanguageHelp'
  | 'globalThumbnails' | 'globalThumbnailsHelp' | 'focusThumbnails' | 'focusThumbnailsHelp'
  | 'calm' | 'balanced' | 'dense' | 'compact' | 'gallery' | 'full' | 'libraryPath' | 'databasePath'
  | 'libraryEmptyTitle' | 'libraryEmptyHelp' | 'noMatchingPrompts' | 'noMatchingPromptsHelp' | 'addFirstPrompt'
  | 'copyPrompt' | 'favorite' | 'saved' | 'edit' | 'noImage' | 'unclustered'
  | 'collections' | 'closeFilters' | 'searchCollections' | 'allReferences' | 'noCollectionsFound'
  | 'loading' | 'copySuccess' | 'copyFailed' | 'add' | 'close' | 'closeConfig';

export const UI_LANGUAGE_LABELS: Record<UiLanguage, string> = {
  zh_hant: '繁體中文',
  zh_hans: '简体中文',
  en: 'English',
};

export const DEFAULT_UI_LANGUAGE: UiLanguage = 'zh_hant';

export function normalizeUiLanguage(value?: string | null): UiLanguage {
  if (value === 'zh_hant' || value === 'zh_hans' || value === 'en') return value;
  return DEFAULT_UI_LANGUAGE;
}

const TRANSLATIONS: Record<UiLanguage, Record<TranslationKey, string>> = {
  zh_hant: {
    filters: '篩選', searchAria: '搜尋所有 prompts', searchPlaceholder: '搜尋所有 prompts、標題、標籤…', config: '設定', referencesShown: '個參考顯示中', searchChip: '搜尋', collectionChip: 'Collection',
    explore: 'Explore', cards: 'Cards', uiLanguage: '介面語言', promptCopyLanguage: 'Prompt 複製語言', promptCopyLanguageHelp: '複製時先用偏好 prompt，之後英文，再之後任何可用 prompt。',
    globalThumbnails: 'Global thumbnails', globalThumbnailsHelp: 'Explore 全部 collection 嘅整體密度。', focusThumbnails: 'Focus thumbnails', focusThumbnailsHelp: '選中 collection 周圍最多顯示幾多張真實縮圖。',
    calm: 'Calm', balanced: 'Balanced', dense: 'Dense', compact: 'Compact', gallery: 'Gallery', full: 'Full', libraryPath: 'Library path', databasePath: 'Database path',
    libraryEmptyTitle: '你的 library 仍然係空', libraryEmptyHelp: '新增第一個 prompt 或匯入 OpenNana export，就可以開始瀏覽。', noMatchingPrompts: '搵唔到符合嘅 prompts', noMatchingPromptsHelp: '試吓另一個搜尋、清除篩選，或者新增 prompt 參考。', addFirstPrompt: '新增第一個 prompt',
    copyPrompt: '複製 prompt', favorite: 'Favorite', saved: '已儲存', edit: '編輯', noImage: '無圖片', unclustered: '未分類',
    collections: 'Collections', closeFilters: '關閉篩選', searchCollections: '搜尋 collections', allReferences: '全部參考', noCollectionsFound: '搵唔到 collections',
    loading: '載入中…', copySuccess: 'Prompt 已複製', copyFailed: '複製失敗', add: '新增', close: '關閉', closeConfig: '關閉設定',
  },
  zh_hans: {
    filters: '筛选', searchAria: '搜索所有 prompts', searchPlaceholder: '搜索所有 prompts、标题、标签…', config: '设置', referencesShown: '个参考显示中', searchChip: '搜索', collectionChip: 'Collection',
    explore: 'Explore', cards: 'Cards', uiLanguage: '界面语言', promptCopyLanguage: 'Prompt 复制语言', promptCopyLanguageHelp: '复制时先用偏好 prompt，然后英文，再然后任何可用 prompt。',
    globalThumbnails: 'Global thumbnails', globalThumbnailsHelp: 'Explore 全部 collection 的整体密度。', focusThumbnails: 'Focus thumbnails', focusThumbnailsHelp: '选中 collection 周围最多显示多少张真实缩图。',
    calm: 'Calm', balanced: 'Balanced', dense: 'Dense', compact: 'Compact', gallery: 'Gallery', full: 'Full', libraryPath: 'Library path', databasePath: 'Database path',
    libraryEmptyTitle: '你的 library 还是空的', libraryEmptyHelp: '新增第一个 prompt 或导入 OpenNana export，就可以开始浏览。', noMatchingPrompts: '找不到符合的 prompts', noMatchingPromptsHelp: '试试另一个搜索、清除筛选，或者新增 prompt 参考。', addFirstPrompt: '新增第一个 prompt',
    copyPrompt: '复制 prompt', favorite: 'Favorite', saved: '已保存', edit: '编辑', noImage: '无图片', unclustered: '未分类',
    collections: 'Collections', closeFilters: '关闭筛选', searchCollections: '搜索 collections', allReferences: '全部参考', noCollectionsFound: '找不到 collections',
    loading: '加载中…', copySuccess: 'Prompt 已复制', copyFailed: '复制失败', add: '新增', close: '关闭', closeConfig: '关闭设置',
  },
  en: {
    filters: 'Filters', searchAria: 'Search all prompts', searchPlaceholder: 'Search all prompts, titles, tags…', config: 'Config', referencesShown: 'references shown', searchChip: 'Search', collectionChip: 'Collection',
    explore: 'Explore', cards: 'Cards', uiLanguage: 'UI language', promptCopyLanguage: 'Prompt copy language', promptCopyLanguageHelp: 'Copy uses your preferred prompt first, then English, then any available prompt.',
    globalThumbnails: 'Global thumbnails', globalThumbnailsHelp: 'Overall Explore density across all clusters.', focusThumbnails: 'Focus thumbnails', focusThumbnailsHelp: 'Maximum real thumbnails around the selected cluster.',
    calm: 'Calm', balanced: 'Balanced', dense: 'Dense', compact: 'Compact', gallery: 'Gallery', full: 'Full', libraryPath: 'Library path', databasePath: 'Database path',
    libraryEmptyTitle: 'Your library is empty', libraryEmptyHelp: 'Add your first prompt or import an OpenNana export to start exploring.', noMatchingPrompts: 'No matching prompts', noMatchingPromptsHelp: 'Try another search, clear filters, or add a new prompt reference.', addFirstPrompt: 'Add your first prompt',
    copyPrompt: 'Copy prompt', favorite: 'Favorite', saved: 'Saved', edit: 'Edit', noImage: 'No image', unclustered: 'Unclustered',
    collections: 'Collections', closeFilters: 'Close filters', searchCollections: 'Search collections', allReferences: 'All references', noCollectionsFound: 'No collections found',
    loading: 'Loading…', copySuccess: 'Prompt copied', copyFailed: 'Copy failed', add: 'Add', close: 'Close', closeConfig: 'Close config',
  },
};

export type Translator = (key: TranslationKey) => string;

export function makeTranslator(language: UiLanguage): Translator {
  return (key: TranslationKey) => TRANSLATIONS[language][key] || TRANSLATIONS.en[key] || key;
}
