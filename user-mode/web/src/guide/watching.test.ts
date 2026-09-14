/**
 * What the consent notice promises, held to by the code that sends frames.
 *
 * Doc 21 lists claims with the thing that enforces each one. These are the
 * browser half: nothing is sent unless the local gate admitted it and a step is
 * waiting, the counter shown is the server's own, running out keeps the guide
 * working, and one tap ends it including whatever was in flight.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Watcher, type FrameSource, type WatchHooks } from './watching';
import { SAMPLE_SIZE } from './observer';
import type { GuideApi, ObservationTick, Session } from '../types';

const session = { id: 'session-1', state_version: 4 } as Session;

const flat = (value: number) => new Uint8Array(SAMPLE_SIZE * SAMPLE_SIZE).fill(value);

class Failure extends Error {
  constructor(message: string, readonly status: number, readonly code: string) { super(message); }
}

function tick(overrides: Partial<ObservationTick> = {}): ObservationTick {
  return {
    decision: 'wait', confidence: 0, ui_changed: true, anomaly: 'none', note: '',
    frames_observed: 1, observation_calls_remaining: 199, session, ...overrides,
  };
}

function harness(options: {
  observe?: GuideApi['observe'];
  awaiting?: () => boolean;
  callsRemaining?: number;
} = {}) {
  const notices: string[] = [];
  const stops: string[] = [];
  const ticks: ObservationTick[] = [];
  const counters: [number, number][] = [];
  let frame = flat(10);

  const api = {
    startWatching: vi.fn(async () => ({
      active: true, frames_observed: 0,
      observation_calls_remaining: options.callsRemaining ?? 200,
      consent_version: 'observation-draft-2', session,
    })),
    stopWatching: vi.fn(async () => ({
      active: false, frames_observed: 2, observation_calls_remaining: 198,
      consent_version: 'observation-draft-2', session,
    })),
    observe: options.observe ?? vi.fn(async () => tick()),
  } as unknown as GuideApi;

  const source: FrameSource = {
    sample: () => frame,
    encode: vi.fn(async () => 'bWFza2Vk'),
  };
  const hooks: WatchHooks = {
    session: () => session,
    awaitingAction: options.awaiting ?? (() => true),
    onCounters: (frames, remaining) => counters.push([frames, remaining]),
    onTick: value => ticks.push(value),
    onNotice: message => notices.push(message),
    onStopped: reason => stops.push(reason),
  };

  const watcher = new Watcher(api, source, hooks);
  return {
    api, source, watcher, notices, stops, ticks, counters,
    show: (value: number) => { frame = flat(value); },
  };
}

/** Feed the gate a baseline, a change, and then the stillness it waits for.
 *  `shade` must differ between calls, or there is nothing for it to notice. */
async function settle(context: ReturnType<typeof harness>, from = 0, shade = 200) {
  await context.watcher.pump(from);
  context.show(shade);
  await context.watcher.pump(from + 500);
  context.show(shade);
  await context.watcher.pump(from + 1500);
}

beforeEach(() => vi.restoreAllMocks());

describe('switching watching on', () => {
  it('sends the exact notice version the user was shown', async () => {
    const context = harness();
    await context.watcher.start('observation-draft-2');
    expect(context.api.startWatching).toHaveBeenCalledWith(session, 'observation-draft-2');
    expect(context.watcher.status).toBe('watching');
    expect(context.counters[0]).toEqual([0, 200]);
  });

  it('refuses to start without a session to watch for', async () => {
    const context = harness();
    const watcher = new Watcher(
      context.api, context.source,
      { ...({} as WatchHooks), session: () => null } as WatchHooks,
    );
    await expect(watcher.start('observation-draft-2')).rejects.toThrow(/Start the guide/);
    expect(context.api.startWatching).not.toHaveBeenCalled();
  });
});

describe('what actually gets sent', () => {
  it('sends nothing until a change has settled', async () => {
    const context = harness();
    await context.watcher.start('observation-draft-2');

    expect(await context.watcher.pump(0)).toBe('ignored');   // baseline
    context.show(200);
    expect(await context.watcher.pump(500)).toBe('settling'); // still moving
    expect(context.api.observe).not.toHaveBeenCalled();

    context.show(200);
    expect(await context.watcher.pump(1500)).toBe('admit');
    expect(context.api.observe).toHaveBeenCalledTimes(1);
  });

  it('sends the masked frame the source encoded, and nothing else', async () => {
    const context = harness();
    await context.watcher.start('observation-draft-2');
    await settle(context);
    const [, image, admittedAt] = (context.api.observe as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(context.source.encode).toHaveBeenCalled();
    expect(image).toBe('bWFza2Vk');
    expect(admittedAt).toBe(new Date(1500).toISOString());
  });

  it('sends nothing while no step is waiting on the user', async () => {
    const context = harness({ awaiting: () => false });
    await context.watcher.start('observation-draft-2');
    await settle(context);
    expect(context.api.observe).not.toHaveBeenCalled();
  });

  it('never has two ticks in flight at once', async () => {
    let release = () => {};
    const pending = new Promise<void>(resolve => { release = resolve; });
    const observe = vi.fn(async () => { await pending; return tick(); });
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');

    // Prime the gate, then start the admitting tick without waiting for it.
    await context.watcher.pump(0);
    context.show(200);
    await context.watcher.pump(500);
    const first = context.watcher.pump(1500);
    expect(context.watcher.status).toBe('sending');

    context.show(20);
    expect(await context.watcher.pump(3000)).toBe('idle');
    release();
    await first;
    expect(observe).toHaveBeenCalledTimes(1);
  });
});

describe('the counter and the verdict', () => {
  it('shows the server’s count, never one of its own', async () => {
    const observe = vi.fn(async () => tick({ frames_observed: 7, observation_calls_remaining: 193 }));
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');
    await settle(context);
    expect(context.counters.at(-1)).toEqual([7, 193]);
  });

  it('passes a verdict on rather than acting on it here', async () => {
    const observe = vi.fn(async () => tick({ decision: 'ask', confidence: 0.7 }));
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');
    await settle(context);
    expect(context.ticks.at(-1)?.decision).toBe('ask');
    expect(context.stops).toEqual([]);
  });

  it('says once when the observer cannot read frames at all', async () => {
    const observe = vi.fn(async () => tick({
      anomaly: 'unreadable', note: 'The development observer cannot read frames.',
    }));
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');
    await settle(context, 0, 200);
    await settle(context, 10_000, 60);
    expect(observe).toHaveBeenCalledTimes(2);
    expect(context.notices).toEqual(['The development observer cannot read frames.']);
  });
});

describe('running out', () => {
  it('stops watching and keeps the guide going', async () => {
    const observe = vi.fn(async () => {
      throw new Failure(
        'Guider has watched as much as this session allows.', 429, 'observation_budget_spent',
      );
    });
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');
    await settle(context);

    expect(context.watcher.status).toBe('off');
    expect(context.notices.at(-1)).toContain('watched as much as');
    expect(context.api.stopWatching).toHaveBeenCalled();
  });

  it('treats the local budget the same way, without asking the server first', async () => {
    const context = harness({ callsRemaining: 0 });
    await context.watcher.start('observation-draft-2');
    await settle(context);
    expect(context.api.observe).not.toHaveBeenCalled();
    expect(context.notices.at(-1)).toContain('Keep going and tell it when a step is done.');
  });
});

describe('refusals that are not failures', () => {
  it('keeps watching through a rate limit', async () => {
    const observe = vi.fn(async () => {
      throw new Failure('Guider is looking too often.', 429, 'rate_limited');
    });
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');
    await settle(context);
    expect(context.watcher.status).toBe('watching');
    expect(context.stops).toEqual([]);
  });

  it('stops when the session says watching is off', async () => {
    const observe = vi.fn(async () => {
      throw new Failure('Watching was switched off.', 409, 'observation_stopped');
    });
    const context = harness({ observe: observe as unknown as GuideApi['observe'] });
    await context.watcher.start('observation-draft-2');
    await settle(context);
    expect(context.watcher.status).toBe('off');
    expect(context.stops.at(-1)).toBe('Watching was switched off.');
  });
});

describe('one tap off', () => {
  it('stops the loop before anything else, and tells the server', async () => {
    const context = harness();
    await context.watcher.start('observation-draft-2');
    await context.watcher.stop('You switched watching off.');

    expect(context.watcher.status).toBe('off');
    expect(context.api.stopWatching).toHaveBeenCalledWith('session-1');
    expect(context.stops).toEqual(['You switched watching off.']);
    // Nothing more is sent afterwards, settled change or not.
    await settle(context, 20_000, 60);
    expect(context.api.observe).not.toHaveBeenCalled();
  });

  it('still stops locally when the server cannot be reached', async () => {
    const context = harness();
    (context.api.stopWatching as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('offline'),
    );
    await context.watcher.start('observation-draft-2');
    await expect(context.watcher.stop('You switched watching off.')).rejects.toThrow('offline');
    expect(context.watcher.status).toBe('off');
    expect(context.stops).toEqual(['You switched watching off.']);
  });
});
