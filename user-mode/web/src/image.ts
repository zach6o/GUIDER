import type { Box } from './types';

export function validBox(box: Box, width: number, height: number): boolean {
  return Object.values(box).every(Number.isFinite) && box.x >= 0 && box.y >= 0
    && box.width > 0 && box.height > 0 && box.x + box.width <= width && box.y + box.height <= height;
}

export async function editImage(blob: Blob, box: Box, mode: 'crop' | 'hide'): Promise<Blob> {
  const bitmap = await createImageBitmap(blob);
  try {
    if (!validBox(box, bitmap.width, bitmap.height)) throw new Error('Keep the selected area inside the image.');
    const canvas = document.createElement('canvas');
    canvas.width = mode === 'crop' ? box.width : bitmap.width;
    canvas.height = mode === 'crop' ? box.height : bitmap.height;
    const ctx = canvas.getContext('2d')!;
    if (mode === 'crop') ctx.drawImage(bitmap, box.x, box.y, box.width, box.height, 0, 0, box.width, box.height);
    else { ctx.drawImage(bitmap, 0, 0); ctx.fillStyle = '#111815'; ctx.fillRect(box.x, box.y, box.width, box.height); }
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(
      result => result ? resolve(result) : reject(new Error('Could not prepare the image.')), 'image/png',
    ));
  } finally { bitmap.close(); }
}

export async function prepareImage(file: Blob): Promise<Blob> {
  if (file.size > 10 * 1024 * 1024) throw new Error('Choose an image smaller than 10 MiB.');
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('Choose a PNG, JPEG or WebP image.');
  const bitmap = await createImageBitmap(file).catch(() => { throw new Error('This image could not be opened.'); });
  const width = bitmap.width, height = bitmap.height;
  bitmap.close();
  if (Math.max(width, height) > 8192 || width * height > 20_000_000) throw new Error('Choose an image up to 20 megapixels and 8,192 pixels per side.');
  const clean = await editImage(file, { x: 0, y: 0, width, height }, 'crop');
  if (clean.size > 10 * 1024 * 1024) throw new Error('This image is too large after preparation. Choose a smaller image.');
  return clean;
}
