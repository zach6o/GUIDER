/**
 * Resumable event following.
 *
 * `GuidanceEvent.sequence` is monotonic and unique per session, so the whole
 * client-side protocol is one integer. A dropped connection costs nothing: ask
 * again from the cursor. The cursor only ever moves forward, so a retried or
 * duplicated page cannot replay work the caller has already seen.
 */

export interface GuideEvent {
  sequence: number;
  state_version: number;
  control_epoch: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface EventPage {
  items: GuideEvent[];
  next_after: number;
}

export class EventCursor {
  constructor(private at = 0) {}

  /** Where the next request should resume. */
  get position(): number {
    return this.at;
  }

  /**
   * Takes a page and returns only what the caller has not seen, advancing the
   * cursor. Anything at or before the cursor is dropped rather than re-delivered.
   */
  accept(page: EventPage): GuideEvent[] {
    const fresh = page.items
      .filter(event => event.sequence > this.at)
      .sort((left, right) => left.sequence - right.sequence);
    // next_after can lag the newest item if a page was served out of order; the
    // cursor takes whichever is further ahead so it never goes backwards.
    this.at = Math.max(this.at, page.next_after, ...fresh.map(event => event.sequence));
    return fresh;
  }
}

export interface FollowOptions {
  fetchPage: (after: number, signal: AbortSignal) => Promise<EventPage>;
  onEvents: (events: GuideEvent[]) => void;
  signal: AbortSignal;
  from?: number;
  /** Backoff after a failed request, so a dead backend is not hammered. */
  retryDelayMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const wait = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

/** Follows a session until aborted. Returns the cursor reached, so a caller that
 *  restarts the loop resumes exactly where this one stopped. */
export async function followEvents(options: FollowOptions): Promise<number> {
  const { fetchPage, onEvents, signal, retryDelayMs = 2000, sleep = wait } = options;
  const cursor = new EventCursor(options.from ?? 0);
  while (!signal.aborted) {
    try {
      const fresh = cursor.accept(await fetchPage(cursor.position, signal));
      if (fresh.length) onEvents(fresh);
    } catch (error) {
      if (signal.aborted || (error instanceof DOMException && error.name === 'AbortError')) break;
      // The cursor is untouched, so the retry asks for exactly what was missed.
      await sleep(retryDelayMs);
    }
  }
  return cursor.position;
}
