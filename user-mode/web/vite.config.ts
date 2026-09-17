import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { contentSecurityPolicy, securityHeaders } from './src/csp.ts';

export default defineConfig(({ command, mode }) => {
  // Relative to this config's own directory, which is where the .env files are.
  const env = loadEnv(mode, '.', 'VITE_');
  const dev = command === 'serve';
  const input = { apiUrl: env.VITE_API_URL, supabaseUrl: env.VITE_SUPABASE_URL, dev };
  const headers = securityHeaders(input);
  return {
    plugins: [
      react(),
      {
        // The built page carries the policy itself, because a static host that
        // forgets the header should still not be able to serve a page that can
        // talk to anywhere. The header remains the stronger of the two.
        name: 'guider-csp',
        transformIndexHtml: {
          order: 'post' as const,
          handler: () => [{
            tag: 'meta',
            attrs: {
              'http-equiv': 'Content-Security-Policy',
              content: contentSecurityPolicy({ ...input, meta: true }),
            },
            injectTo: 'head-prepend' as const,
          }],
        },
      },
    ],
    server: { strictPort: true, headers },
    preview: { headers },
  };
});
