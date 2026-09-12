import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const web = join(root, 'user-mode', 'web');
const backend = join(root, 'user-mode', 'backend');
const windows = process.platform === 'win32';
const python = join(backend, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
const vite = join(web, 'node_modules', 'vite', 'bin', 'vite.js');
const children = new Set();
let stopping = false;

function launch(command, args, cwd, options = {}) {
  const child = spawn(command, args, { cwd, stdio: 'inherit', windowsHide: true, ...options });
  children.add(child);
  child.once('exit', () => children.delete(child));
  child.once('error', () => children.delete(child));
  return child;
}

function completed(child, label) {
  return new Promise((resolve, reject) => {
    child.once('error', error => reject(new Error(`${label}: ${error.message}`)));
    child.once('exit', (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${label} stopped (${signal || `exit ${code}`}).`));
    });
  });
}

async function run(command, args, cwd, options) {
  await completed(launch(command, args, cwd, options), command);
  if (stopping) throw new Error('Stopped.');
}

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  // Windows Python virtual environments can use a launcher subprocess.
  // Close only the process trees this launcher created, never every node/python process.
  for (const child of children) {
    if (windows && child.pid) {
      const cleanup = spawn('taskkill.exe', ['/pid', String(child.pid), '/t', '/f'],
        { windowsHide: true, stdio: 'ignore' });
      cleanup.once('error', () => child.kill('SIGTERM'));
    } else child.kill('SIGTERM');
  }
  const force = setTimeout(() => {
    for (const child of children) child.kill('SIGKILL');
  }, 5000);
  force.unref();
}

process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());

function requireSetup() {
  if (!existsSync(python) || !existsSync(vite)) {
    throw new Error('Dependencies are missing. Run npm install or pnpm install at the repository root.');
  }
}

async function setup() {
  console.log('Checking uv (Python 3.13 is required by the backend)...');
  try {
    await run('uv', ['--version'], backend);
  } catch {
    throw new Error('Install uv and Python 3.13, then run npm run setup or pnpm run setup.');
  }
  console.log('Installing the locked web dependencies...');
  // npm ships with Node. Keep one canonical frontend lockfile for both root runners.
  // Only fixed arguments enter the Windows command shell; no user input is interpolated.
  if (windows) {
    await run('cmd.exe', ['/d', '/s', '/c', 'npm.cmd ci --no-audit --no-fund'], web);
  } else {
    await run('npm', ['ci', '--no-audit', '--no-fund'], web);
  }
  console.log('Installing the locked Python dependencies...');
  await run('uv', ['sync', '--locked'], backend);
  await mkdir(join(backend, '.local'), { recursive: true });
  console.log('Setup complete. Run npm start or pnpm start.');
}

async function available(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', () => reject(new Error(
      `Port ${port} is already in use. Close the existing service and start Guider again.`,
    )));
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(resolve));
  });
}

async function start() {
  requireSetup();
  await Promise.all([available(8000), available(5173)]);
  await mkdir(join(backend, '.local'), { recursive: true });
  console.log('Applying local database migrations...');
  await run(python, ['-m', 'alembic', 'upgrade', 'head'], backend);
  console.log('\nStarting Guider at http://127.0.0.1:5173/#live');
  console.log('API docs: http://127.0.0.1:8000/docs\nPress Ctrl+C to stop both services.\n');
  const api = launch(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
    '--port', '8000', '--no-access-log'], backend);
  const frontend = launch(process.execPath, [vite, '--host', '127.0.0.1',
    '--port', '5173', '--strictPort', '--clearScreen', 'false'], web);
  for (const [child, name] of [[api, 'Backend'], [frontend, 'Web app']]) {
    completed(child, name).then(() => {
      if (!stopping) { console.error(`${name} exited; stopping Guider.`); stop(1); }
    }).catch(error => {
      if (!stopping) { console.error(error.message); stop(1); }
    });
  }
}

try {
  switch (process.argv[2]) {
    case 'setup': await setup(); break;
    case 'start': await start(); break;
    case 'build':
      requireSetup();
      await run(process.execPath, [join(web, 'node_modules', 'typescript', 'bin', 'tsc'), '-b'], web);
      await run(process.execPath, [vite, 'build'], web);
      break;
    case 'test':
      requireSetup();
      await run(process.execPath, [join(web, 'node_modules', 'vitest', 'vitest.mjs'), 'run'], web);
      await mkdir(join(backend, '.local', 'tests'), { recursive: true });
      await run(python, ['-m', 'pytest', '-q', '-o', 'cache_dir=.local/tests/cache'], backend, {
        env: { ...process.env, PYTEST_DEBUG_TEMPROOT: join(backend, '.local', 'tests') },
      });
      break;
    default: throw new Error('Use setup, start, build or test.');
  }
} catch (error) {
  if (!stopping) { console.error(`\nGuider: ${error.message}`); stop(1); }
}
