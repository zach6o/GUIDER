import { lazy, Suspense, useEffect, useState } from 'react';
import { supabase } from './api';
import './personal.css';
const LiveGuide = lazy(() => import('./LiveGuide').then(module => ({ default: module.LiveGuide })));

export function PersonalSite() {
  const [user, setUser] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sharing, setSharing] = useState(false);
  useEffect(() => {
    if (!supabase) { setLoading(false); return; }
    let active = true;
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) { setUser(session?.user.id ?? null); setLoading(false); }
    });
    return () => { active = false; listener.subscription.unsubscribe(); };
  }, []);
  return <div className="personal-site"><header className="personal-header"><strong>guider.</strong>
    <span>{sharing ? 'Screen sharing on' : 'A little direction, one step at a time.'}</span>
    {user && <button className="text-button" onClick={() => {
      setUser(null); setSharing(false); // Unmount capture before waiting for the network.
      void supabase!.auth.signOut({ scope: 'local' }).catch(() => setError('Local sign-out could not finish. Close this tab.'));
    }}>Sign out</button>}</header>
    {!supabase ? <p role="alert">This website needs its Supabase sign-in configuration.</p>
      : loading ? <p role="status">Opening your workspace…</p>
      : user ? <Suspense fallback={<p role="status">Opening your guide…</p>}><LiveGuide key={user} onSharingChange={setSharing} /></Suspense>
      : <section className="personal-card personal-login"><h1>Your guide, on any computer.</h1><p>Sign in to use your encrypted saved API keys. Sharing starts only when you choose a window.</p>
        <form className="personal-form" onSubmit={event => {
          event.preventDefault(); setBusy(true); setError('');
          const operation = sent ? supabase!.auth.verifyOtp({ email, token: code, type: 'email' })
            : supabase!.auth.signInWithOtp({ email, options: { shouldCreateUser: false } });
          void operation.then(result => { if (result.error) throw result.error; if (!sent) setSent(true); })
            .catch(error => setError(error.message)).finally(() => setBusy(false));
        }}>
          <label>Email<input type="email" value={email} disabled={busy || sent} required onChange={event => setEmail(event.target.value)} /></label>
          {sent && <label>Email code<input autoComplete="one-time-code" inputMode="numeric" value={code} required onChange={event => setCode(event.target.value)} /></label>}
          <button className="primary" disabled={busy}>{busy ? 'Please wait…' : sent ? 'Sign in' : 'Email me a sign-in code'}</button>
          {sent && <button type="button" className="text-button" onClick={() => { setSent(false); setCode(''); }}>Use another email or resend</button>}
        </form><p className="muted">This deployment uses invited accounts. Ask its owner to enable your account if needed.</p>
      </section>}
    {error && <p className="message error" role="alert">{error}</p>}
  </div>;
}
