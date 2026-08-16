# Tauri IPC: Commands (Calling Rust from Frontend)

> **Source**: Tauri v2 Official Docs — IPC Commands  
> **Tags**: tauri, ipc, commands, invoke, rust, frontend, whovisions  
> **Domain**: nougenshards-tauri-ipc

## Overview

Tauri commands are the primary mechanism for calling Rust functions from the
web frontend with **type safety**. Commands can accept arguments, return values,
return errors, and run asynchronously.

---

## Basic Command Definition

```rust
// src-tauri/src/lib.rs
#[tauri::command]
fn my_custom_command() {
  println!("I was invoked from JavaScript!");
}
```

> **Note**: Commands in `lib.rs` must NOT be `pub` — the glue code generator
> creates a macro with the same name, which conflicts with public exports.

### Registering Commands

```rust
pub fn run() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![my_custom_command])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
```

### Invoking from JavaScript

```typescript
import { invoke } from '@tauri-apps/api/core';
invoke('my_custom_command');
```

---

## Commands in Separate Modules

```rust
// src-tauri/src/commands.rs
#[tauri::command]
pub fn my_custom_command() {  // pub is required here
  println!("I was invoked from JavaScript!");
}

// src-tauri/src/lib.rs
mod commands;

pub fn run() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![commands::my_custom_command])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
```

> The `commands::` prefix is for Rust only — JS still calls `invoke("my_custom_command")`.

---

## Passing Arguments

Arguments are passed as a JSON object with **camelCase** keys:

```rust
#[tauri::command]
fn my_custom_command(invoke_message: String) {
  println!("Message: {}", invoke_message);
}
```

```typescript
invoke('my_custom_command', { invokeMessage: 'Hello!' });
```

Use `#[tauri::command(rename_all = "snake_case")]` to keep snake_case in JS.

Arguments can be any type implementing `serde::Deserialize`.

---

## Returning Data

```rust
#[tauri::command]
fn my_custom_command() -> String {
  "Hello from Rust!".into()
}
```

```typescript
invoke('my_custom_command').then((msg) => console.log(msg));
```

Return types must implement `serde::Serialize`.

### Returning Array Buffers (Optimized)

```rust
use tauri::ipc::Response;
#[tauri::command]
fn read_file() -> Response {
  let data = std::fs::read("/path/to/file").unwrap();
  tauri::ipc::Response::new(data)
}
```

---

## Error Handling

Return `Result<T, String>` for simple cases:

```rust
#[tauri::command]
fn login(user: String, password: String) -> Result<String, String> {
  if user == "tauri" && password == "tauri" {
    Ok("logged_in".to_string())
  } else {
    Err("invalid credentials".to_string())
  }
}
```

```typescript
invoke('login', { user: 'tauri', password: '0j4rijw8=' })
  .then((msg) => console.log(msg))
  .catch((err) => console.error(err));
```

### Custom Error Types (Idiomatic)

```rust
#[derive(Debug, thiserror::Error)]
enum Error {
  #[error(transparent)]
  Io(#[from] std::io::Error),
}

impl serde::Serialize for Error {
  fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
  where S: serde::ser::Serializer {
    serializer.serialize_str(self.to_string().as_ref())
  }
}

#[tauri::command]
fn my_custom_command() -> Result<(), Error> {
  std::fs::File::open("path/that/does/not/exist")?;
  Ok(())
}
```

### Tagged Error Enums (Frontend-Friendly)

```rust
#[derive(serde::Serialize)]
#[serde(tag = "kind", content = "message")]
#[serde(rename_all = "camelCase")]
enum ErrorKind { Io(String), Utf8(String) }
```

Frontend receives `{ kind: 'io' | 'utf8', message: string }`.

---

## Async Commands

Async commands run on a separate `async_runtime::spawn` task (non-blocking UI):

```rust
#[tauri::command]
async fn my_custom_command(value: String) -> String {
  some_async_function().await;
  value
}
```

> **Caution**: Async functions cannot use borrowed arguments (`&str`, `State<'_, T>`).
> Workaround 1: Use owned types (`String` instead of `&str`).
> Workaround 2: Wrap return in `Result<T, ()>`.

---

## Channels (Streaming Data)

For streaming data (e.g., chunked file reads):

```rust
use tokio::io::AsyncReadExt;

#[tauri::command]
async fn load_image(path: std::path::PathBuf, reader: tauri::ipc::Channel<&[u8]>) {
  let mut file = tokio::fs::File::open(path).await.unwrap();
  let mut chunk = vec![0; 4096];
  loop {
    let len = file.read(&mut chunk).await.unwrap();
    if len == 0 { break; }
    reader.send(&chunk).unwrap();
  }
}
```

---

## Accessing Tauri Internals in Commands

### WebviewWindow

```rust
#[tauri::command]
async fn my_command(webview_window: tauri::WebviewWindow) {
  println!("Window: {}", webview_window.label());
}
```

### AppHandle

```rust
#[tauri::command]
async fn my_command(app_handle: tauri::AppHandle) {
  let app_dir = app_handle.path().app_dir();
}
```

### Managed State

```rust
struct MyState(String);

#[tauri::command]
fn my_command(state: tauri::State<MyState>) {
  assert_eq!(state.0, "some state value");
}

pub fn run() {
  tauri::Builder::default()
    .manage(MyState("some state value".into()))
    .invoke_handler(tauri::generate_handler![my_command])
    .run(tauri::generate_context!())
    .expect("error");
}
```

### Raw Request Access

```rust
#[tauri::command]
fn upload(request: tauri::ipc::Request) -> Result<(), Error> {
  let tauri::ipc::InvokeBody::Raw(data) = request.body() else {
    return Err(Error::RequestBodyMustBeRaw);
  };
  let auth = request.headers().get("Authorization");
  Ok(())
}
```

```typescript
const data = new Uint8Array([1, 2, 3]);
await __TAURI__.core.invoke('upload', data, {
  headers: { Authorization: 'apikey' },
});
```

---

## Multiple Commands

```rust
pub fn run() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![cmd_a, cmd_b, cmd_c])
    .run(tauri::generate_context!())
    .expect("error");
}
```

> **Critical**: Only ONE `invoke_handler` call — multiple calls silently discard earlier registrations.

---

## NouGenShards Implementation Reference

Our Tauri commands live in `src-tauri/src/lib.rs`:

| Command | Purpose | Engine Args |
|---------|---------|-------------|
| `search_shards` | FTS5 search | `["search", query, "--json"]` |
| `engine_status` | Substrate health | `["status", "--json"]` |
| `memory_stats` | Period analytics | `["stats", "--period", p, "--json"]` |
| `minimize_window` | Window control | N/A |
| `toggle_maximize_window` | Window control | N/A |
| `close_window` | Window control | N/A |
