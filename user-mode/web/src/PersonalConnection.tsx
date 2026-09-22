import { useEffect, useRef, useState } from 'react';
import { cloudApi, hostedPersonal } from './cloudApi';
import type { ConnectionResult } from './cloudApi';

export const personalProviders = {
  openai: { name: 'OpenAI', models: ['gpt-4.1-mini', 'gpt-4.1'] },
  anthropic: { name: 'Claude', models: ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'] },
};

export function PersonalConnection({ onConnected }: { onConnected: (result: ConnectionResult) => void }) {
  const [provider, setProvider] = useState<keyof typeof personalProviders>('openai');
  const [model, setModel] = useState('gpt-4.1-mini');
  const [key, setKey] = useState('');
  const [saved, setSaved] = useState<string[]>([]);
  const [available, setAvailable] = useState(false);
  const [replace, setReplace] = useState(false);
  const [remember, setRemember] = useState(true);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [retry, setRetry] = useState(0);
  const pending = useRef<AbortController | null>(null);
  const service = personalProviders[provider];
  const useSaved = saved.includes(provider) && !replace;
  useEffect(() => {
    let active = true;
    setReady(false); setError('');
    void cloudApi.savedKeys().then(result => {
      if (active) { setSaved(result.providers ?? []); setAvailable(result.available === true); setReady(true); }
    }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; pending.current?.abort(); };
  }, [retry]);

  return <section className="personal-card"><span className="eyebrow">YOUR AI CONNECTION</span>
    <h2>Connect once. Come back whenever you need help.</h2>
    <p>{hostedPersonal ? 'Saved keys are encrypted for your account and work on your other computers after sign-in.' : 'On Windows, saved keys are encrypted for your Windows account on this PC.'} Screen sharing always asks separately.</p>
    {error && <p role="alert" className="message error">{error}</p>}
    {!ready && (error
      ? <button type="button" className="text-button" onClick={() => setRetry(value => value + 1)}>Retry backend connection</button>
      : <p role="status">Checking your Guider connection…</p>)}
    <form className="personal-form" onSubmit={event => {
      event.preventDefault();
      if (busy || !ready || !consent) return;
      const controller = new AbortController(); pending.current = controller;
      setBusy(true); setError('');
      void cloudApi.connect(key.trim(), provider, model, controller.signal, remember && available, useSaved)
        .then(result => {
          if (controller.signal.aborted) { void cloudApi.disconnect(result.connection_token).catch(() => {}); return; }
          setKey(''); onConnected(result);
        }).catch(error => { if (!controller.signal.aborted) setError(error.message); })
        .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }}>
      <label>Service<select value={provider} disabled={busy} onChange={event => {
        const next = event.target.value as keyof typeof personalProviders;
        setProvider(next); setModel(personalProviders[next].models[0]); setReplace(false); setKey(''); setConsent(false);
      }}>{Object.entries(personalProviders).map(([id, item]) => <option key={id} value={id}>{item.name}</option>)}</select></label>
      <label>Model<select value={model} disabled={busy} onChange={event => setModel(event.target.value)}>{service.models.map(model => <option key={model}>{model}</option>)}</select></label>
      {useSaved ? <div><p>A saved {service.name} key is ready. The key is never sent back to this browser.</p>
        <button type="button" className="text-button" disabled={busy} onClick={() => setReplace(true)}>Replace saved key</button>
        <button type="button" className="text-button" disabled={busy} onClick={() => {
          setBusy(true); void cloudApi.forgetKey(provider).then(() => setSaved(saved.filter(id => id !== provider)))
            .catch(error => setError(error.message)).finally(() => setBusy(false));
        }}>Forget saved key</button></div>
        : <label>{service.name} API key<input type="password" autoComplete="off" required minLength={20} maxLength={512} value={key} disabled={busy} onChange={event => setKey(event.target.value)} /></label>}
      {!useSaved && <label className="check-label"><input type="checkbox" checked={remember && available} disabled={busy || !available} onChange={event => setRemember(event.target.checked)} />Remember this key securely{!available && ' (unavailable on this server)'}</label>}
      <label className="check-label"><input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)} />Allow my goal and pasted steps to be sent to {service.name}. Screen uploads need separate permission. API usage is billed to my provider account.</label>
      <button className="primary" disabled={busy || !ready || !consent || (!useSaved && key.trim().length < 20)}>{busy ? 'Connecting…' : useSaved ? `Use saved ${service.name} key` : `Connect ${service.name}`}</button>
    </form>
  </section>;
}
