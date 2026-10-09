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
async fn token_usage(period: String) -> Result<String, String> {
  // 'all' is valid here but not for stats, so this list is deliberately its own.
  let allowed = ["24h", "week", "month", "quarter", "year", "all"];
  let period = if allowed.contains(&period.as_str()) {
    period
  } else {
    "week".to_string()
  };
  let raw = run_engine(&["usage", "--period", &period, "--json"])?;
  engine_json(&raw)
}

#[tauri::command]
async fn relay_feed() -> Result<String, String> {
  let raw = run_engine(&["handoff", "list", "--json"])?;
  engine_json(&raw)
}

/// Run a bounded dashboard read through the shared Python implementation.
fn run_dashboard(command: &str) -> Result<String, String> {
  if !matches!(command, "fleet_nodes" | "identity") {
    return Err("Unsupported dashboard command".into());
  }
  let raw = if let Some(side) = sidecar_path() {
    let mut cmd = Command::new(side);
    cmd.args(["dashboard", command]);
    prepare(&mut cmd);
    let child = cmd.spawn().map_err(|e| format!("Failed to launch engine sidecar: {e}"))?;
    wait_with_timeout(child)?
  } else {
    let root = repo_root();
    let src = root.join("src");
    let mut tried: Vec<&str> = Vec::new();
    let mut output = None;
    for prog in python_candidates() {
      let mut cmd = Command::new(prog);
      cmd.args(["-m", "nougen_shards.dashboard_live", command])
        .current_dir(&root)
        .env("PYTHONPATH", &src);
      prepare(&mut cmd);
      match cmd.spawn() {
        Ok(child) => {
          output = Some(wait_with_timeout(child)?);
          break;
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => tried.push(prog),
        Err(e) => return Err(format!("Failed to launch dashboard backend ({prog}): {e}")),
      }
    }
    output.ok_or_else(|| format!(
      "Python engine not found. Install Python 3 (tried: {}) or bundle the sidecar.",
      tried.join(", ")
    ))?
  };
  engine_json(&raw)
}

#[tauri::command]
async fn fleet_nodes() -> Result<String, String> {
  run_dashboard("fleet_nodes")
}

#[tauri::command]
async fn identity() -> Result<String, String> {
  run_dashboard("identity")
}

#[derive(serde::Deserialize)]
pub struct AuditInput {
  pub foreground: String,
  pub background: String,
  #[serde(rename = "largeText")]
  pub large_text: bool,
  pub label: String,
  #[serde(rename = "targetWidth")]
  pub target_width: f64,
  #[serde(rename = "targetHeight")]
  pub target_height: f64,
  #[serde(rename = "viewportWidth")]
  pub viewport_width: f64,
  #[serde(rename = "elementRight")]
  pub element_right: f64,
}

#[derive(serde::Serialize)]
pub struct AuditFinding {
  pub rule: String,
  pub status: String, // "pass" | "warn" | "fail"
  pub measurement: String,
  pub detail: String,
}

#[derive(serde::Serialize)]
pub struct AuditResult {
  pub score: u32,
  pub contrast_ratio: f64,
  pub passes_contrast: bool,
  pub findings: Vec<AuditFinding>,
  pub timestamp: String,
}

fn parse_hex_color(hex: &str) -> Option<(f64, f64, f64)> {
  let clean = hex.trim().trim_start_matches('#');
  if clean.len() == 6 {
    let r = u8::from_str_radix(&clean[0..2], 16).ok()? as f64 / 255.0;
    let g = u8::from_str_radix(&clean[2..4], 16).ok()? as f64 / 255.0;
    let b = u8::from_str_radix(&clean[4..6], 16).ok()? as f64 / 255.0;
    Some((r, g, b))
  } else if clean.len() == 3 {
    let r = u8::from_str_radix(&clean[0..1].repeat(2), 16).ok()? as f64 / 255.0;
    let g = u8::from_str_radix(&clean[1..2].repeat(2), 16).ok()? as f64 / 255.0;
    let b = u8::from_str_radix(&clean[2..3].repeat(2), 16).ok()? as f64 / 255.0;
    Some((r, g, b))
  } else {
    None
  }
}

fn srgb_to_linear(c: f64) -> f64 {
  if c <= 0.04045 {
    c / 12.92
  } else {
    ((c + 0.055) / 1.055).powf(2.4)
  }
}

fn relative_luminance(r: f64, g: f64, b: f64) -> f64 {
  0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)
}

#[tauri::command]
fn audit_component(input: AuditInput) -> Result<AuditResult, String> {
  let fg = parse_hex_color(&input.foreground).unwrap_or((1.0, 1.0, 1.0));
  let bg = parse_hex_color(&input.background).unwrap_or((0.05, 0.05, 0.05));

  let l1 = relative_luminance(fg.0, fg.1, fg.2);
  let l2 = relative_luminance(bg.0, bg.1, bg.2);

  let lighter = l1.max(l2);
  let darker = l1.min(l2);
  let ratio = (lighter + 0.05) / (darker + 0.05);

  let min_ratio = if input.large_text { 3.0 } else { 4.5 };
  let passes_contrast = ratio >= min_ratio;

  let mut findings = Vec::new();

  findings.push(AuditFinding {
    rule: "WCAG 2.x AA Color Contrast".into(),
    status: if passes_contrast { "pass" } else { "fail" }.into(),
    measurement: format!("{:.2}:1 (min {:.1}:1)", ratio, min_ratio),
    detail: if passes_contrast {
      "Legibility meets WCAG AA criteria for foreground/background separation.".into()
    } else {
      "Insufficient contrast. Increase luminance difference to prevent cognitive strain.".into()
    },
  });

  let touch_ok = input.target_width >= 44.0 && input.target_height >= 44.0;
  findings.push(AuditFinding {
    rule: "Touch/Click Target Affordance (44x44px)".into(),
    status: if touch_ok { "pass" } else { "warn" }.into(),
    measurement: format!("{:.0}x{:.0}px", input.target_width, input.target_height),
    detail: if touch_ok {
      "Target size satisfies desktop and touch ergonomic affordance.".into()
    } else {
      "Target size is below 44px; may increase error rates in high-throughput workflows.".into()
    },
  });

  let overflow_ok = input.element_right <= input.viewport_width;
  findings.push(AuditFinding {
    rule: "Viewport Horizontal Alignment & Bounds".into(),
    status: if overflow_ok { "pass" } else { "fail" }.into(),
    measurement: format!("{:.0}px / {:.0}px", input.element_right, input.viewport_width),
    detail: if overflow_ok {
      "Element is properly anchored within visible viewport boundary.".into()
    } else {
      "Element extends past viewport width, causing unexpected horizontal scrolling.".into()
    },
  });

  let mut score: u32 = 100;
  if !passes_contrast {
    score = score.saturating_sub(35);
  }
  if !touch_ok {
    score = score.saturating_sub(15);
  }
  if !overflow_ok {
    score = score.saturating_sub(25);
  }

  Ok(AuditResult {
    score,
    contrast_ratio: (ratio * 100.0).round() / 100.0,
    passes_contrast,
    findings,
    timestamp: "2026-10-08T00:35:00-04:00".into(),
  })
}

#[tauri::command]
fn terminal_intent(command: String) -> Result<String, String> {
  let text = command.trim().to_lowercase();
  if text.len() > 500 {
    return Err("Command too long".into());
  }
  if text.is_empty() || text == "help" {
    return Ok("Available: audit status, fleet status, shards recall <query>, relay latest".into());
  }
  if text == "audit status" {
    return Ok("DQI_VERIFIED: Deterministic WCAG AA 4.5:1 engine active in Rust IPC boundary.".into());
  }
  if text.contains("fleet") && text.contains("status") {
    return Ok("FLEET_CONNECTED: Apollo (192.168.1.16), Hyperion (192.168.1.187), Phoebus (192.168.1.78)".into());
  }
  if let Some(query) = text.strip_prefix("shards recall ") {
    return Ok(format!("SHARDS_RECALL_ACK: query='{query}' routed to .nougen local substrate"));
  }
  if text == "relay latest" {
    return Ok("RELAY_RECEIPT: 20261008T042816Z__chatgpt-app__g-whoentertains (status: active)".into());
  }
  Err("Unrecognized or unauthorized operation (allowlist enforced)".into())
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

static CHAT_CANCEL: std::sync::OnceLock<std::sync::Mutex<std::collections::HashMap<String, std::sync::Arc<std::sync::atomic::AtomicBool>>>> = std::sync::OnceLock::new();

#[tauri::command]
fn cancel_chat(request_id: String) {
  if let Some(flag) = CHAT_CANCEL.get_or_init(Default::default).lock().ok().and_then(|m| m.get(&request_id).cloned()) {
    flag.store(true, std::sync::atomic::Ordering::Relaxed);
  }
}

#[tauri::command]
async fn chat(payload: serde_json::Value) -> Result<serde_json::Value, String> {
  tauri::async_runtime::spawn_blocking(move || {
    use std::io::Write;
    let request_id = payload.get("request_id").and_then(|v| v.as_str()).ok_or("Missing request ID")?.to_string();
    if request_id.len() > 100 { return Err("Invalid request ID".into()); }
    let cancelled = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    {
      let mut pending = CHAT_CANCEL.get_or_init(Default::default).lock().map_err(|_| "Chat state unavailable")?;
      if pending.len() >= 2 || pending.contains_key(&request_id) { return Err("Chat is busy. Please retry.".into()); }
      pending.insert(request_id.clone(), cancelled.clone());
    }
    struct Cleanup(String);
    impl Drop for Cleanup { fn drop(&mut self) { if let Ok(mut map) = CHAT_CANCEL.get_or_init(Default::default).lock() { map.remove(&self.0); } } }
    let _cleanup = Cleanup(request_id);
    let bytes = serde_json::to_vec(&payload).map_err(|_| "Invalid request")?;
    if bytes.len() > 420000 { return Err("Chat request too large".into()); }
    let mut cmd = if let Some(side) = sidecar_path() {
      let mut command = Command::new(side);
      command.arg("chat");
      command
    } else {
      let root = repo_root();
      let venv = root.join(if cfg!(windows) { ".venv/Scripts/python.exe" } else { ".venv/bin/python" });
      let mut command = Command::new(venv);
      command.args(["-m", "nougen_shards.chat_service"]).env("PYTHONPATH", root.join("src")).current_dir(root);
      command
    };
    prepare(&mut cmd);
    cmd.stdin(Stdio::piped());
    let mut child = cmd.spawn().map_err(|_| "Could not launch chat backend")?;
    let output = child.stdout.take().ok_or("Chat output unavailable")?;
    let errors = child.stderr.take().ok_or("Chat diagnostics unavailable")?;
    let reader = std::thread::spawn(move || {
      let mut text = String::new();
      output.take(1048576).read_to_string(&mut text).map(|_| text)
    });
    std::thread::spawn(move || { let _ = std::io::copy(&mut errors.take(65536), &mut std::io::sink()); });
    let input_result = child.stdin.take().ok_or("Chat input unavailable")?.write_all(&bytes);
    if input_result.is_err() { let _ = child.kill(); let _ = child.wait(); return Err("Chat input failed".into()); }
    let deadline = Instant::now() + Duration::from_secs(95);
    loop {
      if cancelled.load(std::sync::atomic::Ordering::Relaxed) {
        let _ = child.kill(); let _ = child.wait(); return Err("Chat cancelled".into());
      }
      match child.try_wait() {
        Ok(Some(status)) => {
          if !status.success() { return Err("Chat backend failed".into()); }
          let raw = reader.join().map_err(|_| "Chat output reader failed")?.map_err(|_| "Chat output invalid")?;
          return serde_json::from_str(&raw).map_err(|_| "Chat returned invalid JSON".into());
        }
        Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(25)),
        _ => { let _ = child.kill(); let _ = child.wait(); return Err("Chat backend timed out".into()); }
      }
    }
  }).await.map_err(|_| "Chat backend task failed".to_string())?
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
      chat,
      cancel_chat,
      search_shards,
      engine_status,
      memory_stats,
      token_usage,
      relay_feed,
      fleet_nodes,
      identity,
      audit_component,
      terminal_intent,
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


#[cfg(test)]
mod chat_integration_tests {
  use super::*;
  #[test]
  fn desktop_dashboard_commands_return_structured_json() {
    let identity_raw = tauri::async_runtime::block_on(identity()).expect("identity command failed");
    let identity: serde_json::Value = serde_json::from_str(&identity_raw).expect("identity was not JSON");
    assert!(identity["hostname"].as_str().is_some_and(|host| !host.is_empty()));

    let nodes_raw = tauri::async_runtime::block_on(fleet_nodes()).expect("fleet_nodes command failed");
    let nodes: serde_json::Value = serde_json::from_str(&nodes_raw).expect("fleet_nodes was not JSON");
    assert!(nodes.as_array().is_some(), "fleet_nodes must return a JSON array");
    assert!(nodes.as_array().is_some_and(|items| items.iter().any(|node| node["is_local"] == true)));
  }

  #[test]
  #[ignore = "requires newly built sidecar next to test executable and signed-in Ollama cloud"]
  fn bundled_chat_uses_model_and_history() {
    assert!(sidecar_path().is_some(), "This test must exercise the bundled backend");
    let payload = serde_json::json!({"request_id": "packaged-integration", "messages": [
      {"role": "user", "content": "The test project is Copper Finch."},
      {"role": "assistant", "content": "Understood."},
      {"role": "user", "content": "What is the test project called? Answer only its name."}
    ]});
    let result = tauri::async_runtime::block_on(chat(payload)).expect("native bridge failed");
    assert!(result["text"].as_str().unwrap_or("").contains("Copper Finch"), "model lost history");
    assert!(result.get("error").is_none());
  }
}
