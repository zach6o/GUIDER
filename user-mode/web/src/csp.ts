/**
 * The one policy, written once, for the three places it has to appear.
 *
 * A Content-Security-Policy that is maintained separately for the dev server,
 * the preview server and the built page drifts, and the copy that drifts is
 * always the one in production. So the policy is a function of where this build
 * is allowed to talk to — its API and its Supabase project, both of which are
 * build-time configuration — and every surface asks this file.
 *
 * Two directives cannot travel in a `<meta>` tag: `frame-ancestors` and
 * `sandbox` are ignored there by specification, and a browser says so in the
 * console. They are sent as a header by the dev and preview servers, and
 * **whatever serves the built files in production must send this header too**;
 * the meta tag is the floor, not the ceiling, and it leaves out what it cannot
 * carry rather than stating a rule that does not apply.
 */

export interface PolicyInput {
  /** `VITE_API_URL`, when one is configured. */
  apiUrl?: string;
  /** `VITE_SUPABASE_URL`, when the app is not running its browser demo. */
  supabaseUrl?: string;
  /** Vite's dev and preview servers serve modules and styles the built page
   *  does not have, so the relaxations live here and nowhere near a build. */
  dev?: boolean;
  /** Set for the `<meta>` copy, which drops the directives a meta tag cannot
   *  carry instead of stating them where they are ignored. */
  meta?: boolean;
}

/** The web font the stylesheet asks for, and where its files come from.
 *
 *  A self-hosted copy would need neither, and is the better end state; until
 *  then the two origins are named here rather than met with a wildcard. */
export const FONT_STYLE_ORIGIN = 'https://fonts.googleapis.com';
export const FONT_FILE_ORIGIN = 'https://fonts.gstatic.com';

/** The origin a URL belongs to, or nothing when it is absent or unparseable.
 *
 *  Unparseable configuration yields no source rather than a guess: a policy that
 *  quietly allowed everything because a variable was misspelled would be worse
 *  than one that blocks a request the developer can see blocked. */
export function originOf(url?: string): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/** The local API, which is not configuration.
 *
 *  `src/api.ts` falls back to it when `VITE_API_URL` is unset, and
 *  `src/cloudApi.ts` reaches the live guide's routes there with no override at
 *  all. A policy that left it out would block the product's own backend on every
 *  developer machine, so it is listed here rather than discovered at runtime. */
export const LOCAL_API_ORIGIN = 'http://127.0.0.1:8000';

/** Every origin this app may open a connection to, `self` included. */
export function connectSources(input: PolicyInput): string[] {
  const origins = [LOCAL_API_ORIGIN, originOf(input.apiUrl), originOf(input.supabaseUrl)]
    .filter((origin): origin is string => Boolean(origin));
  // Supabase realtime and the dev server's own reload channel are websockets to
  // the same origins, and `connect-src` governs those by scheme.
  const sockets = input.dev
    ? ['ws:', 'wss:']
    : origins.filter(origin => origin.startsWith('https:')).map(origin => origin.replace('https:', 'wss:'));
  return ["'self'", ...new Set([...origins, ...sockets])];
}

export function contentSecurityPolicy(input: PolicyInput = {}): string {
  // Vite serves modules and injects styles through script in development. The
  // built page has neither, so the relaxation must not survive the build.
  const inline = input.dev ? " 'unsafe-inline'" : '';
  return [
    "default-src 'self'",
    `script-src 'self'${inline}`,
    `style-src 'self' ${FONT_STYLE_ORIGIN}${inline}`,
    // Screenshots and mirrored frames are object URLs; the fixture example is a
    // data URI. Neither can reach another origin.
    "img-src 'self' blob: data:",
    "media-src 'self' blob:",
    `font-src 'self' ${FONT_FILE_ORIGIN}`,
    `connect-src ${connectSources(input).join(' ')}`,
    "worker-src 'self' blob:",
    // Nothing here is a plugin, a frame or a form post, so none of them is
    // allowed at all. An allowance nobody uses is an allowance nobody notices.
    "object-src 'none'",
    "frame-src 'none'",
    "form-action 'none'",
    "base-uri 'none'",
    // Honoured as a header and ignored in a meta tag, so it is only stated where
    // it does something.
    ...(input.meta ? [] : ["frame-ancestors 'none'"]),
  ].join('; ');
}

/** The headers a server in front of these files should send.
 *
 *  Kept beside the policy so the dev server, the preview server and the
 *  deployment note cannot disagree about what they are. */
export function securityHeaders(input: PolicyInput = {}): Record<string, string> {
  return {
    'Content-Security-Policy': contentSecurityPolicy(input),
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    // Capture and optional dictation still need explicit browser permission.
    'Permissions-Policy': 'camera=(), microphone=(self), geolocation=(), display-capture=(self)',
  };
}
