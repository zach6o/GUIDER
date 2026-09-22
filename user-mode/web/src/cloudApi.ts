import { supabase } from './api';

export const hostedPersonal = Boolean(import.meta.env.VITE_PERSONAL_API_URL);

export interface PersonalPlan {
  id: string; goal: string; assumptions: string[];
  steps: { title: string; action: string; success_criterion: string; permission: 'allow' | 'confirm' | 'blocked' }[];
  confirmed: boolean; watching: boolean; step_index: number; approved_steps: number[];
  verified_steps: number[]; finished: boolean; calls_remaining: number;
}
export interface PersonalGuidance {
  observation: string; action: string; where: string; step_complete: boolean; confidence: number;
  target: { x: number; y: number; label: string } | null;
  disposition: 'guide' | 'needs_context' | 'blocked';
}
export interface ConnectionResult {
  connection_token: string; provider: string; display_name: string; model: string; expires_in_seconds: number;
}
export interface CloudGuidance {
  observation: string;
  next_step: string;
  where: string;
  check_for: string;
  question: string;
  disposition: 'guide' | 'needs_context' | 'blocked';
}

export class CloudApiError extends Error {
  constructor(message: string, public code: string) { super(message); }
}

// Hosting is explicit; the old saved-task API URL cannot redirect personal keys.
const root = (import.meta.env.VITE_PERSONAL_API_URL || 'http://127.0.0.1:8000/api/v1/local-guide').replace(/\/$/, '');

async function send<T>(path: string, token: string, init: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (hostedPersonal) {
    const { data } = await supabase!.auth.getSession();
    if (!data.session) throw new CloudApiError('Sign in to continue.', 'invalid_token');
    headers.Authorization = `Bearer ${data.session.access_token}`;
    if (token) headers['X-Guide-Connection'] = token;
  } else if (token) headers.Authorization = `Bearer ${token}`;
  if (init.signal?.aborted) throw new DOMException('Canceled', 'AbortError');
  let response: Response;
  try {
    response = await fetch(root + path, { ...init, cache: 'no-store',
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new CloudApiError(hostedPersonal ? 'Guider is waking up or unavailable. Wait a moment and retry.' : 'Could not reach Guider’s local backend on port 8000. Start the API server and retry.', 'backend_offline');
  }
  if (!response.ok) {
    if (response.status === 404 && path === '/saved-keys') {
      throw new CloudApiError(hostedPersonal
        ? 'The Guider API needs updating. Deploy the backend version that matches this website.'
        : 'The running Guider backend is out of date. Stop Guider, run npm.cmd start from the project folder, then retry.',
      'backend_outdated');
    }
    const body = await response.json().catch(() => null);
    throw new CloudApiError(body?.error?.message || 'The request could not be completed.', body?.error?.code || 'request_failed');
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}

export const cloudApi = {
  savedKeys: () => send<{ available: boolean; providers: string[] }>('/saved-keys', '', { method: 'GET' }),
  forgetKey: (provider: string) => send<void>(`/saved-keys/${encodeURIComponent(provider)}`, '', { method: 'DELETE' }),
  connect: (apiKey: string, provider: string, model: string, signal: AbortSignal, remember = false, saved = false) => send<ConnectionResult>('/connection', '', { method: 'POST', signal,
    body: JSON.stringify({ ...(saved ? { use_saved_key: true } : { api_key: apiKey }), remember_key: remember, provider, model, accepted_cloud_terms: true }) }),
  plan: (token: string, goal: string, pasted_steps: string, signal: AbortSignal) => send<PersonalPlan>('/plans', token, { method: 'POST', signal, body: JSON.stringify({ goal, pasted_steps }) }),
  confirm: (token: string, id: string, signal?: AbortSignal) => send<PersonalPlan>(`/plans/${id}/confirm`, token, { method: 'POST', signal, body: JSON.stringify({ accepted: true }) }),
  approve: (token: string, id: string, step_index: number, signal?: AbortSignal) => send<PersonalPlan>(`/plans/${id}/approve-step`, token, { method: 'POST', signal, body: JSON.stringify({ step_index, accepted: true }) }),
  watch: (token: string, id: string, signal?: AbortSignal) => send<PersonalPlan>(`/plans/${id}/watch`, token, { method: 'POST', signal, body: JSON.stringify({ accepted_automatic_frames: true, scope_reviewed: true }) }),
  stopWatch: (token: string, id: string) => send<PersonalPlan>(`/plans/${id}/watch`, token, { method: 'DELETE', keepalive: true }),
  frame: (token: string, id: string, step_index: number, image_base64: string, signal: AbortSignal) => send<{ plan: PersonalPlan; guidance: PersonalGuidance; advanced: boolean }>(`/plans/${id}/frames`, token, { method: 'POST', signal, body: JSON.stringify({ step_index, image_base64 }) }),
  disconnect: (token: string) => send<void>('/connection', token, { method: 'DELETE', keepalive: true }),
  cancel: (token: string) => send<void>('/cancel', token, { method: 'POST', body: '{}', keepalive: true }),
  async check(token: string, blob: Blob, goal: string, question: string, previousStep: string, signal: AbortSignal) {
    if (blob.size > 4 * 1024 * 1024) throw new CloudApiError('Crop this image to less than 4 MiB before sending.', 'image_too_large');
    const encoded = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('Could not read the captured frame.')); reader.readAsDataURL(blob);
    });
    if (signal.aborted) throw new DOMException('Canceled', 'AbortError');
    return send<CloudGuidance>('/checks', token, { method: 'POST', signal, body: JSON.stringify({
      goal, question, previous_step: previousStep.slice(0, 1000), image_base64: encoded, reviewed: true,
    }) });
  },
};
