import { useEffect, useRef, useState } from 'react';
import { Check, Compass, LogOut, MessageCircle, Monitor, Pause, Play, Square, X } from 'lucide-react';
import type { PersonalGuidance, PersonalPlan } from './cloudApi';

interface Props {
  plan: PersonalPlan;
  guidance: PersonalGuidance | null;
  watching: boolean;
  checking: boolean;
  busy: boolean;
  notice: string;
  error: string;
  onApprove: () => void;
  onShare: () => void;
  onPause: () => void;
  onStop: () => void;
  onExit: () => void;
  onShowScreen: () => void;
}

export function describeGuidance({ plan, guidance, watching, notice, error }: Pick<Props, 'plan' | 'guidance' | 'watching' | 'notice' | 'error'>) {
  const step = plan.steps[plan.step_index];
  const needsApproval = step?.permission === 'confirm' && !plan.approved_steps.includes(plan.step_index);
  const blocked = step?.permission === 'blocked';
  const progress = plan.finished ? 'All steps complete' : `Step ${plan.step_index + 1} of ${plan.steps.length}`;
  const title = error ? 'Let’s get back on track' : plan.finished ? 'You’re all done!'
    : blocked ? 'Let’s pause here' : needsApproval ? notice.startsWith('Step checked.') ? 'Step complete — one quick approval' : 'One quick approval'
    : !watching && notice ? 'Sharing is off' : guidance?.disposition === 'needs_context'
      ? 'I need a clearer view' : notice.startsWith('Step checked.') ? 'Step complete — here’s what’s next' : progress;
  const message = error || (plan.finished ? 'Your plan is complete. I’ve stopped screen sharing.'
    : blocked ? 'This step is outside the supported scope. Return to Guider to revise your plan.'
    : !watching && notice ? notice
    : guidance?.disposition === 'needs_context' ? guidance.observation
    : guidance?.action || step?.action || 'Choose a window and I’ll guide you from here.');
  return { step, needsApproval, blocked, progress, title, message };
}

/** Text-only companion. Targets can also appear in an explicitly connected tab. */
export function GuideAssistant(props: Props) {
  const { plan, guidance, watching, checking, busy } = props;
  const [menuOpen, setMenuOpen] = useState(false);
  const [dismissed, setDismissed] = useState('');
  const root = useRef<HTMLElement>(null);
  const ball = useRef<HTMLButtonElement>(null);
  const { step, needsApproval, blocked, progress, title, message } = describeGuidance(props);
  // Checking status changes must not reopen a message the user just dismissed.
  const messageKey = JSON.stringify([plan.id, plan.step_index, title, message, guidance?.where]);
  const showBubble = !menuOpen && dismissed !== messageKey;

  useEffect(() => {
    if (!menuOpen) return;
    const owner = root.current?.ownerDocument;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); ball.current?.focus(); }
    };
    owner?.addEventListener('keydown', close);
    return () => owner?.removeEventListener('keydown', close);
  }, [menuOpen]);

  const invoke = (callback: () => void) => { setMenuOpen(false); callback(); };
  return <aside ref={root} className="guide-assistant" aria-label="Guide assistant">
    {showBubble && <section className="guide-chat-bubble" aria-label="Guide message">
      <div className="guide-chat-heading"><span><MessageCircle size={14} /> GUIDER</span>
        <button aria-label="Dismiss guide message" onClick={() => {
          setDismissed(messageKey); ball.current?.focus();
        }}><X size={15} /></button></div>
      <div role="status" aria-live="polite" aria-atomic="true">
        <strong>{plan.finished && <Check size={17} />} {title}</strong>
        <p>{message}</p>
        {watching && guidance?.where && !needsApproval && <p className="guide-chat-where">{guidance.where}</p>}
      </div>
      {needsApproval && <><small>{progress} · {step.title}</small><button className="primary" disabled={busy} onClick={props.onApprove}>I approve this step</button></>}
      {!watching && !plan.finished && !blocked && !needsApproval && <button className="text-button" disabled={busy} onClick={props.onShare}><Play size={13} /> Share a window to continue</button>}
    </section>}
    {menuOpen && <section className="guide-ball-menu" id="guide-ball-options" aria-label="Guide options">
      <div className="guide-menu-heading"><strong>{progress}</strong><small>{checking ? 'Checking your screen…' : watching ? 'Screen sharing on' : 'Screen sharing off'}</small></div>
      <button onClick={() => { setDismissed(''); setMenuOpen(false); }}><MessageCircle size={16} /> Show current step</button>
      {watching ? <button onClick={() => invoke(props.onPause)}><Pause size={16} /> Pause guidance</button>
        : !plan.finished && !blocked && <button disabled={busy} onClick={() => invoke(props.onShare)}><Play size={16} /> Resume / choose window</button>}
      <button onClick={() => invoke(props.onShowScreen)}><Monitor size={16} /> {watching ? 'Show shared screen' : 'Return to Guider'}</button>
      <button onClick={() => invoke(props.onStop)}><Square size={16} /> Stop screen sharing</button>
      <button className="guide-exit" onClick={() => invoke(props.onExit)}><LogOut size={16} /> Exit guide</button>
      <small>{plan.calls_remaining} AI requests left in this connection</small>
    </section>}
    <button ref={ball} className={`guide-assistant-ball ${watching ? 'is-watching' : ''}`}
      aria-label={menuOpen ? 'Close guide options' : 'Open guide options'} aria-expanded={menuOpen}
      aria-controls={menuOpen ? 'guide-ball-options' : undefined} onClick={() => setMenuOpen(!menuOpen)}>
      {menuOpen ? <X size={24} /> : plan.finished ? <Check size={26} /> : <Compass size={27} />}
      <span className="guide-ball-dot" aria-hidden="true" />
    </button>
  </aside>;
}
