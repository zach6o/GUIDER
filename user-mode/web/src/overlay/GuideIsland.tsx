import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, CircleHelp, Compass, Pause, Play, SkipForward, X } from 'lucide-react';
import type { Step } from '../types';
import { COLLAPSE_AFTER_MS, PRESENTATION, type IslandState } from './states';

export interface GuideIslandProps {
  state: IslandState;
  step: Step | null;
  ordinal: number;
  total: number;
  /** Set while the guide is asking the user to confirm the expected result. */
  asking: boolean;
  correction: string;
  paused: boolean;
  mount: HTMLElement | null;
  onClaim: () => void;
  onAnswer: (happened: boolean) => void;
  onTogglePause: () => void;
  onSkip: () => void;
  onClose: () => void;
}

export function GuideIsland(props: GuideIslandProps) {
  const { state, step, ordinal, total, asking, correction, paused, mount } = props;
  const presentation = PRESENTATION[state];
  const [expanded, setExpanded] = useState(true);
  const [held, setHeld] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  // Ordinary progress collapses back to the logo; anything awaiting a decision
  // stays open, and so does anything the user is currently reading.
  useEffect(() => {
    setExpanded(true);
  }, [step?.id, state, asking, correction]);
  useEffect(() => {
    if (!expanded || presentation.sticky || held) return;
    const timer = setTimeout(() => setExpanded(false), COLLAPSE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [expanded, presentation.sticky, held, step?.id, state]);

  const Glyph = presentation.glyph;
  const announcement = step
    ? `${presentation.label}. Step ${ordinal} of ${total}. ${step.title}`
    : presentation.label;

  const island = <div
    className={`guide-island tone-${presentation.tone}${expanded ? ' expanded' : ''}`}
    data-state={state}
    onMouseEnter={() => setHeld(true)}
    onMouseLeave={() => setHeld(false)}
    onFocusCapture={() => setHeld(true)}
    onBlurCapture={() => setHeld(false)}
  >
    <div className="sr-only" role="status" aria-live={presentation.live}>{announcement}</div>

    <button
      className="island-dot"
      aria-expanded={expanded}
      aria-label={expanded ? 'Collapse the guide' : `Expand the guide. ${announcement}`}
      onClick={() => setExpanded(!expanded)}
    >
      <span className={presentation.pulse ? 'island-ring pulse' : 'island-ring'} aria-hidden="true" />
      <Compass size={20} aria-hidden="true" />
    </button>

    {expanded && <div className="island-panel" ref={panel}>
      <div className="island-head">
        <span className="island-status"><Glyph size={14} aria-hidden="true" />{presentation.label}</span>
        <span className="island-count">Step {ordinal} of {total}</span>
        <button className="icon-button island-close" aria-label="Close the guide" onClick={props.onClose}>
          <X size={15} />
        </button>
      </div>

      {step ? <>
        <h3>{step.title}</h3>
        <p className="island-action">{step.action}</p>
        {asking
          ? <div className="island-ask">
              <p><Check size={14} aria-hidden="true" /> Did this happen: {step.expected_result}</p>
              <div className="island-answers">
                <button className="primary" onClick={() => props.onAnswer(true)}>Yes, that happened</button>
                <button className="text-button" onClick={() => props.onAnswer(false)}>Not yet</button>
              </div>
              <small>You are telling Guider this yourself. Nothing has been checked on screen.</small>
            </div>
          : <p className="island-expected"><Check size={13} aria-hidden="true" /> {step.expected_result}</p>}
        {correction && <p className="island-correction" role="status">{correction}</p>}
      </> : <p className="island-action">Every step is finished. Nothing was verified on screen.</p>}

      <div className="island-controls">
        {step && !asking && <button className="primary" onClick={props.onClaim}>
          <Check size={15} /> I&rsquo;ve done this
        </button>}
        {step?.explanation && <details className="island-why">
          <summary><CircleHelp size={14} /> Why this step?</summary>
          <p>{step.explanation}</p>
          {step.fallback && <p><strong>If that doesn&rsquo;t work:</strong> {step.fallback}</p>}
        </details>}
        <div className="island-secondary">
          <button onClick={props.onTogglePause} aria-label={paused ? 'Resume the guide' : 'Pause the guide'}>
            {paused ? <Play size={14} /> : <Pause size={14} />}{paused ? 'Resume' : 'Pause'}
          </button>
          {step && <button onClick={props.onSkip}><SkipForward size={14} /> Skip</button>}
        </div>
      </div>
    </div>}
  </div>;

  return mount ? createPortal(island, mount) : island;
}
