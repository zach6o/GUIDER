import { describe, expect, it } from 'vitest';
import { validBox } from './image';

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
