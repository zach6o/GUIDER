import { describe, expect, it } from 'vitest';
import { accepts, guideReducer, initialGuideState, isComplete, type GuideState } from './engine';

const steps = [
  { id: 'one', target: 'First control' },
  { id: 'two', target: 'Second control' },
] as const;

const reduce = (state: GuideState, ...actions: Parameters<typeof guideReducer>[2][]) =>
  actions.reduce((current, action) => guideReducer(steps, current, action), state);

const claimed = reduce(initialGuideState, { type: 'act', target: 'one' });

describe('acting on a step', () => {
  it('claims the step without advancing it', () => {
    expect(claimed.phase).toBe('checking');
    expect(claimed.step).toBe(0);
    expect(isComplete(claimed)).toBe(false);
  });

  it('corrects a wrong action and stays on the step', () => {
    const wrong = reduce(initialGuideState, { type: 'act', target: 'two' });
    expect(wrong.correction).toBe('wrong_target');
    expect(wrong.phase).toBe('ready');
    expect(wrong.step).toBe(0);
  });

  it('cannot be claimed twice, so a repeat cannot skip ahead', () => {
    const again = reduce(claimed, { type: 'act', target: 'one' });
    expect(again).toEqual(claimed);
  });
});

describe('verification decides progress', () => {
  it('advances only on passing evidence', () => {
    const passed = reduce(claimed, { type: 'verify', passed: true });
    expect(passed.step).toBe(1);
    expect(passed.phase).toBe('ready');
  });

  it('returns to the same step when evidence is missing', () => {
    const failed = reduce(claimed, { type: 'verify', passed: false });
    expect(failed.step).toBe(0);
    expect(failed.phase).toBe('ready');
    expect(failed.correction).toBe('missing_evidence');
  });

  it('completes on the last step', () => {
    const done = reduce(
      claimed,
      { type: 'verify', passed: true },
      { type: 'act', target: 'two' },
      { type: 'verify', passed: true },
    );
    expect(isComplete(done)).toBe(true);
    expect(done.step).toBe(1);
  });

  it('is ignored unless a claim is outstanding', () => {
    expect(reduce(initialGuideState, { type: 'verify', passed: true })).toEqual(initialGuideState);
  });
});

describe('pausing', () => {
  const paused = reduce(initialGuideState, { type: 'pause' });

  it('refuses actions while paused', () => {
    expect(reduce(paused, { type: 'act', target: 'one' })).toEqual(paused);
    expect(accepts(paused, { type: 'act', target: 'one' })).toBe(false);
  });

  it('refuses a pending verification while paused', () => {
    const held = reduce(claimed, { type: 'pause' });
    expect(reduce(held, { type: 'verify', passed: true })).toEqual(held);
  });

  it('resumes from the same step, not from the start', () => {
    const resumed = reduce(claimed, { type: 'pause' }, { type: 'resume' });
    expect(resumed.phase).toBe('checking');
    expect(resumed.step).toBe(0);
  });
});

describe('restart', () => {
  it('returns to the first step', () => {
    const restarted = reduce(claimed, { type: 'verify', passed: true }, { type: 'restart' });
    expect(restarted).toEqual(initialGuideState);
  });

  it('is accepted even while paused', () => {
    expect(reduce(initialGuideState, { type: 'pause' }, { type: 'restart' }).paused).toBe(false);
  });
});
