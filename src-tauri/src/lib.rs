use std::path::PathBuf;
use std::process::Command;

/// Locates the repository root (parent of src-tauri) so dev builds can run
/// the Python engine in-place. Bundled builds will ship a sidecar instead.
fn repo_root() -> PathBuf {
  PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    .parent()
    .map(|p| p.to_path_buf())
    .unwrap_or_else(|| PathBuf::from("."))
}

/// Runs the nougen Python CLI with --json and returns its stdout.
fn run_engine(args: &[&str]) -> Result<String, String> {
  let root = repo_root();
  let src = root.join("src");

  let mut cmd = Command::new(if cfg!(windows) { "python" } else { "python3" });
  cmd.arg("-m")
    .arg("nougen_shards.cli")
    .args(args)
    .current_dir(&root)
    .env("PYTHONPATH", &src)
    .env("PYTHONIOENCODING", "utf-8");

  let output = cmd
    .output()
    .map_err(|e| format!("Failed to launch engine: {e}"))?;

  if !output.status.success() {
    let stderr = String::from_utf8_lossy(&output.stderr);
    return Err(format!(
      "Engine exited with {}: {}",
      output.status,
      stderr.trim()
    ));
  }

  Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
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

#[tauri::command]
async fn search_shards(query: String) -> Result<String, String> {
  if query.trim().is_empty() {
    return Ok("[]".into());
  }
  let raw = run_engine(&["search", &query, "--json"])?;
  Ok(tail_json(&raw))
}

#[tauri::command]
async fn engine_status() -> Result<String, String> {
  let raw = run_engine(&["status", "--json"])?;
  Ok(tail_json(&raw))
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
  Ok(tail_json(&raw))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
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
      memory_stats
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
