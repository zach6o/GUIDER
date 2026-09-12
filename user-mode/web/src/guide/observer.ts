/**
 * Tier 0 and tier 1 of the observer, per ADR-016.
 *
 * A screen being worked on is static almost all of the time. Between meaningful
 * UI changes there is nothing a vision model could learn, so the cheap part of
 * observation runs here, on this machine, and nothing leaves it:
 *
 *   T0  every ~500 ms, reduce the frame to 64x64 grayscale and compare it to the
 *       previous one. Unchanged frames are discarded and forgotten.
 *   T1  a change must hold steady for ~700 ms before it counts, so animations and
 *       half-drawn repaints do not each buy a provider call. An admitted frame
 *       also has to clear the rate limit, the session budget, and the fact that a
 *       step is actually waiting on the user.
 *
 * Nothing in this module performs any network access. Sending an admitted frame
 * is tier 2, and a separate decision.
 */

export const SAMPLE_SIZE = 64;

/** Mean per-pixel difference, 0-255, below which two frames count as the same.
 *  Low enough to catch a dialog, high enough to ignore a caret and compression. */
export const CHANGE_THRESHOLD = 2.2;

/** How long a change must persist before it is treated as settled. */
export const SETTLE_MS = 700;

/** Floor between admitted frames. ADR-016's budget arithmetic depends on it. */
export const MIN_INTERVAL_MS = 4000;

/** Ceiling per minute, enforced again server-side. */
export const MAX_FRAMES_PER_MINUTE = 12;

export interface FrameLike {
  data: Uint8ClampedArray | Uint8Array;
  width: number;
  height: number;
}

/** Reduce any frame to a fixed-size grayscale thumbnail by box sampling. The
 *  result is what the gate compares; the original pixels are never retained. */
export function downsample(frame: FrameLike, size = SAMPLE_SIZE): Uint8Array {
  const out = new Uint8Array(size * size);
  const columnWidth = frame.width / size;
  const rowHeight = frame.height / size;
  for (let row = 0; row < size; row++) {
    for (let column = 0; column < size; column++) {
      const x = Math.min(frame.width - 1, Math.floor((column + 0.5) * columnWidth));
      const y = Math.min(frame.height - 1, Math.floor((row + 0.5) * rowHeight));
      const at = (y * frame.width + x) * 4;
      // Rec. 601 luma: close enough for change detection, and cheap.
      out[row * size + column] = Math.round(
        0.299 * frame.data[at] + 0.587 * frame.data[at + 1] + 0.114 * frame.data[at + 2],
      );
    }
  }
  return out;
}

export function meanAbsoluteDifference(before: Uint8Array, after: Uint8Array): number {
  if (before.length !== after.length) return 255;
  let total = 0;
  for (let index = 0; index < before.length; index++) total += Math.abs(before[index] - after[index]);
  return total / before.length;
}

/** Difference hash: each bit records whether a pixel is brighter than its right
 *  neighbour. Robust to overall brightness shifts that mean difference is not. */
export function differenceHash(gray: Uint8Array, size = SAMPLE_SIZE): Uint8Array {
  const bits = new Uint8Array(size * (size - 1));
  let at = 0;
  for (let row = 0; row < size; row++) {
    for (let column = 0; column < size - 1; column++) {
      const index = row * size + column;
      bits[at++] = gray[index] > gray[index + 1] ? 1 : 0;
    }
  }
  return bits;
}

export function hammingDistance(before: Uint8Array, after: Uint8Array): number {
  if (before.length !== after.length) return before.length;
  let total = 0;
  for (let index = 0; index < before.length; index++) {
    if (before[index] !== after[index]) total++;
  }
  return total;
}

export type Decision =
  /** Nothing changed, or the guide is not waiting on the user. */
  | 'ignored'
  /** Something changed but has not held still long enough to be real. */
  | 'settling'
  /** Settled, but too soon after the last admitted frame. */
  | 'throttled'
  /** Settled, but the session has spent its observation budget. */
  | 'exhausted'
  /** Send this one. */
  | 'admit';

export interface GateContext {
  /** Observation only runs while a step is actually waiting on the user. */
  awaitingAction: boolean;
  /** Admitted frames still available this session. */
  budgetRemaining: number;
}

export interface GateOptions {
  changeThreshold?: number;
  settleMs?: number;
  minIntervalMs?: number;
  maxFramesPerMinute?: number;
}

/**
 * Decides, frame by frame, whether anything is worth sending. Holds one 64x64
 * thumbnail and a few numbers; never a frame, never a history of frames.
 */
export class MotionGate {
  private previous: Uint8Array | null = null;
  private changedAt: number | null = null;
  private lastAdmittedAt = -Infinity;
  private admissions: number[] = [];
  private readonly options: Required<GateOptions>;

  constructor(options: GateOptions = {}) {
    this.options = {
      changeThreshold: options.changeThreshold ?? CHANGE_THRESHOLD,
      settleMs: options.settleMs ?? SETTLE_MS,
      minIntervalMs: options.minIntervalMs ?? MIN_INTERVAL_MS,
      maxFramesPerMinute: options.maxFramesPerMinute ?? MAX_FRAMES_PER_MINUTE,
    };
  }

  /** Frames admitted in the last minute, for the counter the overlay shows. */
  admittedRecently(now: number): number {
    return this.admissions.filter(at => at > now - 60_000).length;
  }

  reset() {
    this.previous = null;
    this.changedAt = null;
  }

  consider(gray: Uint8Array, now: number, context: GateContext): Decision {
    const previous = this.previous;
    this.previous = gray;

    // Observation is pointless when no step is waiting; keep the baseline fresh
    // so resuming does not report the whole intervening period as one change.
    if (!context.awaitingAction) {
      this.changedAt = null;
      return 'ignored';
    }
    if (previous === null) return 'ignored'; // First frame is the baseline.

    const changed = meanAbsoluteDifference(previous, gray) >= this.options.changeThreshold;
    if (changed) {
      // Still moving: restart the settle timer rather than counting the flicker.
      this.changedAt = now;
      return 'settling';
    }
    if (this.changedAt === null) return 'ignored'; // Nothing has changed since the last admission.
    if (now - this.changedAt < this.options.settleMs) return 'settling';

    // Settled. Now the cheap checks that keep tier 2 affordable.
    if (now - this.lastAdmittedAt < this.options.minIntervalMs) return 'throttled';
    if (this.admittedRecently(now) >= this.options.maxFramesPerMinute) return 'throttled';
    if (context.budgetRemaining <= 0) return 'exhausted';

    this.changedAt = null;
    this.lastAdmittedAt = now;
    this.admissions = [...this.admissions.filter(at => at > now - 60_000), now];
    return 'admit';
  }
}
