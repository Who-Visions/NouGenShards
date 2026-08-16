# Tauri Frontend Framework Configuration (Vite + Next.js)

> **Source**: Tauri v2 Official Docs — Frontend Configuration  
> **Tags**: tauri, vite, nextjs, config, frontend, static-export, whovisions  
> **Domain**: nougenshards-tauri-frontend

## Vite Configuration (NouGenShards Active Setup)

NouGenShards uses **Vite + React** as the frontend bundler.

### tauri.conf.json

```json
{
  "build": {
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build",
    "devUrl": "http://localhost:5173",
    "frontendDist": "../dist"
  }
}
```

### vite.config.ts (Full Tauri-Aware Config)

```typescript
import { defineConfig } from 'vite';

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? { protocol: 'ws', host, port: 1421 }
      : undefined,
    watch: { ignored: ['**/src-tauri/**'] },
  },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    target: process.env.TAURI_ENV_PLATFORM == 'windows'
      ? 'chrome105'
      : 'safari13',
    minify: !process.env.TAURI_ENV_DEBUG ? 'esbuild' : false,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
});
```

### Key Points
- `TAURI_DEV_HOST` enables iOS physical device dev
- `strictPort: true` — Tauri expects a fixed port
- Ignore `src-tauri/` in watch to prevent Rust rebuilds from triggering Vite HMR
- `TAURI_ENV_*` env vars exposed in frontend code
- Build target: `chrome105` on Windows (Chromium), `safari13` on macOS/Linux (WebKit)

---

## Next.js Configuration (Alternative)

For projects using Next.js instead of Vite. **NouGenShards does not use Next.js**
but this reference is preserved for OpenRouter agent routing.

### Critical Requirement
Tauri does NOT support server-side rendering (SSR). You MUST use static exports:

```javascript
// next.config.mjs
const isProd = process.env.NODE_ENV === 'production';
const internalHost = process.env.TAURI_DEV_HOST || 'localhost';

const nextConfig = {
  output: 'export',       // SSG only — no SSR
  images: {
    unoptimized: true,     // Required for static export
  },
  assetPrefix: isProd ? undefined : `http://${internalHost}:3000`,
};

export default nextConfig;
```

### tauri.conf.json (Next.js)

```json
{
  "build": {
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build",
    "devUrl": "http://localhost:3000",
    "frontendDist": "../out"
  }
}
```

### Key Differences from Vite
| Aspect | Vite | Next.js |
|--------|------|---------|
| Output dir | `../dist` | `../out` |
| Dev port | `5173` | `3000` |
| Static export | Default | `output: 'export'` required |
| Image optimization | N/A | Must set `unoptimized: true` |
| SSR | N/A | FORBIDDEN — Tauri is client-only |

---

## NouGenShards Current Configuration

Our `vite.config.ts` and `src-tauri/tauri.conf.json`
are already aligned with the Vite configuration pattern above:

- `root: 'ui'` — Frontend source in `ui/` directory
- `outDir: '../dist'` — Build output matches `frontendDist`
- `target: 'chrome105'` — Windows Chromium target
- `port: 5173` with `strictPort: true`
