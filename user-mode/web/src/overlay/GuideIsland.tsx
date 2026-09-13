import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, CircleHelp, Compass, Pause, Play, SkipForward, X } from 'lucide-react';
import type { Instruction, Step } from '../types';
import { COLLAPSE_AFTER_MS, PRESENTATION, type IslandState } from './states';

export interface GuideIslandProps {
  state: IslandState;
  step: Step | null;
  /** The engine's own wording for this step, when a server session published
   *  one. The plan's text is the fallback, and the offline practice demo's only
   *  source. */
  instruction?: Instruction | null;
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
  const instruction = props.instruction ?? null;
  const action = instruction?.what ?? step?.action ?? '';
  const where = instruction?.where ?? '';
  const check = instruction?.confirmation_hint || step?.expected_result || '';
  const why = instruction?.why ?? step?.explanation ?? '';
  const stuck = instruction?.cannot_find_hint ?? step?.fallback ?? '';
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
  const announcement = step && ordinal >= 1
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
        {ordinal >= 1 && <span className="island-count">Step {ordinal} of {total}</span>}
        <button className="icon-button island-close" aria-label="Close the guide" onClick={props.onClose}>
          <X size={15} />
        </button>
      </div>

      {step ? <>
        <h3>{step.title}</h3>
        <p className="island-action">{action}</p>
        {where && <p className="island-where">{where}</p>}
        {asking
          ? <div className="island-ask">
              <p><Check size={14} aria-hidden="true" /> Did this happen: {check}</p>
              <div className="island-answers">
                <button className="primary" onClick={() => props.onAnswer(true)}>Yes, that happened</button>
                <button className="text-button" onClick={() => props.onAnswer(false)}>Not yet</button>
              </div>
              <small>You are telling Guider this yourself. Nothing has been checked on screen.</small>
            </div>
          : <p className="island-expected"><Check size={13} aria-hidden="true" /> {check}</p>}
        {correction && <p className="island-correction" role="status">{correction}</p>}
      </> : <p className="island-action">{state === 'finished'
        ? 'Every step is finished. Nothing was verified on screen.'
        : 'Getting your next step ready…'}</p>}

      <div className="island-controls">
        {step && !asking && <button className="primary" onClick={props.onClaim}>
          <Check size={15} /> I&rsquo;ve done this
        </button>}
        {step && (why || stuck) && <details className="island-why">
          <summary><CircleHelp size={14} /> Why this step?</summary>
          {why && <p>{why}</p>}
          {stuck && <p><strong>If that doesn&rsquo;t work:</strong> {stuck}</p>}
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
