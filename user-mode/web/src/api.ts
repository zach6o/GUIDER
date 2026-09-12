import { createClient } from '@supabase/supabase-js';
import type { GuideApi } from './types';
import { demoApi } from './demo';

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const supabase = url && key ? createClient(url, key, {
  auth: { flowType: 'pkce', persistSession: false, autoRefreshToken: true, detectSessionInUrl: true },
}) : null;
export const isDemo = !supabase;
const base = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1/guide';

async function request<T>(path: string, init: RequestInit = {}, binary = false): Promise<T> {
  const { data } = await supabase!.auth.getSession();
  if (!data.session) throw new Error('Sign in to continue.');
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${data.session.access_token}`);
  if (init.method === 'POST') headers.set('Idempotency-Key', crypto.randomUUID());
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}${path}`, { ...init, headers, cache: 'no-store' });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error?.message || 'Could not reach Guider. Please try again.');
  }
  return binary ? await response.blob() as T : (await response.json()).data as T;
}

const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) });
const remote: GuideApi = {
  create: input => post('/tasks', input),
  history: () => request('/sessions'),
  task: id => request(`/tasks/${id}`),
  session: id => request(`/sessions/${id}`),
  upload: (task, session, file, replaces) => {
    const body = new FormData();
    body.append('file', file, 'redacted-screenshot.png');
    body.append('metadata', JSON.stringify({
      session_id: session.id, expected_version: session.state_version,
      source: 'manual', purpose: 'context', captured_at: new Date().toISOString(),
      ...(replaces ? { replaces_screenshot_id: replaces.id } : {}),
    }));
    return request(`/tasks/${task.id}/screenshots`, { method: 'POST', body });
  },
  content: id => request(`/screenshots/${id}/content`, {}, true),
  analyze: (task, session, screenshot) => post(`/tasks/${task.id}/analyses`, {
    session_id: session.id, expected_version: session.state_version,
    screenshot_ids: [screenshot.id], question: task.goal,
  }),
  requestPlan: (task, session) => post(`/tasks/${task.id}/plans`, {
    session_id: session.id, expected_version: session.state_version,
  }),
  plan: id => request(`/plans/${id}`),
  confirmPlan: (plan, session) => post(`/plans/${plan.id}/confirm`, {
    expected_version: session.state_version, plan_version: plan.version,
  }),
  operation: id => request(`/operations/${id}`),
  deleteImage: id => request(`/screenshots/${id}`, { method: 'DELETE' }),
  pause: id => post(`/sessions/${id}/pause`, { reason: 'user' }),
  stop: id => post(`/sessions/${id}/stop`, { reason: 'user' }),
};
export const api: GuideApi = isDemo ? demoApi : remote;
