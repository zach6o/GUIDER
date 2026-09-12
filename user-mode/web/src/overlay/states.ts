import { AlertTriangle, Check, Compass, Eye, LoaderCircle, Pause } from 'lucide-react';

/**
 * The island communicates state three ways at once — colour, glyph and text —
 * because an overlay that speaks only in colour excludes people by construction.
 * Nothing here relies on hue alone.
 */
export type IslandState =
  | 'idle' | 'watching' | 'thinking' | 'attention' | 'error' | 'finished';

export interface Presentation {
  /** Always rendered, never only announced. */
  label: string;
  glyph: typeof Compass;
  /** Maps to a CSS token, never to a raw colour. */
  tone: 'neutral' | 'good' | 'warn' | 'bad';
  /** Interruptive states interrupt; ordinary progress does not. */
  live: 'polite' | 'assertive';
  /** Whether the ring animates. Suppressed under prefers-reduced-motion in CSS. */
  pulse: boolean;
  /** States that demand a decision stay open rather than collapsing on a timer. */
  sticky: boolean;
}

export const PRESENTATION: Record<IslandState, Presentation> = {
  idle: {
    label: 'Paused', glyph: Pause, tone: 'neutral', live: 'polite', pulse: false, sticky: false,
  },
  watching: {
    label: 'On this step', glyph: Eye, tone: 'good', live: 'polite', pulse: false, sticky: false,
  },
  thinking: {
    label: 'Checking', glyph: LoaderCircle, tone: 'good', live: 'polite', pulse: true,
    sticky: true,
  },
  attention: {
    label: 'Needs you', glyph: AlertTriangle, tone: 'warn', live: 'assertive', pulse: false,
    sticky: true,
  },
  error: {
    label: 'Stopped', glyph: AlertTriangle, tone: 'bad', live: 'assertive', pulse: false,
    sticky: true,
  },
  finished: {
    label: 'All done', glyph: Check, tone: 'good', live: 'polite', pulse: false, sticky: true,
  },
};

export const ISLAND_STATES = Object.keys(PRESENTATION) as IslandState[];

/** How long an ordinary state stays expanded before collapsing back to the logo. */
export const COLLAPSE_AFTER_MS = 6000;
