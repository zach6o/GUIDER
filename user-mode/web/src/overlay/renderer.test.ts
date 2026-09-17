import { describe, expect, it } from 'vitest';
import { labelSide, labelTop, MarkPayload, pictureBox, place } from './renderer';

const mark = (box: [number, number, number, number]): MarkPayload =>
  ({ kind: 'circle', box, label: 'Download' });

describe('finding the picture inside the element', () => {
  it('matches the element when the shapes agree', () => {
    const box = pictureBox({ clientWidth: 800, clientHeight: 450 }, 1600, 900);
    expect(box).toEqual({ left: 0, top: 0, width: 800, height: 450 });
  });

  it('accounts for letterboxing rather than measuring the element', () => {
    // A 16:9 picture in a 4:3 element: bars top and bottom, and a mark placed
    // against the element would sit that far out.
    const box = pictureBox({ clientWidth: 800, clientHeight: 600 }, 1600, 900);
    expect(box.width).toBe(800);
    expect(box.height).toBe(450);
    expect(box.top).toBe(75);
  });

  it('degrades to the element before the video has dimensions', () => {
    const box = pictureBox({ clientWidth: 400, clientHeight: 300 }, 0, 0);
    expect(box).toEqual({ left: 0, top: 0, width: 400, height: 300 });
  });
});

describe('placing a mark', () => {
  const picture = { left: 0, top: 0, width: 1000, height: 500 };

  it('multiplies normalised coordinates by the picture', () => {
    const box = place(mark([0.1, 0.2, 0.3, 0.4]), picture)!;
    expect(box.left).toBeCloseTo(100);
    expect(box.top).toBeCloseTo(100);
    expect(box.width).toBeCloseTo(200);
    expect(box.height).toBeCloseTo(100);
  });

  it('survives a resize by changing only the multiplier', () => {
    const half = { left: 0, top: 0, width: 500, height: 250 };
    const first = place(mark([0.1, 0.2, 0.3, 0.4]), picture)!;
    const second = place(mark([0.1, 0.2, 0.3, 0.4]), half)!;
    expect(second.left).toBe(first.left / 2);
    expect(second.width).toBe(first.width / 2);
  });

  it('respects letterbox offsets', () => {
    const offset = { left: 20, top: 75, width: 800, height: 450 };
    const box = place(mark([0, 0, 0.5, 0.5]), offset)!;
    expect(box.left).toBeCloseTo(20);
    expect(box.top).toBeCloseTo(75);
    expect(box.width).toBeCloseTo(400);
    expect(box.height).toBeCloseTo(225);
  });

  it('drops a mark too small to read as guidance', () => {
    expect(place(mark([0.5, 0.5, 0.5005, 0.9]), picture)).toBeNull();
  });
});

describe('placing the label', () => {
  const picture = { left: 0, top: 0, width: 1000, height: 500 };

  it('sits above when there is room', () => {
    expect(labelSide({ left: 0, top: 200, width: 100, height: 40 }, picture)).toBe('above');
  });

  it('drops below when the target is at the top', () => {
    expect(labelSide({ left: 0, top: 4, width: 100, height: 40 }, picture)).toBe('below');
  });

  it('goes inside only when there is nowhere else', () => {
    expect(labelSide({ left: 0, top: 2, width: 100, height: 490 }, picture)).toBe('inside');
  });

  it('starts a label below the box where the box ends', () => {
    const box = { left: 0, top: 4, width: 100, height: 40 };
    expect(labelTop(box, 'below')).toBe(44);
  });

  it('leaves the rest of the lifting to the stylesheet', () => {
    const box = { left: 0, top: 200, width: 100, height: 40 };
    expect(labelTop(box, 'above')).toBe(200);
    expect(labelTop(box, 'inside')).toBe(200);
  });
});
