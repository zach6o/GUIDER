import { describe, expect, it } from 'vitest';
import { connectSources, contentSecurityPolicy, LOCAL_API_ORIGIN, originOf, securityHeaders } from './csp';

describe('reading configured origins', () => {
  it('keeps the origin and drops the path', () => {
    expect(originOf('http://127.0.0.1:8000/api/v1/guide')).toBe('http://127.0.0.1:8000');
  });

  it('yields nothing for configuration that is absent or misspelled', () => {
    // A guess here would be a policy that allowed somewhere nobody chose.
    expect(originOf(undefined)).toBeNull();
    expect(originOf('not a url')).toBeNull();
  });
});

describe('what the app may connect to', () => {
  it('always includes the local API, which is not configuration', () => {
    expect(connectSources({})).toContain(LOCAL_API_ORIGIN);
  });

  it('includes the configured Supabase project and its websocket origin', () => {
    const sources = connectSources({ supabaseUrl: 'https://abc.supabase.co' });
    expect(sources).toContain('https://abc.supabase.co');
    expect(sources).toContain('wss://abc.supabase.co');
  });

  it('lists nothing twice when the API and Supabase share an origin', () => {
    const sources = connectSources({
      apiUrl: 'https://guider.example/api', supabaseUrl: 'https://guider.example',
    });
    expect(sources.filter(source => source === 'https://guider.example')).toHaveLength(1);
  });
});

describe('the policy itself', () => {
  it('refuses framing, plugins, form posts and a rewritten base', () => {
    const policy = contentSecurityPolicy();
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("frame-src 'none'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("form-action 'none'");
    expect(policy).toContain("base-uri 'none'");
  });

  it('states nothing in a meta tag that a meta tag cannot carry', () => {
    // A browser logs a warning for frame-ancestors in a meta element, and a
    // warning nobody can act on is noise in the one console that matters.
    expect(contentSecurityPolicy({ meta: true })).not.toContain('frame-ancestors');
  });

  it('names the font origins the stylesheet actually asks for', () => {
    const policy = contentSecurityPolicy();
    expect(policy).toContain("style-src 'self' https://fonts.googleapis.com");
    expect(policy).toContain("font-src 'self' https://fonts.gstatic.com");
  });

  it('allows the object URLs screenshots and mirrored frames arrive as', () => {
    expect(contentSecurityPolicy()).toContain('img-src \'self\' blob: data:');
  });

  it('never lets the development relaxation reach a build', () => {
    // The dev server injects modules and styles inline; the built page has
    // neither, and a policy that kept the allowance would be a policy that
    // permitted an injected script for no reason at all.
    expect(contentSecurityPolicy({ dev: true })).toContain("script-src 'self' 'unsafe-inline'");
    expect(contentSecurityPolicy({ dev: false })).toContain("script-src 'self';");
    expect(contentSecurityPolicy({ dev: false })).not.toContain('unsafe-inline');
  });
});

describe('the headers in front of the files', () => {
  it('carries the same policy as the page', () => {
    const headers = securityHeaders({ supabaseUrl: 'https://abc.supabase.co' });
    expect(headers['Content-Security-Policy'])
      .toBe(contentSecurityPolicy({ supabaseUrl: 'https://abc.supabase.co' }));
  });

  it('refuses every powerful feature except the one the guide asks for', () => {
    const permissions = securityHeaders()['Permissions-Policy'];
    expect(permissions).toContain('camera=()');
    expect(permissions).toContain('microphone=(self)');
    expect(permissions).toContain('display-capture=(self)');
  });
});
