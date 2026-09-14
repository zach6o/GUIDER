import { describe, expect, it } from 'vitest';
import { IDLE_STEPS, IdleStage, IdleWatcher } from './idle';

function watcher() {
  const seen: IdleStage[] = [];
  let clock = 0;
  const instance = new IdleWatcher({ now: () => clock, onStage: step => seen.push(step.stage) });
  return {
    seen,
    instance,
    advance(ms: number) { clock += ms; instance.check(); },
  };
}

describe('staged quiet time', () => {
  it('says nothing while something is happening', () => {
    const { seen, advance } = watcher();
    advance(29_000);
    expect(seen).toEqual([]);
  });

  it('works through the stages in order, once each', () => {
    const { seen, advance } = watcher();
    advance(30_000);
    expect(seen).toEqual(['offer']);
    advance(1_000);
    // Still quiet, but that stage has already been said.
    expect(seen).toEqual(['offer']);
    advance(30_000);
    expect(seen).toEqual(['offer', 'remind']);
    advance(120_000);
    expect(seen).toEqual(['offer', 'remind', 'warn']);
    advance(120_000);
    expect(seen).toEqual(['offer', 'remind', 'warn', 'stop']);
  });

  it('starts over when something actually happens', () => {
    const { seen, instance, advance } = watcher();
    advance(60_000);
    expect(seen).toEqual(['offer', 'remind']);
    instance.activity();
    advance(29_000);
    expect(seen).toEqual(['offer', 'remind']);
    advance(1_000);
    // The quiet period restarted, so the first stage is due again.
    expect(seen).toEqual(['offer', 'remind', 'offer']);
  });

  it('stops counting once it has stopped watching', () => {
    const { seen, instance, advance } = watcher();
    advance(300_000);
    expect(seen).toContain('stop');
    instance.reset();
    advance(600_000);
    expect(seen.filter(stage => stage === 'stop')).toHaveLength(1);
  });
});

describe('what the copy claims', () => {
  it('describes what was observed, never what the user did', () => {
    for (const step of IDLE_STEPS) {
      const message = step.message.toLowerCase();
      // "You walked away" would be a guess: a browser cannot see the desk.
      expect(message).not.toContain('walked away');
      expect(message).not.toContain('you left');
      expect(message).not.toContain('away from');
    }
  });

  it('promises the place is kept, on both stages that could lose it', () => {
    const warn = IDLE_STEPS.find(step => step.stage === 'warn')!;
    const stop = IDLE_STEPS.find(step => step.stage === 'stop')!;
    expect(warn.message.toLowerCase()).toContain('place');
    expect(stop.message.toLowerCase()).toContain('place is saved');
  });

  it('matches the five minutes the consent notice states', () => {
    expect(IDLE_STEPS.at(-1)!.afterMs).toBe(300_000);
  });
});
