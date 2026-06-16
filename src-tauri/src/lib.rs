use std::io::Read;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

/// Hard ceiling on a single engine invocation. Cold Python / PyInstaller
/// start-up plus a substrate query should finish well inside this; anything
/// longer is treated as a hang and killed so the UI never sticks.
const ENGINE_TIMEOUT: Duration = Duration::from_secs(30);

/// Locates the repository root (parent of src-tauri) for the dev fallback path
/// that runs the Python engine in-place. Honors `NOUGEN_ROOT` so the engine can
/// be relocated without a recompile. Bundled builds use the sidecar instead and
/// never reach this.
fn repo_root() -> PathBuf {
  if let Ok(root) = std::env::var("NOUGEN_ROOT") {
    if !root.trim().is_empty() {
      return PathBuf::from(root);
    }
  }
  PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    .parent()
    .map(|p| p.to_path_buf())
    .unwrap_or_else(|| PathBuf::from("."))
}

/// Resolves the bundled engine sidecar, which Tauri places next to the main
/// executable (without the target-triple suffix). Returns `None` in dev builds
/// where no sidecar has been bundled, so we fall back to system Python.
fn sidecar_path() -> Option<PathBuf> {
  let exe = std::env::current_exe().ok()?;
  let dir = exe.parent()?;
  let name = if cfg!(windows) {
    "nougen_engine.exe"
  } else {
    "nougen_engine"
  };
  let candidate = dir.join(name);
  if candidate.is_file() {
    Some(candidate)
  } else {
    None
  }
}

/// Python launchers to try, in order, for the dev fallback.
fn python_candidates() -> &'static [&'static str] {
  if cfg!(windows) {
    &["python", "py", "python3"]
  } else {
    &["python3", "python"]
  }
}

/// Suppresses the transient console window the (console-mode) sidecar would
/// otherwise flash on Windows.
#[cfg(windows)]
fn hide_window(cmd: &mut Command) {
  use std::os::windows::process::CommandExt;
  const CREATE_NO_WINDOW: u32 = 0x0800_0000;
  cmd.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_window(_cmd: &mut Command) {}

/// Common environment for any engine launch.
fn prepare(cmd: &mut Command) {
  cmd.env("PYTHONIOENCODING", "utf-8");
  cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
  hide_window(cmd);
}

/// Waits for a spawned child up to `ENGINE_TIMEOUT`, killing it on expiry.
/// Engine payloads are small (capped result sets), so reading the pipes after
/// exit cannot deadlock on a full OS buffer.
fn wait_with_timeout(mut child: Child) -> Result<String, String> {
  let deadline = Instant::now() + ENGINE_TIMEOUT;
  loop {
    match child.try_wait() {
      Ok(Some(status)) => {
        let mut out = String::new();
        let mut err = String::new();
        if let Some(mut so) = child.stdout.take() {
          let _ = so.read_to_string(&mut out);
        }
        if let Some(mut se) = child.stderr.take() {
          let _ = se.read_to_string(&mut err);
        }
        if status.success() {
          return Ok(out.trim().to_string());
        }
        let detail = err.trim();
        return Err(format!(
          "Engine exited with {status}{}",
          if detail.is_empty() {
            String::new()
          } else {
            format!(": {detail}")
          }
        ));
      }
      Ok(None) => {
        if Instant::now() >= deadline {
          let _ = child.kill();
          let _ = child.wait();
          return Err("Engine timed out (no response within 30s)".into());
        }
        std::thread::sleep(Duration::from_millis(25));
      }
      Err(e) => return Err(format!("Engine wait failed: {e}")),
    }
  }
}

/// Runs the nougen engine with CLI-style `args` (e.g. `["search", q, "--json"]`)
/// and returns its stdout. Prefers the bundled sidecar; falls back to running
/// the Python module in-place for dev.
fn run_engine(args: &[&str]) -> Result<String, String> {
  // 1. Bundled, self-contained sidecar (release).
  if let Some(side) = sidecar_path() {
    let mut cmd = Command::new(&side);
    cmd.args(args);
    prepare(&mut cmd);
    let child = cmd
      .spawn()
      .map_err(|e| format!("Failed to launch engine sidecar: {e}"))?;
    return wait_with_timeout(child);
  }

  // 2. Dev fallback: system Python running the module from the repo.
  let root = repo_root();
  let src = root.join("src");
  let mut tried: Vec<&str> = Vec::new();
  for prog in python_candidates() {
    let mut cmd = Command::new(prog);
    cmd
      .arg("-m")
      .arg("nougen_shards.cli")
      .args(args)
      .current_dir(&root)
      .env("PYTHONPATH", &src);
    prepare(&mut cmd);
    match cmd.spawn() {
      Ok(child) => return wait_with_timeout(child),
      Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
        tried.push(prog);
        continue;
      }
      Err(e) => return Err(format!("Failed to launch engine ({prog}): {e}")),
    }
  }
  Err(format!(
    "Python engine not found. Install Python 3 (tried: {}) or bundle the sidecar.",
    tried.join(", ")
  ))
}

/// Extracts the trailing JSON payload from CLI output: the CLI prints the
/// machine-readable document last, so return everything from the first
/// character that opens a JSON value.
fn tail_json(raw: &str) -> String {
  match raw.find(|c| c == '{' || c == '[') {
    Some(pos) => raw[pos..].to_string(),
    None => raw.to_string(),
  }
}

/// Returns the trailing JSON payload only if it actually parses, so the
/// frontend always receives well-formed data or a clean error — never a
/// half-printed traceback that throws inside `JSON.parse`.
fn engine_json(raw: &str) -> Result<String, String> {
  let payload = tail_json(raw);
  match serde_json::from_str::<serde_json::Value>(&payload) {
    Ok(_) => Ok(payload),
    Err(_) => Err("Engine returned malformed output (not valid JSON)".into()),
  }
}

#[tauri::command]
async fn search_shards(query: String) -> Result<String, String> {
  if query.trim().is_empty() {
    return Ok("[]".into());
  }
  let raw = run_engine(&["search", &query, "--json"])?;
  engine_json(&raw)
}

#[tauri::command]
async fn engine_status() -> Result<String, String> {
  let raw = run_engine(&["status", "--json"])?;
  engine_json(&raw)
}

#[tauri::command]
async fn memory_stats(period: String) -> Result<String, String> {
  let allowed = ["24h", "week", "month", "quarter", "year"];
  let period = if allowed.contains(&period.as_str()) {
    period
  } else {
    "week".to_string()
  };
  let raw = run_engine(&["stats", "--period", &period, "--json"])?;
  engine_json(&raw)
}

#[tauri::command]
fn minimize_window(window: tauri::Window) {
  let _ = window.minimize();
}

#[tauri::command]
fn toggle_maximize_window(window: tauri::Window) {
  if let Ok(maximized) = window.is_maximized() {
    if maximized {
      let _ = window.unmaximize();
    } else {
      let _ = window.maximize();
    }
  }
}

#[tauri::command]
fn close_window(window: tauri::Window) {
  let _ = window.close();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let result = tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![
      search_shards,
      engine_status,
      memory_stats,
      minimize_window,
      toggle_maximize_window,
      close_window
    ])
    .run(tauri::generate_context!());

  if let Err(e) = result {
    log::error!("fatal: tauri runtime error: {e}");
    eprintln!("NouGenShards failed to start: {e}");
    std::process::exit(1);
  }
}
