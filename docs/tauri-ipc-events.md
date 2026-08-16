# Tauri IPC: Event System (Frontend ↔ Rust Communication)

> **Source**: Tauri v2 Official Docs — Event System  
> **Tags**: tauri, ipc, events, emit, listen, rust, frontend, whovisions  
> **Domain**: nougenshards-tauri-ipc

## Overview

The event system is a **simpler, dynamic** communication mechanism compared to
commands. Events are:
- Always **async**
- Not type-safe (unlike commands)
- Cannot return values
- Only support **JSON payloads**

Use events for fire-and-forget notifications, state change broadcasts, and
cross-webview communication.

---

## Emitting Events (Frontend → Rust)

### Global Events (delivered to ALL listeners)

```typescript
import { emit } from '@tauri-apps/api/event';
emit('file-selected', '/path/to/file');

// Or from a webview window instance:
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';
const appWebview = getCurrentWebviewWindow();
appWebview.emit('route-changed', { url: window.location.href });
```

### Webview-Specific Events (targeted to a specific webview)

```typescript
import { emitTo } from '@tauri-apps/api/event';
emitTo('settings', 'settings-update-requested', {
  key: 'notification',
  value: 'all',
});
```

> **Note**: Webview-specific events are NOT delivered to global listeners.
> To catch all events, use `{ target: { kind: 'Any' } }` option.

```typescript
import { listen } from '@tauri-apps/api/event';
listen('state-changed', (event) => {
  console.log('got state changed event', event);
}, { target: { kind: 'Any' } });
```

---

## Listening to Events (Frontend)

### Global Listener

```typescript
import { listen } from '@tauri-apps/api/event';

type DownloadStarted = {
  url: string;
  downloadId: number;
  contentLength: number;
};

listen<DownloadStarted>('download-started', (event) => {
  console.log(`downloading ${event.payload.contentLength} bytes`);
});
```

### Webview-Specific Listener

```typescript
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';
const appWebview = getCurrentWebviewWindow();
appWebview.listen<string>('logged-in', (event) => {
  localStorage.setItem('session-token', event.payload);
});
```

### Unlisten (Cleanup)

```typescript
const unlisten = await listen('download-started', (event) => {});
unlisten(); // Stop listening
```

### Listen Once

```typescript
import { once } from '@tauri-apps/api/event';
once('ready', (event) => {});
```

---

## Common Pitfalls

### 1. Don't call unlisten before the listener resolves

```typescript
// WRONG — unlisten is still a Promise here
const unlisten = listen('sync-complete', (event) => {});
unlisten(); // This is a no-op!

// CORRECT — await the Promise first
const unlisten = await listen('sync-complete', (event) => {});
unlisten();
```

### 2. Timing in setup hooks (React/Vue/Svelte)

```typescript
// WRONG — DOM ref may not exist during setup
function MyComponent() {
  const ref = useRef(null);
  listen('scroll-to', (event) => {
    ref.current.scrollIntoView(); // ref.current may be null!
  });
  return <div ref={ref} />;
}

// CORRECT — use useEffect for post-mount
function MyComponent() {
  const ref = useRef(null);
  useEffect(() => {
    const unlisten = listen('scroll-to', (event) => {
      ref.current?.scrollIntoView();
    });
    return () => { unlisten.then((fn) => fn()); };
  }, []);
  return <div ref={ref} />;
}
```

### 3. Event ordering with async listeners

Rapid-fire events + async listeners = out-of-order processing.
For ordered, high-throughput data → use **Channels** instead.

---

## Framework-Specific Cleanup

### React

```typescript
import { useEffect, useState } from 'react';
import { listen } from '@tauri-apps/api/event';

function DownloadTracker() {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const unlisten = listen<number>('download-progress', (event) => {
      setProgress(event.payload);
    });
    return () => { unlisten.then((fn) => fn()); };
  }, []);
  return <div>Download progress: {progress}%</div>;
}
```

---

## Listening to Events in Rust

### Global Events (Rust Side)

```rust
use tauri::Listener;

pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      app.listen("download-started", |event| {
        if let Ok(payload) = serde_json::from_str::<DownloadStarted>(&event.payload()) {
          println!("downloading {}", payload.url);
        }
      });
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error");
}
```

### Webview-Specific Events (Rust Side)

```rust
use tauri::{Listener, Manager};

pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      let webview = app.get_webview_window("main").unwrap();
      webview.listen("logged-in", |event| {
        let session_token = event.data;
      });
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error");
}
```

### Unlisten (Rust)

```rust
let event_id = app.listen("download-started", |event| {});
app.unlisten(event_id);

// Or unlisten on condition:
let handle = app.handle().clone();
app.listen("status-changed", |event| {
  if event.data == "ready" {
    handle.unlisten(event.id);
  }
});
```

### Listen Once (Rust)

```rust
app.once("ready", |event| {
  println!("app is ready");
});
```

---

## NouGenShards Event Architecture

Our app currently uses **commands only** (no events yet). Future candidates
for the event system:

| Event Name | Direction | Purpose |
|-----------|-----------|---------|
| `shard-ingested` | Rust → Frontend | Notify HUD of new shard |
| `search-progress` | Rust → Frontend | Stream search progress |
| `theme-changed` | Frontend → Rust | Sync UI theme to config |
| `engine-error` | Rust → Frontend | Push error notifications |
