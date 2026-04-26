import type { ImageRecord } from '../types';

export function selectPrimaryImage(images: Array<ImageRecord | undefined>) {
  return images.find(image => image?.role === 'result_image') || images.find(Boolean);
}

export function imageDisplayPath(image?: ImageRecord) {
  return image?.thumb_path || image?.preview_path || image?.original_path || '';
}

export function imageThumbnailPath(image?: ImageRecord) {
  return image?.thumb_path || image?.preview_path || '';
}

export function imageHeroPath(image?: ImageRecord) {
  return image?.preview_path || image?.original_path || image?.thumb_path || '';
}
