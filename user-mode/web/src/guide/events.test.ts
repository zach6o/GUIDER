import { describe, expect, it, vi } from 'vitest';
import { EventCursor, followEvents, type EventPage, type GuideEvent } from './events';

const event = (sequence: number, type = 'session.state_changed'): GuideEvent => ({
  sequence, type, state_version: sequence, control_epoch: 1, payload: {},
  created_at: '2026-09-12T00:00:00Z',
});
const page = (...sequences: number[]): EventPage => ({
  items: sequences.map(value => event(value)),
  next_after: sequences.length ? Math.max(...sequences) : 0,
});

describe('the cursor', () => {
  it('starts at the beginning and reports everything once', () => {
    const cursor = new EventCursor();
    expect(cursor.position).toBe(0);
    expect(cursor.accept(page(1, 2, 3)).map(e => e.sequence)).toEqual([1, 2, 3]);
    expect(cursor.position).toBe(3);
  });

  it('resumes from a supplied position', () => {
    const cursor = new EventCursor(5);
    expect(cursor.accept(page(6, 7)).map(e => e.sequence)).toEqual([6, 7]);
  });

  it('drops a replayed page instead of delivering it twice', () => {
    const cursor = new EventCursor();
    cursor.accept(page(1, 2, 3));
    expect(cursor.accept(page(1, 2, 3))).toEqual([]);
    expect(cursor.position).toBe(3);
  });

  it('delivers only the unseen half of an overlapping page', () => {
    const cursor = new EventCursor();
    cursor.accept(page(1, 2));
    expect(cursor.accept(page(2, 3, 4)).map(e => e.sequence)).toEqual([3, 4]);
  });

  it('never moves backwards', () => {
    const cursor = new EventCursor(10);
    cursor.accept({ items: [], next_after: 4 });
    expect(cursor.position).toBe(10);
  });

  it('orders a page that arrives shuffled', () => {
    expect(new EventCursor().accept(page(3, 1, 2)).map(e => e.sequence)).toEqual([1, 2, 3]);
  });

  it('holds position when there is nothing new', () => {
    const cursor = new EventCursor(7);
    expect(cursor.accept({ items: [], next_after: 7 })).toEqual([]);
    expect(cursor.position).toBe(7);
  });
});

describe('following a session', () => {
  it('asks from the cursor each time and reports each event once', async () => {
    const asked: number[] = [];
    const pages = [page(1, 2), page(3), { items: [], next_after: 3 }];
    const controller = new AbortController();
    const seen: number[] = [];

    await followEvents({
      signal: controller.signal,
      onEvents: events => seen.push(...events.map(e => e.sequence)),
      fetchPage: async after => {
        asked.push(after);
        const next = pages.shift();
        if (!next) { controller.abort(); return { items: [], next_after: after }; }
        return next;
      },
    });

    expect(asked).toEqual([0, 2, 3, 3]);
    expect(seen).toEqual([1, 2, 3]);
  });

  it('resumes at the exact sequence after a forced reconnect', async () => {
    const controller = new AbortController();
    const seen: number[] = [];
    let calls = 0;

    const reached = await followEvents({
      signal: controller.signal,
      sleep: async () => {},
      onEvents: events => seen.push(...events.map(e => e.sequence)),
      fetchPage: async after => {
        calls += 1;
        if (calls === 1) return page(1, 2);
        // The connection drops mid-stream.
        if (calls === 2) throw new TypeError('network error');
        if (calls === 3) {
          expect(after).toBe(2); // resumed exactly where it stopped
          return page(3, 4);
        }
        controller.abort();
        return { items: [], next_after: after };
      },
    });

    expect(seen).toEqual([1, 2, 3, 4]);
    expect(reached).toBe(4);
  });

  it('backs off before retrying a failed request', async () => {
    const controller = new AbortController();
    const sleep = vi.fn(async () => {});
    let calls = 0;

    await followEvents({
      signal: controller.signal,
      sleep,
      retryDelayMs: 1234,
      onEvents: () => {},
      fetchPage: async after => {
        calls += 1;
        if (calls === 1) throw new Error('boom');
        controller.abort();
        return { items: [], next_after: after };
      },
    });

    expect(sleep).toHaveBeenCalledWith(1234);
  });

  it('stops quietly when aborted mid-request', async () => {
    const controller = new AbortController();
    const seen: number[] = [];
    const reached = await followEvents({
      signal: controller.signal,
      onEvents: events => seen.push(...events.map(e => e.sequence)),
      fetchPage: async () => {
        controller.abort();
        throw new DOMException('Aborted', 'AbortError');
      },
    });
    expect(seen).toEqual([]);
    expect(reached).toBe(0);
  });
});
