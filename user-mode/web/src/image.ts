import type { Box } from './types';

// Inspect container chunks before canvas flattens animation into a still frame.
export function isAnimated(bytes: Uint8Array): boolean {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const tag = (offset: number) => String.fromCharCode(...bytes.subarray(offset, offset + 4));
  if (bytes.length >= 8 && bytes[0] === 137 && tag(1) === 'PNG\r') {
    for (let offset = 8; offset + 12 <= bytes.length;) {
      const size = view.getUint32(offset);
      if (size > bytes.length - offset - 12) break;
      if (tag(offset + 4) === 'acTL') return true;
      offset += size + 12;
    }
  }
  if (bytes.length >= 12 && tag(0) === 'RIFF' && tag(8) === 'WEBP') {
    for (let offset = 12; offset + 8 <= bytes.length;) {
      const size = view.getUint32(offset + 4, true);
      if (size > bytes.length - offset - 8) break;
      const type = tag(offset);
      if (type === 'ANIM' || type === 'ANMF'
        || (type === 'VP8X' && size > 0 && (bytes[offset + 8] & 2) !== 0)) return true;
      offset += size + 8 + (size % 2);
    }
  }
  return false;
}

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
  if (isAnimated(new Uint8Array(await file.arrayBuffer()))) throw new Error('Choose a still image, not an animation.');
  const bitmap = await createImageBitmap(file).catch(() => { throw new Error('This image could not be opened.'); });
  const width = bitmap.width, height = bitmap.height;
  bitmap.close();
  if (Math.max(width, height) > 8192 || width * height > 20_000_000) throw new Error('Choose an image up to 20 megapixels and 8,192 pixels per side.');
  const clean = await editImage(file, { x: 0, y: 0, width, height }, 'crop');
  if (clean.size > 10 * 1024 * 1024) throw new Error('This image is too large after preparation. Choose a smaller image.');
  return clean;
}
