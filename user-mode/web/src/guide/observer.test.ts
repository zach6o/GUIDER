import { describe, expect, it } from 'vitest';
import {
  MotionGate, SAMPLE_SIZE, differenceHash, downsample, hammingDistance,
  meanAbsoluteDifference, type Decision, type FrameLike,
} from './observer';

/** A flat grayscale frame, optionally with a bright rectangle drawn on it —
 *  the cheapest stand-in for "a dialog appeared". */
function frame(base = 40, box?: { x: number; y: number; w: number; h: number; value: number }): FrameLike {
  const width = 320, height = 200;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let index = 0; index < width * height; index++) {
    data[index * 4] = data[index * 4 + 1] = data[index * 4 + 2] = base;
    data[index * 4 + 3] = 255;
  }
  if (box) {
    for (let y = box.y; y < box.y + box.h; y++) {
      for (let x = box.x; x < box.x + box.w; x++) {
        const at = (y * width + x) * 4;
        data[at] = data[at + 1] = data[at + 2] = box.value;
      }
    }
  }
  return { data, width, height };
}

const STATIC = downsample(frame());
const DIALOG = downsample(frame(40, { x: 60, y: 40, w: 180, h: 110, value: 230 }));
const CARET = downsample(frame(40, { x: 10, y: 10, w: 2, h: 12, value: 200 }));

/** Feed a sequence of thumbnails at a fixed cadence and collect the decisions. */
function run(
  gate: MotionGate, frames: Uint8Array[], { start = 0, everyMs = 500, awaitingAction = true,
    budgetRemaining = 200 } = {},
): Decision[] {
  return frames.map((gray, index) =>
    gate.consider(gray, start + index * everyMs, { awaitingAction, budgetRemaining }));
}

const repeat = (gray: Uint8Array, times: number) => Array.from({ length: times }, () => gray);
const admitted = (decisions: Decision[]) => decisions.filter(d => d === 'admit').length;

describe('reducing a frame', () => {
  it('produces a fixed-size thumbnail whatever the source size', () => {
    expect(downsample(frame()).length).toBe(SAMPLE_SIZE * SAMPLE_SIZE);
    expect(downsample({ data: new Uint8ClampedArray(4 * 4 * 4), width: 4, height: 4 }).length)
      .toBe(SAMPLE_SIZE * SAMPLE_SIZE);
  });

  it('reports no difference between identical frames', () => {
    expect(meanAbsoluteDifference(STATIC, downsample(frame()))).toBe(0);
  });

  it('reports a large difference when a dialog appears', () => {
    expect(meanAbsoluteDifference(STATIC, DIALOG)).toBeGreaterThan(10);
  });

  it('barely notices a caret', () => {
    expect(meanAbsoluteDifference(STATIC, CARET)).toBeLessThan(2.2);
  });
});

describe('the difference hash', () => {
  it('matches a frame against itself', () => {
    expect(hammingDistance(differenceHash(STATIC), differenceHash(downsample(frame())))).toBe(0);
  });

  it('separates two different frames', () => {
    expect(hammingDistance(differenceHash(STATIC), differenceHash(DIALOG))).toBeGreaterThan(0);
  });

  it('survives a uniform brightness shift that mean difference would flag', () => {
    const brighter = downsample(frame(70));
    expect(meanAbsoluteDifference(STATIC, brighter)).toBeGreaterThan(20);
    expect(hammingDistance(differenceHash(STATIC), differenceHash(brighter))).toBe(0);
  });
});

describe('the exit gate', () => {
  it('admits nothing at all from a static screen for a full minute', () => {
    // 120 frames at 500 ms is one minute of someone reading.
    const decisions = run(new MotionGate(), repeat(STATIC, 120));
    expect(admitted(decisions)).toBe(0);
    expect(decisions.every(decision => decision === 'ignored')).toBe(true);
  });

  it('admits exactly one frame for one scripted UI change', () => {
    const gate = new MotionGate();
    const decisions = run(gate, [
      ...repeat(STATIC, 10),   // reading
      DIALOG,                  // the dialog opens
      ...repeat(DIALOG, 20),   // and stays open
    ]);
    expect(admitted(decisions)).toBe(1);
    expect(gate.admittedRecently(15_000)).toBe(1);
  });
});

describe('settling', () => {
  it('does not admit until the change has held still', () => {
    const gate = new MotionGate();
    const decisions = run(gate, [STATIC, DIALOG, DIALOG]);
    // 500 ms after the change is inside the 700 ms settle window.
    expect(decisions).toEqual(['ignored', 'settling', 'settling']);
  });

  it('counts an animation as one change, not one per frame', () => {
    const gate = new MotionGate();
    const moving = [
      downsample(frame(40, { x: 10, y: 10, w: 120, h: 80, value: 200 })),
      downsample(frame(40, { x: 30, y: 10, w: 120, h: 80, value: 200 })),
      downsample(frame(40, { x: 50, y: 10, w: 120, h: 80, value: 200 })),
      downsample(frame(40, { x: 70, y: 10, w: 120, h: 80, value: 200 })),
    ];
    const decisions = run(gate, [STATIC, ...moving, ...repeat(moving[3], 6)]);
    expect(admitted(decisions)).toBe(1);
  });

  it('treats a screen returning to its previous look as a change worth seeing', () => {
    // A dialog that opens and closes is back where it started, but closing it may
    // be exactly the step completing. The gate deliberately does not suppress
    // that: losing the transition that signals completion is worse than one call.
    const gate = new MotionGate();
    const decisions = run(gate, [STATIC, DIALOG, STATIC, ...repeat(STATIC, 6)]);
    expect(admitted(decisions)).toBe(1);
  });
});

describe('keeping tier 2 affordable', () => {
  it('throttles a second change that arrives too soon', () => {
    const gate = new MotionGate({ minIntervalMs: 4000 });
    const decisions = run(gate, [
      ...repeat(STATIC, 2), DIALOG, ...repeat(DIALOG, 2),   // admits at ~2000 ms
      STATIC, ...repeat(STATIC, 2),                          // changes again at ~2500 ms
    ]);
    expect(admitted(decisions)).toBe(1);
    expect(decisions).toContain('throttled');
  });

  it('admits the second change once the interval has passed', () => {
    const gate = new MotionGate({ minIntervalMs: 4000 });
    run(gate, [STATIC, DIALOG, ...repeat(DIALOG, 2)]);
    const later = run(gate, [STATIC, ...repeat(STATIC, 3)], { start: 20_000 });
    expect(admitted(later)).toBe(1);
  });

  it('never exceeds its frames-per-minute ceiling', () => {
    const gate = new MotionGate({ minIntervalMs: 0, maxFramesPerMinute: 3 });
    // Alternate every settle window for a minute: far more changes than allowed.
    const frames: Uint8Array[] = [];
    for (let index = 0; index < 60; index++) {
      frames.push(index % 4 < 2 ? STATIC : DIALOG);
    }
    expect(admitted(run(gate, frames))).toBeLessThanOrEqual(3);
  });

  it('stops admitting when the session budget is gone', () => {
    const gate = new MotionGate();
    const decisions = run(gate, [STATIC, DIALOG, ...repeat(DIALOG, 3)], { budgetRemaining: 0 });
    expect(admitted(decisions)).toBe(0);
    expect(decisions).toContain('exhausted');
  });
});

describe('only while a step is waiting', () => {
  it('admits nothing when no step is awaiting the user', () => {
    const gate = new MotionGate();
    const decisions = run(gate, [STATIC, DIALOG, ...repeat(DIALOG, 4)], { awaitingAction: false });
    expect(admitted(decisions)).toBe(0);
    expect(decisions.every(decision => decision === 'ignored')).toBe(true);
  });

  it('does not report the whole paused period as one change on resume', () => {
    const gate = new MotionGate();
    run(gate, [STATIC, DIALOG], { awaitingAction: false });
    // Resuming takes a fresh baseline: the next frame is not "a change".
    const resumed = run(gate, [DIALOG, ...repeat(DIALOG, 4)], { start: 60_000 });
    expect(admitted(resumed)).toBe(0);
  });
});

describe('what the gate holds on to', () => {
  it('keeps one thumbnail and no frame history', () => {
    const gate = new MotionGate();
    run(gate, [STATIC, DIALOG, ...repeat(DIALOG, 4)]);
    const held = Object.values(gate as unknown as Record<string, unknown>)
      .filter(value => value instanceof Uint8Array);
    expect(held).toHaveLength(1);
    expect((held[0] as Uint8Array).length).toBe(SAMPLE_SIZE * SAMPLE_SIZE);
  });

  it('forgets its baseline on reset', () => {
    const gate = new MotionGate();
    run(gate, [STATIC, DIALOG, ...repeat(DIALOG, 4)]);
    gate.reset();
    expect(run(gate, [DIALOG], { start: 30_000 })).toEqual(['ignored']);
  });
});
