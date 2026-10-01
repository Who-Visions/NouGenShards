import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execFile } from 'child_process';
import path from 'path';

// Vite API plugin that bridges browser requests directly to live dynamic Python CLI, SQLite databases, and handoff markdown files
function liveNougenApiPlugin() {
  const pythonPath = process.env.NOUGEN_PYTHON || (process.platform === 'win32' ? 'python.exe' : 'python3');
  const projectRoot = path.resolve(__dirname);

  const runPythonCli = (args: string[]): Promise<string> => {
    return new Promise((resolve, reject) => {
      execFile(
        pythonPath,
        ['-m', 'nougen_shards.cli', ...args],
        {
          cwd: projectRoot,
          env: {
            ...process.env,
            PYTHONPATH: path.join(projectRoot, 'src'),
          },
          maxBuffer: 15 * 1024 * 1024,
        },
        (error, stdout) => {
          if (error) {
            return reject(error);
          }
          resolve(stdout.trim());
        }
      );
    });
  };

  const runPythonInline = (code: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      execFile(
        pythonPath,
        ['-c', code],
        {
          cwd: projectRoot,
          env: {
            ...process.env,
            PYTHONPATH: path.join(projectRoot, 'src'),
          },
          maxBuffer: 15 * 1024 * 1024,
        },
        (error, stdout) => {
          if (error) {
            return reject(error);
          }
          resolve(stdout.trim());
        }
      );
    });
  };

  const runDashboard = (command: string): Promise<string> => new Promise((resolve, reject) => {
    execFile(pythonPath, ['-m', 'nougen_shards.dashboard_live', command], {
      cwd: projectRoot, env: { ...process.env, PYTHONPATH: path.join(projectRoot, 'src'), PYTHONIOENCODING: 'utf-8' },
      timeout: 20000, maxBuffer: 4 * 1024 * 1024,
    }, (error, stdout) => error ? reject(error) : resolve(stdout.trim()));
  });
  const STATS_PERIODS = new Set(['24h', 'week', 'month', 'quarter', 'year']);
  const USAGE_PERIODS = new Set([...STATS_PERIODS, 'all']);
  const SCOPES = new Set(['local', 'fleet']);
  const MAX_QUERY_CHARS = 500;
  const MAX_CONCURRENT_SEARCHES = 2;
  let activeSearches = 0;
  const reject = (res: any, status: number, error: string) => { res.statusCode = status; res.end(JSON.stringify({ error })); };
  let fleetCache: { value: string; expires: number } | undefined;
  let fleetPending: Promise<string> | undefined;

  return {
    name: 'live-nougen-api',
    configureServer(server: any) {
      server.middlewares.use(async (req: any, res: any, next: any) => {
        if (!req.url.startsWith('/api/')) return next();

        const url = new URL(req.url, 'http://localhost:5173');
        const endpoint = url.pathname.replace('/api/', '');
        res.setHeader('Content-Type', 'application/json');

        try {
          // 1. Live 9-DB Substrate Status
          if (endpoint === 'engine_status') {
            const out = await runPythonInline("import json; from nougen_shards.dynamic_api import get_engine_status; print(json.dumps(get_engine_status()))");
            res.end(out);
            return;
          }

          // 2. Live Full-Text Search (Direct SQLite 9-DB Grid)
          if (endpoint === 'search_shards') {
            const query = url.searchParams.get('query') || '';
            if (query.length > MAX_QUERY_CHARS) return reject(res, 400, 'Query too long');
            if (activeSearches >= MAX_CONCURRENT_SEARCHES) return reject(res, 429, 'Too many searches in flight');
            activeSearches++;
            const child = execFile(
              pythonPath,
              ['-m', 'nougen_shards.dynamic_api', 'search', query],
              {
                cwd: projectRoot,
                env: {
                  ...process.env,
                  PYTHONPATH: path.join(projectRoot, 'src'),
                },
                maxBuffer: 25 * 1024 * 1024,
              },
              (err, stdout) => {
                activeSearches--;
                if (res.writableEnded || res.destroyed) return;
                if (err || !stdout || !stdout.trim()) {
                  res.statusCode = 503; res.end(JSON.stringify({ error: 'Memory search unavailable' }));
                  return;
                }
                res.end(stdout.trim());
              }
            );
            // Client went away (new keystroke aborted the fetch): stop burning a Python process.
            res.on('close', () => { if (!res.writableFinished) child.kill(); });
            return;
          }

          // 3. Live Growth Stats
          if (endpoint === 'memory_stats') {
            const period = url.searchParams.get('period') || 'week';
            if (!STATS_PERIODS.has(period)) return reject(res, 400, 'Invalid period');
            try {
              const out = await runPythonCli(['stats', '--period', period, '--json']);
              res.end(out);
            } catch {
              res.statusCode = 503; res.end(JSON.stringify({ error: 'Memory statistics unavailable' }));
            }
            return;
          }

          if (endpoint === 'relay_feed' || endpoint === 'identity') {
            res.end(await runDashboard(endpoint)); return;
          }

          // 5. Live Token Tracker Usage (from session_costs SQLite DB + Dailies)
          if (endpoint === 'token_usage') {
            const period = url.searchParams.get('period') || 'week';
            const scope = url.searchParams.get('scope') || 'local';
            if (!USAGE_PERIODS.has(period)) return reject(res, 400, 'Invalid period');
            if (!SCOPES.has(scope)) return reject(res, 400, 'Invalid scope');
            execFile(
              pythonPath,
              ['-m', 'nougen_shards.dynamic_api', 'usage', period, scope],
              {
                cwd: projectRoot,
                env: {
                  ...process.env,
                  PYTHONPATH: path.join(projectRoot, 'src'),
                },
              },
              (err, stdout) => {
                if (err || !stdout || !stdout.trim()) {
                  res.statusCode = 503; res.end(JSON.stringify({ error: 'Token telemetry unavailable' }));
                  return;
                }
                res.end(stdout.trim());
              }
            );
            return;
          }

          if (endpoint === 'fleet_nodes') {
            if (!fleetCache || fleetCache.expires < Date.now()) {
              fleetPending ??= runDashboard('fleet_nodes').then(value => {
                fleetCache = { value, expires: Date.now() + 15000 }; return value;
              }).finally(() => { fleetPending = undefined; });
              await fleetPending;
            }
            res.end(fleetCache!.value); return;
          }

          next();
        } catch (err: any) {
          // Full detail stays in the dev-server log; the client never sees local paths or stderr.
          console.error('[live-nougen-api]', err);
          reject(res, 500, 'Engine request failed');
        }
      });
    },
  };
}

// Frontend lives in ui/; build output goes to dist/ (tauri.conf frontendDist).
export default defineConfig({
  root: 'ui',
  plugins: [react(), liveNougenApiPlugin()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    target: 'chrome105',
  },
});
