const $ = (id) => document.getElementById(id);

function parseTags(raw) {
  return String(raw || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

const send = async (type) => {
  showProgress("Initializing...", 10);
  const tags = parseTags($("extra-tags").value);
  await chrome.runtime.sendMessage({ type, goal: $("goal").value, tags });
};

function setBusy(isBusy) {
  $("capture").disabled = isBusy;
  $("tube").disabled = isBusy;
  $("morph").disabled = isBusy;
}

function showProgress(text, percent) {
  const card = $("progress-card");
  const fill = $("progress-fill");
  const label = $("progress-text");
  card.style.display = "block";
  fill.style.width = `${percent}%`;
  label.textContent = text;
  setBusy(true);
}

function finishProgress(text, isError = false) {
  const fill = $("progress-fill");
  const label = $("progress-text");
  const spinner = document.querySelector(".spinner");
  fill.style.width = "100%";
  if (isError) {
    fill.style.background = "var(--danger)";
    if (spinner) spinner.style.borderTopColor = "var(--danger)";
  } else {
    fill.style.background = "var(--accent-green)";
    if (spinner) spinner.style.borderTopColor = "var(--accent-green)";
  }
  label.textContent = text;
  setBusy(false);
  setTimeout(() => {
    $("progress-card").style.display = "none";
    fill.style.width = "0%";
    fill.style.background = "linear-gradient(90deg, var(--accent) 0%, #ffdf9e 50%, var(--accent) 100%)";
    if (spinner) spinner.style.borderTopColor = "var(--accent)";
  }, 4000);
}

// Restore ongoing progress if popup was closed/reopened within 30s
chrome.storage.local.get("last_progress").then(({ last_progress }) => {
  if (last_progress && (Date.now() - last_progress.timestamp < 30000)) {
    if (last_progress.step === "done") {
      finishProgress(last_progress.detail || "Completed", false);
    } else if (last_progress.step === "error") {
      finishProgress(last_progress.detail || "Failed", true);
    } else {
      showProgress(last_progress.detail || "Processing...", last_progress.percent || 30);
    }
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "progress_update") {
    if (msg.step === "error") {
      finishProgress(msg.detail || "Operation failed", true);
    } else if (msg.step === "done") {
      finishProgress(msg.detail || "Completed successfully", false);
    } else {
      showProgress(msg.detail || "Processing...", msg.percent || 30);
    }
  }
});

$("capture").addEventListener("click", () => send("capture"));
$("tube").addEventListener("click", () => send("tube"));
$("morph").addEventListener("click", () => send("morph"));
$("opts").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });

$("sidepanel-link").addEventListener("click", async (e) => {
  e.preventDefault();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && chrome.sidePanel?.open) {
    await chrome.sidePanel.open({ windowId: tab.windowId });
  } else {
    chrome.runtime.sendMessage({ type: "open_side_panel" });
  }
});

// Load live tab info & health check
chrome.runtime.sendMessage({ type: "get_active_tab" }, (res) => {
  if (res?.tab) {
    $("tab-title").textContent = res.tab.title || "Untitled Tab";
    if (res.tab.isYouTube) {
      $("tab-badge").textContent = "YouTube";
      $("tab-badge").className = "badge youtube";
    }
  }
});

chrome.runtime.sendMessage({ type: "check_health" }, (res) => {
  const badge = $("node-status");
  const name = $("node-name");
  if (res?.ok) {
    badge.className = "status-badge online";
    name.textContent = res.data?.node || res.data?.name || "Connected";
  } else {
    badge.className = "status-badge offline";
    name.textContent = "Offline";
  }
});
