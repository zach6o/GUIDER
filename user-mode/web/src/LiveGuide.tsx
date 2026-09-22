import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, Compass, Eye, EyeOff, KeyRound, LoaderCircle,
  MonitorUp, RefreshCw, ShieldCheck, Square, Unplug } from 'lucide-react';
import { cloudApi, CloudApiError } from './cloudApi';
import type { CloudGuidance } from './cloudApi';
import { ImageEditor } from './ImageEditor';
import { ScreenCapture } from './screenCapture';
import { ScreenGuideDemo } from './ScreenGuideDemo';

/**
 * The services a personal key can belong to. Model names live here because the
 * picker shows them; which one is used is still the backend's decision, checked
 * against that adapter's capability descriptor.
 */
const PROVIDERS = {
  openai: {
    label: 'OpenAI', placeholder: 'sk-…',
    policy: 'https://developers.openai.com/api/docs/guides/your-data',
    models: [{ id: 'gpt-4.1-mini', label: 'GPT-4.1 mini' }, { id: 'gpt-4.1', label: 'GPT-4.1' }],
  },
  anthropic: {
    label: 'Claude', placeholder: 'sk-ant-…',
    policy: 'https://www.anthropic.com/legal/privacy',
    models: [
      { id: 'claude-opus-5', label: 'Claude Opus 5' },
      { id: 'claude-sonnet-5', label: 'Claude Sonnet 5' },
      { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
    ],
  },
} as const;
type ProviderId = keyof typeof PROVIDERS;
const PROVIDER_IDS = Object.keys(PROVIDERS) as ProviderId[];

export function LiveGuide({ onSharingChange }: { onSharingChange: (active: boolean) => void }) {
  const [mode, setMode] = useState<'demo' | 'cloud'>('demo');
  return <>
    <div className="guide-mode-switch" role="group" aria-label="Screen guide mode">
      <button aria-pressed={mode === 'demo'} onClick={() => setMode('demo')}>Demo walkthrough</button>
      <button aria-pressed={mode === 'cloud'} onClick={() => setMode('cloud')}>AI screen guide</button>
    </div>
    {mode === 'demo' ? <ScreenGuideDemo onSharingChange={onSharingChange} /> : <CloudLiveGuide onSharingChange={onSharingChange} />}
  </>;
}

function CloudLiveGuide({ onSharingChange }: { onSharingChange: (active: boolean) => void }) {
  const capture = useRef(new ScreenCapture());
  const video = useRef<HTMLVideoElement>(null);
  const token = useRef('');
  const request = useRef<AbortController | null>(null);
  const connectRequest = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const cancelBarrier = useRef<Promise<void>>(Promise.resolve());
  const resultPanel = useRef<HTMLDivElement>(null);
  const expiry = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [provider, setProvider] = useState<ProviderId>('openai');
  const [model, setModel] = useState<string>(PROVIDERS.openai.models[0].id);
  // What the backend said it connected to, rather than what was picked here.
  const [connectedTo, setConnectedTo] = useState('');
  const service = PROVIDERS[provider];
  const [consent, setConsent] = useState(false);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [checking, setChecking] = useState(false);
  const [taking, setTaking] = useState(false);
  const [goal, setGoal] = useState('');
  const [question, setQuestion] = useState('');
  const [review, setReview] = useState<Blob | null>(null);
  const [answer, setAnswer] = useState<CloudGuidance | null>(null);
  const [checkedImage, setCheckedImage] = useState('');
  const [lastChecked, setLastChecked] = useState('');
  const [source, setSource] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const previousStep = useRef('');
  const previousGoal = useRef('');

  const cancelPending = useCallback(() => {
    generation.current++;
    request.current?.abort(); request.current = null;
    const capability = token.current;
    if (capability) {
      // A delayed cancel must finish before a replacement check reaches the server.
      cancelBarrier.current = cancelBarrier.current
        .then(() => cloudApi.cancel(capability)).catch(() => {});
    }
    setChecking(false); setTaking(false); setReview(null);
  }, []);

  const stopSharing = useCallback((message = 'Sharing stopped. Choose a window again to continue.') => {
    cancelPending();
    capture.current.stop();
    if (video.current) video.current.srcObject = null;
    setSharing(false); setPicking(false); setChecking(false); setTaking(false);
    setReview(null); setAnswer(null); setCheckedImage(''); setLastChecked('');
    setSource(''); setQuestion(''); setError('');
    previousStep.current = ''; previousGoal.current = '';
    onSharingChange(false); setNotice(message);
  }, [onSharingChange, cancelPending]);

  const disconnect = useCallback(() => {
    stopSharing('Disconnected. Your key has been cleared from this connection.');
    connectRequest.current?.abort();
    if (token.current) void cloudApi.disconnect(token.current).catch(() => {});
    token.current = ''; setApiKey(''); setConnected(false); setConnecting(false);
    if (expiry.current) clearTimeout(expiry.current);
  }, [stopSharing]);

  useEffect(() => {
    const activeCapture = capture.current;
    const cleanup = () => {
      activeCapture.stop(); request.current?.abort(); connectRequest.current?.abort();
      if (token.current) void cloudApi.disconnect(token.current).catch(() => {});
      token.current = '';
    };
    window.addEventListener('pagehide', disconnect);
    return () => {
      generation.current++; cleanup(); onSharingChange(false);
      window.removeEventListener('pagehide', disconnect);
      if (expiry.current) clearTimeout(expiry.current);
    };
  }, [onSharingChange, disconnect]);
  useEffect(() => () => { if (checkedImage) URL.revokeObjectURL(checkedImage); }, [checkedImage]);
  useEffect(() => { if (review || answer) resultPanel.current?.focus(); }, [review, answer]);

  async function connect() {
    if (!consent || connectRequest.current && !connectRequest.current.signal.aborted) return;
    const controller = new AbortController(); connectRequest.current = controller;
    setError(''); setNotice(''); setConnecting(true);
    try {
      const result = await cloudApi.connect(apiKey.trim(), provider, model, controller.signal);
      if (controller.signal.aborted) { void cloudApi.disconnect(result.connection_token).catch(() => {}); return; }
      token.current = result.connection_token;
      setApiKey(''); setConnected(true);
      expiry.current = setTimeout(() => {
        disconnect(); setNotice('Your 30-minute cloud connection expired. Connect your key again.');
      }, result.expires_in_seconds * 1000);
      setConnectedTo(result.display_name);
      setNotice(`${result.display_name} connected. Now choose the window you want help with.`);
    } catch (error) {
      if (!controller.signal.aborted) setError((error as Error).message);
    } finally {
      if (connectRequest.current === controller) connectRequest.current = null;
      if (!controller.signal.aborted) setConnecting(false);
    }
  }

  async function share() {
    if (!connected || picking) return;
    if (sharing) stopSharing('');
    const current = ++generation.current;
    setError(''); setNotice(''); setPicking(true);
    try {
      const stream = await capture.current.start(stopSharing);
      if (!stream || generation.current !== current) return;
      if (video.current) {
        video.current.srcObject = stream;
        await video.current.play();
      }
      if (generation.current !== current || !capture.current.active) return;
      setSource(stream.getVideoTracks()[0].label || 'Selected window or tab');
      setSharing(true); onSharingChange(true);
    } catch (error) {
      if (generation.current !== current) return;
      capture.current.stop();
      if (video.current) video.current.srcObject = null;
      if (error instanceof DOMException && error.name === 'NotAllowedError') {
        setNotice('Nothing was shared. Choose a window whenever you’re ready.');
      } else setError((error as Error).message);
    } finally { if (generation.current === current) setPicking(false); }
  }

  async function checkScreen() {
    if (!goal.trim()) { setError('Describe what you want to achieve first.'); return; }
    if (!video.current || !sharing || checking || taking || review) return;
    const current = ++generation.current;
    setError(''); setNotice(''); setTaking(true); setAnswer(null); setCheckedImage('');
    try {
      const frame = await capture.current.snapshot(video.current);
      if (generation.current === current) setReview(frame);
    } catch (error) {
      if (generation.current === current) setError((error as Error).message);
    } finally { if (generation.current === current) setTaking(false); }
  }

  async function sendFrame(frame: Blob) {
    if (!sharing || !token.current || !goal.trim() || request.current) return;
    const current = ++generation.current;
    const submittedGoal = goal.trim();
    const submittedQuestion = question.trim();
    const capability = token.current;
    const controller = new AbortController(); request.current = controller;
    setChecking(true); setError(''); setNotice('');
    try {
      await cancelBarrier.current;
      if (generation.current !== current || controller.signal.aborted) return;
      const result = await cloudApi.check(capability, frame, submittedGoal, submittedQuestion,
        previousGoal.current === submittedGoal ? previousStep.current : '', controller.signal);
      if (generation.current !== current || controller.signal.aborted || !capture.current.active) return;
      if (result.disposition === 'blocked') {
        stopSharing('Sharing stopped for this context. Return to a supported, nonsensitive window.');
        setNotice(result.observation); return;
      }
      setAnswer(result); setReview(null); setQuestion('');
      setCheckedImage(URL.createObjectURL(frame)); setLastChecked(new Date().toLocaleTimeString());
      previousStep.current = result.next_step; previousGoal.current = submittedGoal;
    } catch (error) {
      if (generation.current !== current || controller.signal.aborted) return;
      if (error instanceof CloudApiError && ['connection_expired', 'openai_key_rejected'].includes(error.code)) disconnect();
      setError((error as Error).message);
    } finally {
      if (generation.current === current) setChecking(false);
      if (request.current === controller) request.current = null;
    }
  }

  return <div className="live-guide">
    <div className="live-heading">
      <div><span className="eyebrow">WORK THROUGH IT TOGETHER</span><h1>A guide that sees<br />what you’re working on.</h1>
        <p>Choose a window. Check the current view. Get one clear next step.</p></div>
      <span className={sharing ? 'sharing-badge on' : 'sharing-badge'} role="status">
        {sharing ? <Eye size={16} /> : <EyeOff size={16} />}{sharing ? 'Window sharing on' : 'Window sharing off'}
      </span>
    </div>

    {error && <p className="message error" role="alert">{error}</p>}
    {notice && <p className="message notice" role="status">{notice}</p>}

    {!connected ? <section className="cloud-connect" aria-labelledby="connect-title">
      <div className="cloud-intro"><span className="brand-mark"><KeyRound size={23} /></span>
        <h2 id="connect-title">Connect your {service.label} key.</h2>
        <p>Your key connects real vision guidance. It stays in your local backend’s memory for this 30-minute connection and is cleared when you disconnect.</p>
        <div className="connection-facts"><span><CheckCircle2 size={15} /> No account setup required</span><span><ShieldCheck size={15} /> Key never saved to a file</span></div>
      </div>
      <form onSubmit={event => { event.preventDefault(); void connect(); }}>
        <label>Service<select value={provider} onChange={event => {
          const next = event.target.value as ProviderId;
          setProvider(next); setModel(PROVIDERS[next].models[0].id);
        }} disabled={connecting}>{PROVIDER_IDS.map(id => <option key={id} value={id}>{PROVIDERS[id].label}</option>)}</select></label>
        <label>{service.label} API key<input type="password" autoComplete="off" spellCheck={false} placeholder={service.placeholder} value={apiKey} minLength={20} maxLength={512} onChange={event => setApiKey(event.target.value)} required disabled={connecting} /></label>
        <label>Vision model<select value={model} onChange={event => setModel(event.target.value)} disabled={connecting}>{service.models.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="check-label"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={connecting} />I agree to send reviewed frames to {service.label} using my API account. API charges and {service.label}’s data policies apply.</label>
        <button className="primary" disabled={!consent || connecting || apiKey.trim().length < 20}>{connecting ? <><LoaderCircle className="spin" size={17} /> Connecting…</> : <>Connect {service.label} <ArrowRight size={17} /></>}</button>
        <a href={service.policy} target="_blank" rel="noreferrer" className="provider-link">Read {service.label}’s data policies</a>
      </form>
    </section> : <div className="connected-strip"><span><CheckCircle2 size={16} /> {connectedTo || service.label} connected · {model}</span><button onClick={disconnect}><Unplug size={15} /> Disconnect & clear key</button></div>}

    <section className="live-workspace" aria-label="Screen guidance workspace">
      <div className="live-goal"><label htmlFor="live-goal">What are you trying to do?</label>
        <textarea id="live-goal" value={goal} maxLength={4000} disabled={checking || taking || Boolean(review)} onChange={event => { setGoal(event.target.value); setAnswer(null); setCheckedImage(''); setLastChecked(''); setQuestion(''); previousStep.current = ''; previousGoal.current = ''; }} placeholder="For example: help me get this Python project running" /></div>
      <div className="live-toolbar"><span><MonitorUp size={17} /> Your chosen window or tab</span><div>
        <button onClick={() => void share()} disabled={!connected || picking}>{picking ? 'Choose in your browser…' : sharing ? 'Change window' : 'Share a window'}</button>
        <button className="stop-sharing" onClick={() => stopSharing()} disabled={!sharing && !picking}><Square size={13} /> Stop sharing</button>
      </div></div>
      {source && <p className="shared-source">Sharing: <strong>{source}</strong></p>}
      <div className={sharing ? 'live-preview active' : 'live-preview'}>
        <video ref={video} autoPlay muted playsInline aria-label="Live local preview of the selected window" />
        {!sharing && <div className="preview-placeholder"><MonitorUp size={39} /><h2>Your window, in view.</h2><p>Choose a nonsensitive app window or tab in the browser picker.<br />Keep passwords, banking, and private records out of view.</p><span>No audio. No recording. No automatic uploads.</span></div>}
        {sharing && <span className="preview-label"><span /> LOCAL LIVE PREVIEW · NOT UPLOADED</span>}
      </div>
      {connected && <label className="followup">Tell Guider what happened, or ask a question<input value={question} maxLength={1000} disabled={checking} onChange={event => setQuestion(event.target.value)} placeholder="For example: I cannot find the terminal. Sent with your next reviewed frame." /></label>}
      <div className="live-check-bar"><p>{sharing ? `Bring the issue into view. Only a frame you review and send will reach ${service.label}.` : 'Chrome or Edge on desktop works best. Keep Guider visible beside the shared window.'}</p>
        <button className="primary" onClick={() => void checkScreen()} disabled={!sharing || !goal.trim() || checking || taking || Boolean(review)}><ScanIcon />{taking ? 'Capturing…' : answer ? 'I did that — check again' : 'Check screen'}</button></div>
    </section>

    {review && <div className="cloud-review" ref={resultPanel} tabIndex={-1} aria-label="Review the captured screen"><ImageEditor initial={review} busy={checking} cloud={service.label} onUpload={frame => void sendFrame(frame)} onCancel={() => { setReview(null); setError(''); }} /></div>}

    {checking && <div className="checking-status"><p role="status"><LoaderCircle size={17} className="spin" /> {service.label} is checking the reviewed frame.</p><button className="text-button" onClick={() => { cancelPending(); setNotice('Check canceled. Sharing is still on. Capture a fresh frame when ready.'); }}>Cancel check</button></div>}
    {answer && <div className="live-answer" ref={resultPanel} tabIndex={-1} role="region" aria-labelledby="guidance-title">
      <div className="answer-copy"><div className="guide-heading"><span className="brand-mark"><Compass size={22} /></span><div><strong>{answer.disposition === 'needs_context' ? 'A little more context' : 'Here’s your next step'}</strong><small>From the frame checked at {lastChecked}</small></div></div>
        <p className="screen-observation">{answer.observation}</p>
        <h2 id="guidance-title">{answer.next_step || 'A little more context will help.'}</h2>
        {answer.where && <p><strong>Where</strong> {answer.where}</p>}
        {answer.check_for && <p><strong>Look for</strong> {answer.check_for}</p>}
        {answer.question && <div className="context-question"><p>{answer.question}</p></div>}
        <button className="primary" onClick={() => void checkScreen()} disabled={!sharing || checking}><RefreshCw size={16} /> Check the updated screen</button>
        <small className="privacy-note">This describes a checked frame, not a continuously verified screen. You perform every action.</small>
      </div><div className="checked-frame"><span className="eyebrow">FRAME USED FOR THIS ANSWER</span><img src={checkedImage} alt={`Reviewed frame sent to ${service.label} for this answer`} /></div>
    </div>}
    <p className="live-footnote">Local preview stays in this tab. Reviewed images pass through your local backend to {service.label}; Guider does not save these frames or answers. {service.label} retention follows your account’s policies. Stopping cannot retract a frame already sent.</p>
  </div>;
}

function ScanIcon() { return <Eye size={17} />; }
