import { useEffect, useState } from 'react';
import { isDemo, request } from './api';
import './settings.css';

type Role = 'analyze' | 'plan' | 'instruct' | 'observe' | 'observe_context' | 'import';
interface Binding { role: Role; provider_id: string; model: string; has_key: boolean }
interface Provider { id: string; name: string; roles: string[]; models: string[]; local: boolean }
interface Settings {
  providers: Provider[]; bindings: Binding[]; encrypted_storage_available: boolean;
  default_provider: string; daily_limit: number;
  managed_provider: string | null;
}
const roles: Record<Role, string> = {
  analyze: 'Explain screenshots', plan: 'Plan tasks', instruct: 'Write instructions',
  observe: 'Check completed steps', observe_context: 'Understand the screen', import: 'Import conversations',
};

export function ProviderSettings({ signedIn }: { signedIn: boolean }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [role, setRole] = useState<Role>('plan');
  const [providerId, setProviderId] = useState('');
  const [model, setModel] = useState('');
  const [key, setKey] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [usage, setUsage] = useState<{ calls: number; remaining: number } | null>(null);
  const provider = settings?.providers.find(item => item.id === providerId);

  async function load() {
    const [next, calls] = await Promise.all([
      request<Settings>('/providers'), request<{ calls: number; remaining: number }>('/providers/usage'),
    ]);
    setSettings(next); setUsage(calls);
  }
  useEffect(() => {
    if (!isDemo && signedIn) void load().catch(error => setMessage(error.message));
  }, [signedIn]);
  useEffect(() => {
    setKey(''); setAccepted(false);
    const binding = settings?.bindings.find(item => item.role === role);
    const chosen = settings?.providers.find(item => item.id === binding?.provider_id)
      ?? settings?.providers.find(item => item.roles.includes(role));
    setProviderId(chosen?.id ?? ''); setModel(binding?.model ?? chosen?.models[0] ?? '');
  }, [role, settings]);

  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      await request('/providers/bindings', {
        method: 'POST', body: JSON.stringify({
          role, provider_id: providerId, model, api_key: key || null, accepted,
        }),
      });
      setKey(''); await load(); setMessage('Connection saved. Watching is off until you start it again.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not save the connection.'); }
    finally { setKey(''); setBusy(false); }
  }

  return <div className="simple-page provider-settings">
    <span className="eyebrow">CHOOSE HOW GUIDER THINKS</span><h1>AI connections.</h1>
    <p className="muted">Choose a provider for each part of your guide. Keys are never displayed after saving.</p>
    {isDemo || !signedIn ? <p className="message notice">Sign in to configure saved-task connections.
      The local demo uses fixed examples. The live screen guide has its own temporary key connection.</p>
      : settings && <>
        <p>Default: {settings.default_provider}. {usage?.calls ?? 0} calls in the last 24 hours;
          {' '}{usage?.remaining ?? settings.daily_limit} remaining.</p>
        {settings.managed_provider && <p className="message notice">Managed access is active:
          {' '}{settings.managed_provider} handles your guide. Your saved connections apply when managed access ends.</p>}
        <form onSubmit={event => void save(event)}>
          <label>Purpose<select value={role} disabled={busy} onChange={event => setRole(event.target.value as Role)}>
            {Object.entries(roles).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
          </select></label>
          <label>Provider<select value={providerId} disabled={busy} onChange={event => {
            setProviderId(event.target.value); setKey(''); setAccepted(false);
            setModel(settings.providers.find(item => item.id === event.target.value)?.models[0] ?? '');
          }}>{settings.providers.filter(item => item.roles.includes(role)).map(item =>
            <option key={item.id} value={item.id}>{item.name}{item.local ? ' (local)' : ''}</option>)}</select></label>
          <label>Model{provider?.local ? <input value={model} maxLength={120} disabled={busy}
            onChange={event => setModel(event.target.value)} /> : <select value={model} disabled={busy} onChange={event => setModel(event.target.value)}>
            {provider?.models.map(value => <option key={value}>{value}</option>)}
          </select>}</label>
          {!provider?.local && <label>API key<input type="password" autoComplete="off" value={key}
            disabled={busy || !settings.encrypted_storage_available}
            placeholder="Leave blank to keep the saved key" onChange={event => setKey(event.target.value)} /></label>}
          {!provider?.local && !settings.encrypted_storage_available && <p role="status">
            Encrypted credential storage must be configured on your backend before saving remote keys.</p>}
          <label className="check-label"><input type="checkbox" checked={accepted} disabled={busy}
            onChange={event => setAccepted(event.target.checked)} />
            I agree to send the context needed for this purpose to {provider?.name ?? 'this provider'}.
            {provider?.local ? ' It runs on the backend machine.' : ' Provider usage may cost money.'}
          </label>
          <button className="primary" disabled={busy || !accepted || (!provider?.local && !settings.encrypted_storage_available)}>
            {busy ? 'Saving…' : 'Save connection'}</button>
        </form>
        <ul className="connection-list">{settings.bindings.map(binding => <li key={binding.role}>
          <span>{roles[binding.role]}: {binding.provider_id} / {binding.model}</span>
          <button className="text-button" disabled={busy} onClick={async () => {
            setBusy(true); setMessage('');
            try { await request(`/providers/bindings/${binding.role}`, { method: 'DELETE' }); await load(); }
            catch (error) { setMessage(error instanceof Error ? error.message : 'Could not remove the connection.'); }
            finally { setBusy(false); }
          }}>Remove {roles[binding.role].toLowerCase()} connection</button>
        </li>)}</ul>
      </>}
    {message && <p role="status">{message}</p>}
  </div>;
}
