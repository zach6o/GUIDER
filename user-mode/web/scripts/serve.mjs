/** Serve the built preview with the same policy as Vite. No public API proxy. */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { securityHeaders } from '../src/csp.ts';

const root = resolve('dist');
const headers = securityHeaders({
  apiUrl: process.env.VITE_API_URL, supabaseUrl: process.env.VITE_SUPABASE_URL,
});
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript',
  '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
  '.woff2': 'font/woff2', '.json': 'application/json' };
createServer(async (request, response) => {
  for (const [name, value] of Object.entries(headers)) response.setHeader(name, value);
  response.setHeader('Cache-Control', 'no-store');
  if (!['GET', 'HEAD'].includes(request.method)) {
    response.writeHead(405, { Allow: 'GET, HEAD' }).end(); return;
  }
  try {
    const path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    const file = resolve(root, `.${path === '/' ? '/index.html' : path}`);
    if (!file.startsWith(root + sep)) { response.writeHead(404).end(); return; }
    const body = await readFile(file);
    response.setHeader('Content-Type', mime[extname(file)] ?? 'application/octet-stream');
    response.setHeader('Content-Length', body.length);
    response.writeHead(200).end(request.method === 'HEAD' ? undefined : body);
  } catch { response.writeHead(404).end(); }
}).listen(Number(process.env.PORT || 5173), process.env.HOST || '127.0.0.1');
