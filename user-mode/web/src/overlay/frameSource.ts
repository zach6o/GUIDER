/**
 * The only place a watched window becomes pixels.
 *
 * Two jobs, deliberately separate. `sample` produces the 64x64 grayscale
 * thumbnail the motion gate compares, which never leaves this machine.
 * `encode` produces the frame that does leave, with every hidden area painted
 * out first — the hiding happens here, before encoding, because a mask applied
 * anywhere else would mean the pixels had already travelled.
 */

import { downsample, SAMPLE_SIZE } from '../guide/observer';
import type { FrameSource } from '../guide/watching';
import type { Box } from '../types';

/** Longest edge sent. Plenty to read a dialog, and a fraction of the cost of a
 *  full-resolution frame; the server refuses anything over 2,560 anyway. */
export const MAX_SENT_EDGE = 1280;
const JPEG_QUALITY = 0.8;

/** Hidden areas, in fractions of the window, so they survive a resize. */
export interface MaskArea { x: number; y: number; width: number; height: number }

export function normalizeBox(box: Box, width: number, height: number): MaskArea {
  return {
    x: box.x / width, y: box.y / height,
    width: box.width / width, height: box.height / height,
  };
}

export function createFrameSource(
  video: HTMLVideoElement, masks: () => readonly MaskArea[],
): FrameSource {
  const thumbnail = document.createElement('canvas');
  thumbnail.width = thumbnail.height = SAMPLE_SIZE;
  const frame = document.createElement('canvas');

  const ready = () => video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0;

  return {
    sample() {
      if (!ready()) return null;
      const context = thumbnail.getContext('2d', { willReadFrequently: true });
      if (!context) return null;
      context.drawImage(video, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
      const pixels = context.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
      return downsample(
        { data: pixels.data, width: SAMPLE_SIZE, height: SAMPLE_SIZE }, SAMPLE_SIZE,
      );
    },

    async encode() {
      if (!ready()) throw new Error('The watched window is not ready.');
      const scale = Math.min(1, MAX_SENT_EDGE / Math.max(video.videoWidth, video.videoHeight));
      frame.width = Math.round(video.videoWidth * scale);
      frame.height = Math.round(video.videoHeight * scale);
      const context = frame.getContext('2d');
      if (!context) throw new Error('This browser cannot prepare a frame.');
      context.drawImage(video, 0, 0, frame.width, frame.height);
      // Opaque, not blurred: a reversible mask is not a mask.
      context.fillStyle = '#000';
      for (const area of masks()) {
        context.fillRect(
          Math.round(area.x * frame.width), Math.round(area.y * frame.height),
          Math.round(area.width * frame.width), Math.round(area.height * frame.height),
        );
      }
      const url = frame.toDataURL('image/jpeg', JPEG_QUALITY);
      // Drop the backing pixels as soon as the string exists.
      frame.width = frame.height = 0;
      return url.slice(url.indexOf(',') + 1);
    },
  };
}
