import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, CircleHelp, Compass, Eye, EyeOff, Pause, Play, RefreshCw, RotateCcw, SkipForward, ThumbsDown, Volume2, VolumeX, X } from 'lucide-react';
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
  /** Set only while the observer raised the current question, so the copy can
   *  say who is asking and on what basis. */
  observerAsked?: boolean;
  /** The server's own count of frames it has looked at, while watching is on. */
  framesObserved?: number | null;
  /** Anything the user should read about watching: it ran out, or the observer
   *  cannot read frames at all. */
  watchNotice?: string;
  mount: HTMLElement | null;
  /** What the session says is going wrong, in the user's language. Empty when
   *  the guide is simply working. */
  stuck?: string;
  /** Set once the user has said this guidance was wrong and the server blocked
   *  the session. There is no step to show any more, only what happened next. */
  blocked?: string;
  onReportIncorrect?: (said: string) => void;
  onResume?: () => void;
  onRetry?: (said: string) => void;
  /** What the guide believes about the screen right now, in the user's words.
   *  Empty whenever nothing is wrong, which is most of the time. */
  contextMessage?: string;
  /** Reading the step aloud. Absent where the browser has no speech synthesis,
   *  so the control is not offered rather than offered and broken. */
  speaking?: boolean;
  onToggleSpeech?: () => void;
  /** Steps a forward skip would settle, named before anything happens. Nothing
   *  is settled until the user accepts. */
  skipOffer?: { titles: string[]; accept: () => void; dismiss: () => void } | null;
  onStartWatching?: () => void;
  onStopWatching?: () => void;
  onReplan?: () => void;
  /** Offered only when the plan has run out: ending a task is the user's call,
   *  and what it is called depends on what was actually checked. */
  onFinish?: () => void;
  onClaim: () => void;
  onAnswer: (happened: boolean) => void;
  onTogglePause: () => void;
  onSkip: () => void;
  onClose: () => void;
}

export function GuideIsland(props: GuideIslandProps) {
  const { state, step, ordinal, total, asking, correction, paused, mount } = props;
  const watching = typeof props.framesObserved === 'number';
  const instruction = props.instruction ?? null;
  const action = instruction?.what ?? step?.action ?? '';
  const where = instruction?.where ?? '';
  const check = instruction?.confirmation_hint || step?.expected_result || '';
  const why = instruction?.why ?? step?.explanation ?? '';
  const stuck = instruction?.cannot_find_hint ?? step?.fallback ?? '';
  const presentation = PRESENTATION[state];
  const [expanded, setExpanded] = useState(true);
  const [held, setHeld] = useState(false);
  // Reporting wrong guidance blocks the session, so it takes two presses. The
  // first one only reveals what the second will do.
  const [reporting, setReporting] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  // Ordinary progress collapses back to the logo; anything awaiting a decision
  // stays open, and so does anything the user is currently reading.
  useEffect(() => {
    setExpanded(true);
    setReporting(false);
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

      {props.blocked ? <div className="island-blocked" role="status">
        <p>{props.blocked}</p>
        <small>
          Nothing is pointing at your screen. Read back over where the task got
          to, then pick it up when you are ready — watching stays off until you
          switch it on again yourself.
        </small>
        {props.onResume && <button className="primary island-resume" onClick={props.onResume}>
          <RotateCcw size={15} /> Pick this task up again
        </button>}
        {/* A resume that failed has to say so here: there is no step on screen
            to carry the message, and a button that silently does nothing is
            worse than one that explains itself. */}
        {correction && <p className="island-correction" role="status">{correction}</p>}
      </div> : step ? <>
        <h3>{step.title}</h3>
        <p className="island-action">{action}</p>
        {where && <p className="island-where">{where}</p>}
        {asking
          ? <div className="island-ask">
              <p><Check size={14} aria-hidden="true" /> {props.observerAsked
                ? `Guider thinks this is done. Did this happen: ${check}`
                : `Did this happen: ${check}`}</p>
              <div className="island-answers">
                <button className="primary" onClick={() => props.onAnswer(true)}>Yes, that happened</button>
                <button className="text-button" onClick={() => props.onAnswer(false)}>Not yet</button>
              </div>
              <small>{props.observerAsked
                ? 'Guider was not sure enough to move on by itself, so it asked. Your answer is recorded as your word, not as a check.'
                : 'You are telling Guider this yourself. Nothing has been checked on screen.'}</small>
            </div>
          : <p className="island-expected"><Check size={13} aria-hidden="true" /> {check}</p>}
        {correction && <p className="island-correction" role="status">{correction}</p>}
      </> : <>
        <p className="island-action">{state === 'finished'
          ? 'Every step is behind you. Guider checked only what it could see.'
          : 'Getting your next step ready…'}</p>
        {state === 'finished' && props.onFinish && <button
          className="primary island-finish"
          onClick={props.onFinish}
        ><Check size={15} /> Finish this task</button>}
      </>}

      <div className="island-controls">
        {step && !asking && <button className="primary" onClick={props.onClaim}>
          <Check size={15} /> I&rsquo;ve done this
        </button>}
        {step && (why || stuck) && <details className="island-why">
          <summary><CircleHelp size={14} /> Why this step?</summary>
          {why && <p>{why}</p>}
          {stuck && <p><strong>If that doesn&rsquo;t work:</strong> {stuck}</p>}
        </details>}
        {props.stuck && props.onReplan && <div className="island-stuck" role="status">
          <p>{props.stuck}</p>
          <button className="text-button" onClick={props.onReplan}>
            <RefreshCw size={14} /> Ask for a different plan
          </button>
          <small>What you have already done is kept. Only the rest is replaced.</small>
        </div>}
        {step && props.onRetry && !asking && <button
          className="text-button island-retry"
          onClick={() => props.onRetry?.('The user asked for this step again.')}
        ><RefreshCw size={14} /> Say this a different way</button>}
        {step && props.onReportIncorrect && (reporting
          ? <div className="island-report" role="group" aria-label="Report wrong guidance">
              <p>This stops the guide and switches watching off. Your task is kept.</p>
              <div className="island-answers">
                <button className="primary" onClick={() => props.onReportIncorrect?.(
                  'The user said this guidance was wrong.',
                )}>Yes, this is wrong</button>
                <button className="text-button" onClick={() => setReporting(false)}>Keep going</button>
              </div>
            </div>
          : <button className="text-button island-report-start" onClick={() => setReporting(true)}>
              <ThumbsDown size={14} /> This guidance is wrong
            </button>)}
        {props.contextMessage && <p className="island-context" role="status">
          <Eye size={13} aria-hidden="true" /> {props.contextMessage}
        </p>}
        {props.skipOffer && <div className="island-skip-offer" role="group" aria-label="Skip ahead">
          <p>This looks further along than the plan. Shall I mark these done and move on?</p>
          <ul>{props.skipOffer.titles.map(title => <li key={title}>{title}</li>)}</ul>
          <div className="island-answers">
            <button className="primary" onClick={props.skipOffer.accept}>Yes, move ahead</button>
            <button className="text-button" onClick={props.skipOffer.dismiss}>No, stay here</button>
          </div>
          <small>They are recorded as skipped — not as checked, and not as your word.</small>
        </div>}
        {props.watchNotice && <p className="island-watch-notice" role="status">{props.watchNotice}</p>}
        {watching
          ? <div className="island-watching">
              <span className="island-frames" role="status">
                <Eye size={13} aria-hidden="true" />
                Watching this window. {props.framesObserved} picture
                {props.framesObserved === 1 ? '' : 's'} looked at so far.
              </span>
              <button className="text-button" onClick={props.onStopWatching}>
                <EyeOff size={14} /> Stop watching
              </button>
            </div>
          : props.onStartWatching && step && <button
              className="island-watch-start"
              onClick={props.onStartWatching}
            ><Eye size={14} /> Let Guider watch this window</button>}
        <div className="island-secondary">
          {props.onToggleSpeech && <button
            onClick={props.onToggleSpeech}
            aria-pressed={!!props.speaking}
            aria-label={props.speaking ? 'Stop reading steps aloud' : 'Read steps aloud'}
          >{props.speaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
            {props.speaking ? 'Silence' : 'Read aloud'}</button>}
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
