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

// Personal connector must remain loopback even when the account API is hosted elsewhere.
const root = 'http://127.0.0.1:8000/api/v1/local-guide';

async function send<T>(path: string, token: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(root + path, { ...init, cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new CloudApiError('Could not reach Guider’s local backend on port 8000. Start the API server and retry.', 'backend_offline');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new CloudApiError(body?.error?.message || 'The request could not be completed.', body?.error?.code || 'request_failed');
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}

export const cloudApi = {
  connect: (apiKey: string, model: string, signal: AbortSignal) => send<{
    connection_token: string; model: string; expires_in_seconds: number;
  }>('/connection', '', { method: 'POST', signal,
    body: JSON.stringify({ api_key: apiKey, model, accepted_cloud_terms: true }) }),
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
