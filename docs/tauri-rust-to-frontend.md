# Tauri IPC: Calling the Frontend from Rust

> **Source**: Tauri v2 Official Docs — Rust → Frontend Communication  
> **Tags**: tauri, ipc, events, channels, emit, eval, rust, frontend, whovisions  
> **Domain**: nougenshards-tauri-ipc

## Overview

Three mechanisms for Rust → Frontend communication:

| Mechanism | Use Case | Throughput | Type Safety |
|-----------|----------|-----------|-------------|
| **Event System** | Small data, push notifications, multi-consumer | Low | None (JSON strings) |
| **Channels** | Streaming, ordered data, high throughput | High | Serde-based |
| **eval()** | Direct JS execution | N/A | None |

The `AppHandle` and `WebviewWindow` types implement the `Listener` and `Emitter` traits.

---

## Event System

### Global Events (broadcast to ALL listeners)

```rust
use tauri::{AppHandle, Emitter};

#[tauri::command]
fn download(app: AppHandle, url: String) {
  app.emit("download-started", &url).unwrap();
  for progress in [1, 15, 50, 80, 100] {
    app.emit("download-progress", progress).unwrap();
  }
  app.emit("download-finished", &url).unwrap();
}
```

### Webview-Specific Events (targeted delivery)

```rust
use tauri::{AppHandle, Emitter};

#[tauri::command]
fn login(app: AppHandle, user: String, password: String) {
  let authenticated = user == "tauri-apps" && password == "tauri";
  let result = if authenticated { "loggedIn" } else { "invalidCredentials" };
  app.emit_to("login", "login-result", result).unwrap();
}
```

### Filtered Events (multi-webview targeting)

```rust
use tauri::{AppHandle, Emitter, EventTarget};

#[tauri::command]
fn open_file(app: AppHandle, path: std::path::PathBuf) {
  app.emit_filter("open-file", path, |target| match target {
    EventTarget::WebviewWindow { label } => label == "main" || label == "file-viewer",
    _ => false,
  }).unwrap();
}
```

> **Note**: Webview-specific events are NOT delivered to global listeners.
> Use `listen_any` instead of `listen` for catch-all behavior.

### Structured Event Payloads

Payloads must implement `Serialize + Clone`. Use `#[serde(rename_all = "camelCase")]`
for JS-friendly field names:

```rust
use serde::Serialize;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DownloadStarted<'a> {
  url: &'a str,
  download_id: usize,
  content_length: usize,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DownloadProgress {
  download_id: usize,
  chunk_length: usize,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DownloadFinished {
  download_id: usize,
}
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

### Cleanup (Critical for React/Vue/Svelte)

```typescript
// React pattern
useEffect(() => {
  const unlisten = listen<number>('download-progress', (event) => {
    setProgress(event.payload);
  });
  return () => { unlisten.then((fn) => fn()); };
}, []);
```

### Common Pitfalls

1. **Don't call unlisten() before await** — `listen()` returns a Promise, not the handle
2. **Timing in setup hooks** — DOM refs may be null; use `useEffect`/`onMounted`
3. **Async listener ordering** — rapid events may arrive out-of-order; use Channels instead

---

## Channels (High-Performance Streaming)

Channels are **fast, ordered, and designed for streaming**. Used internally by Tauri
for download progress, child process output, and WebSocket messages.

### Rust Side — Tagged Enum Pattern

```rust
use tauri::{AppHandle, ipc::Channel};
use serde::Serialize;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase", rename_all_fields = "camelCase",
        tag = "event", content = "data")]
enum DownloadEvent<'a> {
  Started {
    url: &'a str,
    download_id: usize,
    content_length: usize,
  },
  Progress {
    download_id: usize,
    chunk_length: usize,
  },
  Finished {
    download_id: usize,
  },
}

#[tauri::command]
fn download(app: AppHandle, url: String, on_event: Channel<DownloadEvent>) {
  let content_length = 1000;
  let download_id = 1;

  on_event.send(DownloadEvent::Started {
    url: &url, download_id, content_length,
  }).unwrap();

  for chunk_length in [15, 150, 35, 500, 300] {
    on_event.send(DownloadEvent::Progress {
      download_id, chunk_length,
    }).unwrap();
  }

  on_event.send(DownloadEvent::Finished { download_id }).unwrap();
}
```

### Frontend Side — Channel Consumer

```typescript
import { invoke, Channel } from '@tauri-apps/api/core';

type DownloadEvent =
  | { event: 'started'; data: { url: string; downloadId: number; contentLength: number } }
  | { event: 'progress'; data: { downloadId: number; chunkLength: number } }
  | { event: 'finished'; data: { downloadId: number } };

const onEvent = new Channel<DownloadEvent>();
onEvent.onmessage = (message) => {
  console.log(`got download event ${message.event}`);
};

await invoke('download', {
  url: 'https://example.com/file.zip',
  onEvent,
});
```

### Key Channel Advantages Over Events

| Feature | Events | Channels |
|---------|--------|----------|
| Ordering guarantee | No | Yes |
| Performance | Low (eval-based) | High (binary IPC) |
| Type safety | None | Serde enums |
| Multi-consumer | Yes | No (1:1) |
| Capabilities/permissions | No | Yes |

---

## Evaluating JavaScript Directly

For one-off JS execution from Rust:

```rust
use tauri::Manager;

tauri::Builder::default()
  .setup(|app| {
    let webview = app.get_webview_window("main").unwrap();
    webview.eval("console.log('hello from Rust')")?;
    Ok(())
  })
```

> For complex scripts with Rust data interpolation, use the
> `serialize-to-javascript` crate.

---

## Listening to Events in Rust (Bidirectional)

### Global Listener

```rust
use tauri::Listener;

app.listen("download-started", |event| {
  if let Ok(payload) = serde_json::from_str::<DownloadStarted>(&event.payload()) {
    println!("downloading {}", payload.url);
  }
});
```

### Unlisten

```rust
let event_id = app.listen("download-started", |event| {});
app.unlisten(event_id);

// Conditional unlisten
let handle = app.handle().clone();
app.listen("status-changed", |event| {
  if event.data == "ready" {
    handle.unlisten(event.id);
  }
});
```

### Listen Once

```rust
app.once("ready", |event| {
  println!("app is ready");
});
```

---

## NouGenShards Application Notes

Our current `src-tauri/src/lib.rs`
uses **commands only** (request/response pattern via the Python sidecar).

**Recommended migration path for Rust → Frontend push**:

| Use Case | Recommended Mechanism |
|----------|----------------------|
| `shard-ingested` notifications | Events (`app.emit`) |
| Search result streaming | Channels (`Channel<SearchEvent>`) |
| Engine error push | Events (`app.emit_to`) |
| Research progress (OpenRouter agent) | Channels (ordered, typed) |
| Theme/config sync | Events (small payload, rare) |
