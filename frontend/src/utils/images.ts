import type { ImageRecord } from '../types';

export function selectPrimaryImage(images: Array<ImageRecord | undefined>) {
  return images.find(image => image?.role === 'result_image') || images.find(Boolean);
}

export function imageDisplayPath(image?: ImageRecord) {
  return image?.preview_path || image?.original_path || image?.thumb_path || '';
}

export function imageThumbnailPath(image?: ImageRecord) {
  return image?.thumb_path || image?.preview_path || '';
}

export function imageHeroPath(image?: ImageRecord) {
  return image?.preview_path || image?.original_path || image?.thumb_path || '';
}

export function imageOriginalPath(image?: ImageRecord) {
  return image?.original_path || image?.preview_path || image?.thumb_path || '';
}

export function downloadFileName(title: string, path?: string | null) {
  const extension = path?.split('?')[0]?.split('#')[0]?.split('.').pop() || 'png';
  const safeTitle = title.trim().toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff\u3400-\u4dbf]+/gi, '-').replace(/^-+|-+$/g, '') || 'image';
  return `${safeTitle}.${extension}`;
}
