import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check } from 'lucide-react';
import { cloudApi, CloudApiError } from './cloudApi';
import type { ConnectionResult, PersonalGuidance, PersonalPlan } from './cloudApi';
import { PersonalConnection } from './PersonalConnection';
import { GuideAssistant, describeGuidance } from './GuideAssistant';
import { TabGuideBridge, noTabGuide } from './tabGuideBridge';
import { ScreenCapture } from './screenCapture';
import { WatchSetup } from './overlay/WatchSetup';
import { createFrameSource } from './overlay/frameSource';
import type { MaskArea } from './overlay/frameSource';
import { closeFloatingWindow, openFloatingWindow, pipSupported } from './overlay/pip';
import type { FloatingWindow } from './overlay/pip';
import { meanAbsoluteDifference } from './guide/observer';
import './personal.css';

export function AutomaticGuide({ onSharingChange }: { onSharingChange: (active: boolean) => void }) {
  const [connection, setConnection] = useState<ConnectionResult | null>(null);
  const connectionRef = useRef<ConnectionResult | null>(null);
  const [goal, setGoal] = useState('');
  const [pasted, setPasted] = useState('');
  const [plan, setPlanState] = useState<PersonalPlan | null>(null);
  const planRef = useRef<PersonalPlan | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [setup, setSetup] = useState(false);
  const [watching, setWatching] = useState(false);
  const [keepGuideVisible, setKeepGuideVisible] = useState(true);
  const tabBridge = useRef(new TabGuideBridge());
  const [tabStatus, setTabStatus] = useState(noTabGuide);
  const sharedHandle = useRef('');
  const tabCommand = useRef<(command: string) => void>(() => {});
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [guidance, setGuidance] = useState<PersonalGuidance | null>(null);
  const [masks, setMasks] = useState<MaskArea[]>([]);
  const masksRef = useRef<MaskArea[]>([]);
  const [sourceName, setSourceName] = useState('');
  const capture = useRef(new ScreenCapture());
  const video = useRef<HTMLVideoElement>(null);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const barrier = useRef<Promise<unknown>>(Promise.resolve());
  const floating = useRef<FloatingWindow | null>(null);
  const [floatingMount, setFloatingMount] = useState<HTMLElement | null>(null);
  const setPlan = useCallback((value: PersonalPlan | null) => { planRef.current = value; setPlanState(value); }, []);

  const stop = useCallback((message = 'Sharing stopped. Your confirmed plan is still here.') => {
    generation.current++;
    pending.current?.abort(); pending.current = null;
    capture.current.stop();
    if (video.current) video.current.srcObject = null;
    setWatching(false); setSetup(false); setChecking(false); setBusy(false);
    setGuidance(null); setSourceName('');
    masksRef.current = []; setMasks([]);
    onSharingChange(false); setNotice(message);
    tabBridge.current.publish(sharedHandle.current, { active: false, finished: false,
      approval: false, busy: false, title: 'Sharing is off', message, where: '', target: null });
    const active = connectionRef.current, current = planRef.current;
    if (active && current) {
      setPlan({ ...current, watching: false });
      barrier.current = barrier.current.catch(() => {}).then(() => cloudApi.stopWatch(active.connection_token, current.id)).catch(() => {});
    } else if (active) {
      barrier.current = barrier.current.catch(() => {}).then(() => cloudApi.cancel(active.connection_token)).catch(() => {});
    }
  }, [onSharingChange, setPlan]);

  const disconnect = useCallback(() => {
    stop('Disconnected. Remembered keys stay saved until you choose Forget key.');
    tabBridge.current.disconnect(); sharedHandle.current = '';
    const active = connectionRef.current;
    connectionRef.current = null; setConnection(null); setPlan(null);
    if (active) void cloudApi.disconnect(active.connection_token).catch(() => {});
    const popup = floating.current; floating.current = null; setFloatingMount(null); closeFloatingWindow(popup);
  }, [stop, setPlan]);

  useEffect(() => {
    let previous = noTabGuide;
    return tabBridge.current.start(status => {
      // A navigation removes the injected overlay. Never keep observing invisibly.
      if (sharedHandle.current && capture.current.active && status.target?.handle !== sharedHandle.current) {
        stop('The tab guide disconnected. Re-enable it on your chosen tab before sharing again.');
      }
      setTabStatus(status);
      if (previous.target?.handle !== status.target?.handle || previous.target?.revision !== status.target?.revision) {
        setGuidance(current => current ? { ...current, target: null } : current);
      }
      previous = status;
    }, command => tabCommand.current(command));
  }, [stop]);

  useEffect(() => {
    const currentCapture = capture.current;
    const pagehide = () => disconnect();
    window.addEventListener('pagehide', pagehide);
    return () => {
      generation.current++; pending.current?.abort(); currentCapture.stop();
      const active = connectionRef.current; connectionRef.current = null;
      if (active) void cloudApi.disconnect(active.connection_token).catch(() => {});
      const popup = floating.current; floating.current = null; closeFloatingWindow(popup);
      onSharingChange(false); window.removeEventListener('pagehide', pagehide);
    };
  }, [disconnect, onSharingChange]);

  useEffect(() => {
    if (!connection) return;
    const timer = setTimeout(disconnect, connection.expires_in_seconds * 1000);
    return () => clearTimeout(timer);
  }, [connection, disconnect]);

  async function action(operation: (token: string, signal: AbortSignal) => Promise<PersonalPlan>) {
    const active = connectionRef.current;
    if (!active || pending.current) return;
    const epoch = generation.current;
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError('');
    try {
      await barrier.current;
      if (controller.signal.aborted) return;
      const result = await operation(active.connection_token, controller.signal);
      if (epoch === generation.current) setPlan(result);
    } catch (failure) {
      if (!controller.signal.aborted) setError((failure as Error).message);
    } finally {
      if (epoch === generation.current) setBusy(false);
      if (pending.current === controller) pending.current = null;
    }
  }

  async function startWatching(stream: MediaStream, selectedMasks: MaskArea[]) {
    const active = connectionRef.current, current = planRef.current;
    if (!active || !current || !video.current) throw new Error('Confirm your plan first.');
    const epoch = generation.current;
    const controller = new AbortController(); pending.current = controller;
    try {
      const target = tabBridge.current.status.target;
      const useTabGuide = Boolean(target && capture.current.handle === target.handle);
      if (target && !useTabGuide) throw new Error('Share the exact browser tab where you enabled the extension. Choose it under Chrome Tab / Microsoft Edge Tab, not Window.');
      sharedHandle.current = useTabGuide ? target!.handle : '';
      // Open from Start watching's click, before any await consumes user activation.
      const floatingOpened = keepGuideVisible && !useTabGuide ? await floatControl() : false;
      if (controller.signal.aborted || epoch !== generation.current) throw new DOMException('Canceled', 'AbortError');
      video.current.srcObject = stream;
      await video.current.play();
      await barrier.current;
      if (controller.signal.aborted || epoch !== generation.current) throw new DOMException('Canceled', 'AbortError');
      const result = await cloudApi.watch(active.connection_token, current.id, controller.signal);
      if (epoch !== generation.current || !capture.current.active) throw new DOMException('Canceled', 'AbortError');
      setError(''); masksRef.current = selectedMasks; setMasks(selectedMasks);
      setSourceName(stream.getVideoTracks()[0]?.label || 'Selected window');
      setPlan(result); setWatching(true); onSharingChange(true); setSetup(false);
      setNotice(keepGuideVisible && !floatingOpened && !useTabGuide
        ? 'The floating guide could not open. Use Open floating guide ball to retry in desktop Chrome or Edge.' : '');
    } catch (failure) {
      stream.getTracks().forEach(track => track.stop());
      stop('Watching did not start. Choose a window again.');
      setError((failure as Error).message);
      throw failure;
    } finally { if (pending.current === controller) pending.current = null; }
  }

  useEffect(() => {
    if (!watching || !video.current) return;
    const source = createFrameSource(video.current, () => masksRef.current);
    let previous: Uint8Array | null = null, changed = true, stableSince = Date.now();
    let lastSent = 0, active = true, waitingForFrames = false;
    const epoch = generation.current;
    const pump = async () => {
      const session = connectionRef.current, current = planRef.current;
      if (!active || !session || !current || current.finished || pending.current || !capture.current.active) return;
      if (sharedHandle.current && capture.current.handle !== sharedHandle.current) {
        stop('The shared tab changed. Re-enable the extension on the new page and share that tab again.'); return;
      }
      if (!capture.current.ready) {
        if (!waitingForFrames) {
          waitingForFrames = true;
          setGuidance({ observation: 'The shared tab is temporarily unavailable. I’ll continue when its picture returns.',
            action: '', where: '', target: null, confidence: 0, step_complete: false, disposition: 'needs_context' });
        }
        return;
      }
      if (waitingForFrames) {
        waitingForFrames = false; previous = null; changed = true; stableSince = Date.now(); setGuidance(null);
      }
      const step = current.steps[current.step_index];
      if (step.permission === 'blocked' || (step.permission === 'confirm' && !current.approved_steps.includes(current.step_index))) return;
      const thumbnail = source.sample();
      if (!thumbnail) return;
      const now = Date.now();
      if (previous && meanAbsoluteDifference(previous, thumbnail) > 8) {
        changed = true; stableSince = now; setGuidance(null);
      }
      previous = thumbnail;
      if (now - stableSince < 1200 || now - lastSent < 10000 || (!changed && now - lastSent < 20000)) return;
      lastSent = now; changed = false;
      const controller = new AbortController(); pending.current = controller; setChecking(true);
      try {
        const handle = sharedHandle.current;
        let encoded: string;
        try {
          if (handle && !await tabBridge.current.prepareFrame(handle, video.current!, controller.signal)) {
            changed = true; return;
          }
          encoded = await source.encode();
        } finally { if (handle) tabBridge.current.restore(handle); }
        const revision = tabBridge.current.status.target?.revision;
        if (!active || epoch !== generation.current || controller.signal.aborted || !capture.current.ready) return;
        const result = await cloudApi.frame(session.connection_token, current.id, current.step_index, encoded, controller.signal);
        if (!active || epoch !== generation.current || !capture.current.active) return;
        setPlan(result.plan);
        setGuidance(revision === tabBridge.current.status.target?.revision ? result.guidance : null);
        if (result.advanced) { changed = true; setNotice(result.plan.finished ? 'All steps were checked on screen.' : 'Step checked. Moving to the next step.'); }
        if (result.plan.finished || result.guidance.disposition === 'blocked') stop(result.plan.finished ? 'Plan complete. Screen sharing has stopped.' : result.guidance.observation || 'Sharing stopped for this context.');
      } catch (failure) {
        if (active && !controller.signal.aborted) {
          if (failure instanceof CloudApiError && failure.code === 'rate_limited') {
            changed = true; setNotice('Waiting briefly before the next screen check.');
          } else {
            setError((failure as Error).message);
            stop('Watching paused after an error. Review the message before restarting.');
          }
        }
      } finally {
        if (active && epoch === generation.current) setChecking(false);
        if (pending.current === controller) pending.current = null;
      }
    };
    const timer = setInterval(() => void pump(), 750);
    return () => { active = false; clearInterval(timer); };
  }, [watching, setPlan, stop]);

  async function floatControl() {
    if (floating.current) { floating.current.window.focus(); return true; }
    const epoch = generation.current;
    const opened = await openFloatingWindow(() => {
      if (!floating.current) return;
      floating.current = null; setFloatingMount(null); stop('Floating control closed. Sharing stopped.');
    }, 320, 300);
    if (opened && epoch !== generation.current) { closeFloatingWindow(opened); return false; }
    if (opened) {
      opened.window.document.body.classList.add('personal-ball-window');
      floating.current = opened; setFloatingMount(opened.mount);
    }
    else setNotice('Floating controls are unavailable. Return to this tab for guidance and Stop, or use the browser’s stop-sharing control.');
    return Boolean(opened);
  }

  const step = plan?.steps[plan.step_index];
  const needsApproval = step?.permission === 'confirm' && !plan?.approved_steps.includes(plan.step_index);
  const target = watching && !needsApproval && guidance?.disposition === 'guide' ? guidance.target : null;
  const visibleTarget = target && !masks.some(mask => target.x >= mask.x && target.x <= mask.x + mask.width
    && target.y >= mask.y && target.y <= mask.y + mask.height) ? target : null;
  tabCommand.current = command => {
    if (command === 'return') { window.focus(); return; }
    if (command === 'stop' || command === 'pause') stop(command === 'pause' ? 'Paused. Return to Guider to resume sharing.' : undefined);
    if (command === 'exit') disconnect();
    if (command === 'approve' && plan && needsApproval && watching && sharedHandle.current === tabStatus.target?.handle) {
      void action((token, signal) => cloudApi.approve(token, plan.id, plan.step_index, signal));
    }
  };
  useEffect(() => {
    if (!plan || !sharedHandle.current) return;
    const description = describeGuidance({ plan, guidance, watching, notice, error });
    tabBridge.current.publish(sharedHandle.current, { active: watching, finished: plan.finished,
      approval: Boolean(watching && description.needsApproval), busy,
      title: description.title, message: description.message,
      where: watching && !needsApproval ? guidance?.where || '' : '', target: visibleTarget });
  }, [plan, guidance, watching, notice, error, busy, needsApproval, visibleTarget, tabStatus]);
  const control = plan?.confirmed && <GuideAssistant plan={plan} guidance={guidance} watching={watching}
    checking={checking} busy={busy} notice={notice} error={error}
    onApprove={() => void action((token, signal) => cloudApi.approve(token, plan.id, plan.step_index, signal))}
    onShare={() => { window.focus(); setSetup(true); }}
    onPause={() => stop('Paused. Choose a window when you’re ready to continue.')}
    onStop={() => stop()} onExit={disconnect}
    onShowScreen={() => { window.focus(); video.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }} />;

  return <div className="automatic-guide" data-guider-controller><div className="personal-intro"><span className="eyebrow">FROM A GOAL TO THE NEXT CLICK</span><h1>Let’s work through it.</h1><p>Make a plan together. Share one window. Get the next step as your screen changes.</p></div>
    <section className="personal-card tab-guide-setup"><h2>Guide me on another tab</h2>
      <p>{tabStatus.target ? `Tab guide ready: ${tabStatus.target.label}. Share that exact browser tab to see the ball and arrows there.`
        : tabStatus.connected ? 'Extension connected. Open the website you want help with and choose “Show guidance on this tab” in the extension.'
        : 'Get the Guider extension to see the ball, step messages and click markers inside the website you are using.'}</p>
      <details><summary>Set up the tab extension</summary><ol>
        <li><a href={`${import.meta.env.BASE_URL}guider-extension.zip`} download>Download Guider tab extension</a> and extract the ZIP into a folder.</li>
        <li>Open <strong>chrome://extensions</strong> or <strong>edge://extensions</strong>, enable <strong>Developer mode</strong>, and choose <strong>Load unpacked</strong>. Select the extracted folder and pin Guider in the extensions menu.</li>
        <li>On this Guider page, open the extension and click <strong>Connect this Guider page</strong>.</li>
        <li>On your other website, open the extension and click <strong>Show guidance on this tab</strong>.</li>
        <li>Return here, confirm your plan, share that exact <strong>browser tab</strong> and press <strong>Start watching</strong>.</li>
      </ol><p>After a full page navigation, enable the extension on the new page and share again. Browser settings, extension-store pages and desktop apps cannot use in-tab arrows.</p></details>
    </section>
    {error && <p className="message error" role="alert">{error}</p>}{notice && <p className="message notice" role="status">{notice}</p>}
    {!connection ? <PersonalConnection onConnected={result => { connectionRef.current = result; setConnection(result); setError(''); }} />
      : <><div className="connected-strip"><span>{connection.display_name} connected · {connection.model}</span><button onClick={disconnect}>Disconnect</button>
        <button onClick={() => { stop(''); void cloudApi.forgetKey(connection.provider).then(() => { disconnect(); setNotice('Saved key forgotten.'); }).catch(error => setError(error.message)); }}>Forget key</button></div>
      <section className="personal-card"><form className="personal-form" onSubmit={event => {
        event.preventDefault(); stop(''); setPlan(null); setReviewed(false);
        void action((token, signal) => cloudApi.plan(token, goal.trim(), pasted.trim(), signal));
      }}><label>What would you like to do?<textarea value={goal} required maxLength={4000} disabled={busy || watching} onChange={event => setGoal(event.target.value)} placeholder="For example: install VS Code and set up my first project" /></label>
        <label>Paste steps you already have (optional)<textarea value={pasted} maxLength={16000} disabled={busy || watching} onChange={event => setPasted(event.target.value)} placeholder="Paste instructions from another assistant, a guide, or your notes." /></label>
        <button className="primary" disabled={busy || watching || !goal.trim()}>{busy ? 'Working…' : plan ? 'Create a revised plan' : 'Analyze and make a plan'}</button></form></section>
      {plan && <section className="personal-card"><h2>Review your plan</h2>{plan.assumptions.length > 0 && <ul>{plan.assumptions.map((item, i) => <li key={i}>{item}</li>)}</ul>}
        <ol className="personal-steps">{plan.steps.map((step, i) => <li key={i} className={plan.verified_steps.includes(i) ? 'checked' : ''}><strong>{plan.verified_steps.includes(i) && <Check size={15} />} {step.title}</strong><p>{step.action}</p><small>Check for: {step.success_criterion}</small>{step.permission !== 'allow' && <span className="step-permission">{step.permission === 'blocked' ? 'Outside supported scope' : 'Your approval needed before this step'}</span>}</li>)}</ol>
        {!plan.confirmed && <><label className="check-label"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed this plan. I will perform the actions myself.</label><button className="primary" disabled={!reviewed || busy} onClick={() => void action((token, signal) => cloudApi.confirm(token, plan.id, signal))}>Confirm plan</button></>}
        {plan.confirmed && !plan.finished && <div className="plan-buttons"><button className="primary" disabled={busy || watching} onClick={() => setSetup(true)}>Choose window and permissions</button><button className="text-button" onClick={() => void floatControl()} disabled={!pipSupported()}>Open floating guide ball</button>{!pipSupported() && <small>Use desktop Chrome or Edge for floating controls.</small>}</div>}
      </section>}</>}
    <section className="personal-preview" hidden={!watching}><div className="personal-preview-header"><strong>{sourceName}</strong><button className="text-button" onClick={() => stop()}>Stop sharing</button></div>
      <div className="personal-video"><video ref={video} muted autoPlay playsInline aria-label="Window watched by Guider" />
        {masks.map((mask, i) => <span className="watch-mask" key={i} style={{ left: `${mask.x * 100}%`, top: `${mask.y * 100}%`, width: `${mask.width * 100}%`, height: `${mask.height * 100}%` }} />)}
        {visibleTarget && <div className={`guide-screen-hint ${visibleTarget.x > 0.65 ? 'hint-left' : ''} ${visibleTarget.y > 0.65 ? 'hint-above' : ''}`}
          role="note" aria-label={`Screen hint: ${visibleTarget.label}`} style={{ left: `${visibleTarget.x * 100}%`, top: `${visibleTarget.y * 100}%` }}>
          <span className="guide-hint-ring" /><svg className="guide-hint-arrow" viewBox="0 0 40 40" aria-hidden="true"><path d="M36 36 7 7M7 22V7h15" /></svg>
          <span className="guide-hint-label"><small>NEXT CLICK</small>{visibleTarget.label}</span>
        </div>}
      </div><p className="personal-preview-caption">Follow the marker in your original window. This preview shows where to look.</p>
    </section>
    {setup && connection && <WatchSetup personalProvider={connection.display_name}
      floatingGuide={tabStatus.target ? undefined : { enabled: keepGuideVisible, supported: pipSupported(), onChange: setKeepGuideVisible }}
      chooseWindow={() => capture.current.start(stop, () => true, { keepOnMute: true })} onStart={startWatching} onCancel={() => stop('Window setup canceled. Nothing is being shared.')} />}
    {floatingMount ? createPortal(control, floatingMount) : control}
  </div>;
}
