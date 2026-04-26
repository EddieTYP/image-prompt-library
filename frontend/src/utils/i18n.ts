export type UiLanguage = 'zh_hant' | 'zh_hans' | 'en';

type TranslationKey =
  | 'filters' | 'searchAria' | 'searchPlaceholder' | 'config' | 'referencesShown' | 'searchChip' | 'collectionChip'
  | 'explore' | 'cards' | 'uiLanguage' | 'promptCopyLanguage' | 'promptCopyLanguageHelp'
  | 'globalThumbnails' | 'globalThumbnailsHelp' | 'focusThumbnails' | 'focusThumbnailsHelp'
  | 'calm' | 'balanced' | 'dense' | 'compact' | 'gallery' | 'full' | 'libraryPath' | 'databasePath'
  | 'libraryEmptyTitle' | 'libraryEmptyHelp' | 'noMatchingPrompts' | 'noMatchingPromptsHelp' | 'addFirstPrompt'
  | 'copyPrompt' | 'favorite' | 'saved' | 'edit' | 'noImage' | 'unclustered'
  | 'collections' | 'closeFilters' | 'searchCollections' | 'allReferences' | 'noCollectionsFound'
  | 'loading' | 'copySuccess' | 'copyFailed' | 'add' | 'close' | 'closeConfig'
  | 'newReference' | 'updateReference' | 'addPromptCard' | 'editPromptCard' | 'editorHelp'
  | 'title' | 'titlePlaceholder' | 'collection' | 'collectionPlaceholder' | 'tags' | 'tagsPlaceholder' | 'existingTagSuggestions'
  | 'traditionalChinesePrompt' | 'traditionalPromptPlaceholder' | 'simplifiedChinesePrompt' | 'simplifiedPromptPlaceholder' | 'englishPrompt' | 'englishPromptPlaceholder'
  | 'resultImageAlreadySaved' | 'resultImageRequired' | 'resultImageHelp' | 'referencePhotoOptional' | 'referencePhotoHelp'
  | 'deleteReference' | 'deleteReferenceConfirm' | 'cancel' | 'saving' | 'saveReference' | 'saveFailed'
  | 'primaryNavigation' | 'appHome' | 'currentFilters' | 'preferredPromptLanguage' | 'globalThumbnailBudget' | 'focusThumbnailBudget'
  | 'collectionFilters' | 'itemActions' | 'promptLanguage' | 'promptText' | 'source' | 'defaultModel' | 'localReference'
  | 'imageGeneratedFrom' | 'author' | 'sourceUrl' | 'notes' | 'addNote'
  | 'constellationGraph' | 'constellationControls' | 'zoomOut' | 'zoomIn' | 'resetView' | 'focusThumbnailsVisible' | 'thumbnailsVisible' | 'visible' | 'references' | 'more';

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
    explore: 'Explore', cards: 'Cards', uiLanguage: '介面語言', promptCopyLanguage: 'Prompt 複製語言', promptCopyLanguageHelp: '複製時先使用偏好 prompt，其後使用英文，再其後使用任何可用 prompt。',
    globalThumbnails: '全域縮圖', globalThumbnailsHelp: 'Explore 全部 collection 的整體密度。', focusThumbnails: '焦點縮圖', focusThumbnailsHelp: '選取 collection 周圍最多顯示的真實縮圖數量。',
    calm: '寬鬆', balanced: '平衡', dense: '密集', compact: '精簡', gallery: '圖庫', full: '完整', libraryPath: 'Library 路徑', databasePath: 'Database 路徑',
    libraryEmptyTitle: '你的 library 仍然是空的', libraryEmptyHelp: '新增第一個 prompt，或安裝 sample library 先瀏覽示例內容。', noMatchingPrompts: '找不到符合的 prompts', noMatchingPromptsHelp: '請嘗試另一個搜尋、清除篩選，或新增 prompt 參考。', addFirstPrompt: '新增第一個 prompt',
    copyPrompt: '複製 prompt', favorite: '收藏', saved: '已儲存', edit: '編輯', noImage: '沒有圖片', unclustered: '未分類',
    collections: 'Collections', closeFilters: '關閉篩選', searchCollections: '搜尋 collections', allReferences: '全部參考', noCollectionsFound: '找不到 collections',
    loading: '載入中…', copySuccess: 'Prompt 已複製', copyFailed: '複製失敗', add: '新增', close: '關閉', closeConfig: '關閉設定',
    newReference: '新增參考', updateReference: '更新參考', addPromptCard: '新增 prompt 卡片', editPromptCard: '編輯 prompt 卡片', editorHelp: '將完成圖片、collection、標籤和可重用的多語言 prompts 一併保存。',
    title: '標題', titlePlaceholder: '為此參考命名，方便日後辨識', collection: 'Collection', collectionPlaceholder: '例如：產品商業', tags: '標籤', tagsPlaceholder: 'poster, product, cinematic', existingTagSuggestions: '現有標籤建議',
    traditionalChinesePrompt: '繁體中文 prompt', traditionalPromptPlaceholder: '貼上繁體中文 prompt…', simplifiedChinesePrompt: '簡體中文 prompt', simplifiedPromptPlaceholder: '貼上簡體中文 prompt…', englishPrompt: '英文 prompt', englishPromptPlaceholder: '貼上英文 prompt…',
    resultImageAlreadySaved: '完成圖片已儲存', resultImageRequired: '完成圖片為必填', resultImageHelp: '必填的最終輸出圖片 · PNG、JPG、WEBP 或 GIF', referencePhotoOptional: '參考圖片可選', referencePhotoHelp: '此 prompt 的可選來源／參考圖片',
    deleteReference: '刪除參考', deleteReferenceConfirm: '刪除此參考？它將會被封存並從 library 隱藏。', cancel: '取消', saving: '儲存中…', saveReference: '儲存參考', saveFailed: '儲存失敗，請再試一次。',
    primaryNavigation: '主要導覽', appHome: 'Image Prompt Library 首頁', currentFilters: '目前篩選', preferredPromptLanguage: '偏好 prompt 語言', globalThumbnailBudget: '全域縮圖數量', focusThumbnailBudget: '焦點縮圖數量',
    collectionFilters: 'Collection 篩選', itemActions: '項目操作', promptLanguage: 'Prompt 語言', promptText: 'Prompt 文字', source: '來源', defaultModel: 'ChatGPT Image', localReference: '本機參考',
    imageGeneratedFrom: 'Image generated from', author: '作者', sourceUrl: '來源 URL', notes: '備註', addNote: '新增備註',
    constellationGraph: 'Prompt clusters 縮圖星座圖', constellationControls: '星座圖控制', zoomOut: '縮小', zoomIn: '放大', resetView: '重設', focusThumbnailsVisible: '張焦點縮圖', thumbnailsVisible: '張縮圖顯示中', visible: '顯示中', references: '個參考', more: '更多',
  },
  zh_hans: {
    filters: '筛选', searchAria: '搜索所有 prompts', searchPlaceholder: '搜索所有 prompts、标题、标签…', config: '设置', referencesShown: '个参考显示中', searchChip: '搜索', collectionChip: 'Collection',
    explore: 'Explore', cards: 'Cards', uiLanguage: '界面语言', promptCopyLanguage: 'Prompt 复制语言', promptCopyLanguageHelp: '复制时先使用偏好 prompt，然后使用英文，再然后使用任何可用 prompt。',
    globalThumbnails: '全局缩图', globalThumbnailsHelp: 'Explore 全部 collection 的整体密度。', focusThumbnails: '焦点缩图', focusThumbnailsHelp: '选中 collection 周围最多显示的真实缩图数量。',
    calm: '宽松', balanced: '平衡', dense: '密集', compact: '精简', gallery: '图库', full: '完整', libraryPath: 'Library 路径', databasePath: 'Database 路径',
    libraryEmptyTitle: '你的 library 还是空的', libraryEmptyHelp: '新增第一个 prompt，或安装 sample library 先浏览示例内容。', noMatchingPrompts: '找不到符合的 prompts', noMatchingPromptsHelp: '请尝试另一个搜索、清除筛选，或新增 prompt 参考。', addFirstPrompt: '新增第一个 prompt',
    copyPrompt: '复制 prompt', favorite: '收藏', saved: '已保存', edit: '编辑', noImage: '无图片', unclustered: '未分类',
    collections: 'Collections', closeFilters: '关闭筛选', searchCollections: '搜索 collections', allReferences: '全部参考', noCollectionsFound: '找不到 collections',
    loading: '加载中…', copySuccess: 'Prompt 已复制', copyFailed: '复制失败', add: '新增', close: '关闭', closeConfig: '关闭设置',
    newReference: '新增参考', updateReference: '更新参考', addPromptCard: '新增 prompt 卡片', editPromptCard: '编辑 prompt 卡片', editorHelp: '将完成图片、collection、标签和可复用的多语言 prompts 一并保存。',
    title: '标题', titlePlaceholder: '为此参考命名，方便日后辨识', collection: 'Collection', collectionPlaceholder: '例如：产品商业', tags: '标签', tagsPlaceholder: 'poster, product, cinematic', existingTagSuggestions: '现有标签建议',
    traditionalChinesePrompt: '繁体中文 prompt', traditionalPromptPlaceholder: '贴上繁体中文 prompt…', simplifiedChinesePrompt: '简体中文 prompt', simplifiedPromptPlaceholder: '粘贴简体中文 prompt…', englishPrompt: '英文 prompt', englishPromptPlaceholder: '粘贴英文 prompt…',
    resultImageAlreadySaved: '完成图片已保存', resultImageRequired: '完成图片为必填', resultImageHelp: '必填的最终输出图片 · PNG、JPG、WEBP 或 GIF', referencePhotoOptional: '参考图片可选', referencePhotoHelp: '此 prompt 的可选来源／参考图片',
    deleteReference: '删除参考', deleteReferenceConfirm: '删除此参考？它将会被归档并从 library 隐藏。', cancel: '取消', saving: '保存中…', saveReference: '保存参考', saveFailed: '保存失败，请再试一次。',
    primaryNavigation: '主要导航', appHome: 'Image Prompt Library 首页', currentFilters: '当前筛选', preferredPromptLanguage: '偏好 prompt 语言', globalThumbnailBudget: '全局缩图数量', focusThumbnailBudget: '焦点缩图数量',
    collectionFilters: 'Collection 筛选', itemActions: '项目操作', promptLanguage: 'Prompt 语言', promptText: 'Prompt 文字', source: '来源', defaultModel: 'ChatGPT Image', localReference: '本地参考',
    imageGeneratedFrom: 'Image generated from', author: '作者', sourceUrl: '来源 URL', notes: '备注', addNote: '新增备注',
    constellationGraph: 'Prompt clusters 缩图星座图', constellationControls: '星座图控制', zoomOut: '缩小', zoomIn: '放大', resetView: '重置', focusThumbnailsVisible: '张焦点缩图', thumbnailsVisible: '张缩图显示中', visible: '显示中', references: '个参考', more: '更多',
  },
  en: {
    filters: 'Filters', searchAria: 'Search all prompts', searchPlaceholder: 'Search all prompts, titles, tags…', config: 'Config', referencesShown: 'references shown', searchChip: 'Search', collectionChip: 'Collection',
    explore: 'Explore', cards: 'Cards', uiLanguage: 'UI language', promptCopyLanguage: 'Prompt copy language', promptCopyLanguageHelp: 'Copy uses your preferred prompt first, then English, then any available prompt.',
    globalThumbnails: 'Global thumbnails', globalThumbnailsHelp: 'Overall Explore density across all clusters.', focusThumbnails: 'Focus thumbnails', focusThumbnailsHelp: 'Maximum real thumbnails around the selected cluster.',
    calm: 'Calm', balanced: 'Balanced', dense: 'Dense', compact: 'Compact', gallery: 'Gallery', full: 'Full', libraryPath: 'Library path', databasePath: 'Database path',
    libraryEmptyTitle: 'Your library is empty', libraryEmptyHelp: 'Add your first prompt, or install the sample library if you want demo content first.', noMatchingPrompts: 'No matching prompts', noMatchingPromptsHelp: 'Try another search, clear filters, or add a new prompt reference.', addFirstPrompt: 'Add your first prompt',
    copyPrompt: 'Copy prompt', favorite: 'Favorite', saved: 'Saved', edit: 'Edit', noImage: 'No image', unclustered: 'Unclustered',
    collections: 'Collections', closeFilters: 'Close filters', searchCollections: 'Search collections', allReferences: 'All references', noCollectionsFound: 'No collections found',
    loading: 'Loading…', copySuccess: 'Prompt copied', copyFailed: 'Copy failed', add: 'Add', close: 'Close', closeConfig: 'Close config',
    newReference: 'New reference', updateReference: 'Update reference', addPromptCard: 'Add prompt card', editPromptCard: 'Edit prompt card', editorHelp: 'Keep the finished result image, collection, tags, and reusable multilingual prompts together.',
    title: 'Title', titlePlaceholder: 'Give this reference a memorable name', collection: 'Collection', collectionPlaceholder: 'e.g. Product commercial', tags: 'Tags', tagsPlaceholder: 'poster, product, cinematic', existingTagSuggestions: 'Existing tag suggestions',
    traditionalChinesePrompt: 'Traditional Chinese prompt', traditionalPromptPlaceholder: 'Paste the Traditional Chinese prompt…', simplifiedChinesePrompt: 'Simplified Chinese prompt', simplifiedPromptPlaceholder: 'Paste the Simplified Chinese prompt…', englishPrompt: 'English prompt', englishPromptPlaceholder: 'Paste the English prompt…',
    resultImageAlreadySaved: 'Result image already saved', resultImageRequired: 'Result image required', resultImageHelp: 'Required finished output image · PNG, JPG, WEBP or GIF', referencePhotoOptional: 'Reference photo optional', referencePhotoHelp: 'Optional source/reference image for this prompt',
    deleteReference: 'Delete reference', deleteReferenceConfirm: 'Delete this reference? It will be archived and hidden from the library.', cancel: 'Cancel', saving: 'Saving…', saveReference: 'Save reference', saveFailed: 'Save failed. Please try again.',
    primaryNavigation: 'Primary navigation', appHome: 'Image Prompt Library home', currentFilters: 'Current filters', preferredPromptLanguage: 'Preferred prompt language', globalThumbnailBudget: 'Global thumbnail budget', focusThumbnailBudget: 'Focus thumbnail budget',
    collectionFilters: 'Collection filters', itemActions: 'Item actions', promptLanguage: 'Prompt language', promptText: 'Prompt text', source: 'Source', defaultModel: 'ChatGPT Image', localReference: 'Local reference',
    imageGeneratedFrom: 'Image generated from', author: 'Author', sourceUrl: 'Source URL', notes: 'Notes', addNote: 'Add note',
    constellationGraph: 'Prompt clusters thumbnail constellation graph', constellationControls: 'Constellation controls', zoomOut: 'Zoom out', zoomIn: 'Zoom in', resetView: 'Reset', focusThumbnailsVisible: 'focus thumbnails', thumbnailsVisible: 'thumbnails visible', visible: 'visible', references: 'references', more: 'more',
  },
};

export type Translator = (key: TranslationKey) => string;

export function makeTranslator(language: UiLanguage): Translator {
  return (key: TranslationKey) => TRANSLATIONS[language][key] || TRANSLATIONS.en[key] || key;
}
