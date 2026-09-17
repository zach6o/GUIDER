import { describe, expect, it } from 'vitest';
import { isAnimated, validBox } from './image';

describe('animation detection before canvas decoding', () => {
  it('rejects APNG animation control chunks', () => {
    const bytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 0, 97, 99, 84, 76, 0, 0, 0, 0]);
    expect(isAnimated(bytes)).toBe(true);
  });
  it('rejects WebP animation flags', () => {
    const bytes = new Uint8Array(30);
    bytes.set(new TextEncoder().encode('RIFF'), 0);
    bytes.set(new TextEncoder().encode('WEBPVP8X'), 8);
    bytes[16] = 10;
    bytes[20] = 2;
    expect(isAnimated(bytes)).toBe(true);
    bytes[20] = 0;
    expect(isAnimated(bytes)).toBe(false);
  });
  it('does not scan arbitrary payload text for animation markers', () => {
    expect(isAnimated(new TextEncoder().encode('JPEG EXIF ANIM acTL'))).toBe(false);
    expect(isAnimated(new Uint8Array())).toBe(false);
  });
});

describe('privacy rectangle boundaries', () => {
  it('allows a full image crop', () => {
    expect(validBox({ x: 0, y: 0, width: 960, height: 400 }, 960, 400)).toBe(true);
  });
  it.each([
    { x: -1, y: 0, width: 40, height: 20 },
    { x: 95, y: 0, width: 10, height: 20 },
    { x: 0, y: 0, width: 0, height: 20 },
    { x: NaN, y: 0, width: 10, height: 20 },
    { x: 0, y: 0, width: 10, height: Infinity },
  ])('rejects an invalid or out-of-bounds area', box => {
    expect(validBox(box, 100, 100)).toBe(false);
  });
});
