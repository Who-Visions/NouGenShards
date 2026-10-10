const $ = (id) => document.getElementById(id);

async function refreshActiveTab() {
  chrome.runtime.sendMessage({ type: "get_active_tab" }, (res) => {
    if (res?.tab) {
      $("tab-title").textContent = res.tab.title || "Untitled Tab";
      $("tab-url").textContent = res.tab.url || "";
      if (res.tab.isYouTube) {
        $("side-tube").style.display = "inline-block";
        $("side-tube").style.borderColor = "var(--warn)";
      } else {
        $("side-tube").style.display = "inline-block";
        $("side-tube").style.borderColor = "var(--line)";
      }
    } else {
      $("tab-title").textContent = "No active tab";
      $("tab-url").textContent = "";
    }
  });
}

async function refreshHealth() {
  chrome.runtime.sendMessage({ type: "check_health" }, (res) => {
    const badge = $("node-status");
    const name = $("node-name");
    if (res?.ok) {
      badge.className = "status-badge online";
      const nodeName = res.data?.node || res.data?.name || "Mesh Online";
      name.textContent = `${nodeName}`;
    } else {
      badge.className = "status-badge offline";
      name.textContent = "Offline / Unset";
    }
  });
}

function parseTags(raw) {
  return String(raw || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

function showSideProgress(text, percent) {
  const card = $("side-progress-card");
  const fill = $("side-progress-fill");
  const label = $("side-progress-text");
  if (!card) return;
  card.style.display = "block";
  fill.style.width = `${percent}%`;
  label.textContent = text;
}

function finishSideProgress(text, isError = false) {
  const card = $("side-progress-card");
  const fill = $("side-progress-fill");
  const label = $("side-progress-text");
  const spinner = card?.querySelector(".spinner");
  if (!card) return;
  fill.style.width = "100%";
  if (isError) {
    fill.style.background = "var(--danger)";
    if (spinner) spinner.style.borderTopColor = "var(--danger)";
  } else {
    fill.style.background = "var(--accent-green)";
    if (spinner) spinner.style.borderTopColor = "var(--accent-green)";
  }
  label.textContent = text;
  setTimeout(() => {
    card.style.display = "none";
    fill.style.width = "0%";
    fill.style.background = "linear-gradient(90deg, var(--accent) 0%, #ffdf9e 50%, var(--accent) 100%)";
    if (spinner) spinner.style.borderTopColor = "var(--accent)";
  }, 4000);
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "progress_update") {
    if (msg.step === "error") {
      finishSideProgress(msg.detail || "Operation failed", true);
    } else if (msg.step === "done") {
      finishSideProgress(msg.detail || "Completed successfully", false);
    } else {
      showSideProgress(msg.detail || "Processing...", msg.percent || 30);
    }
  }
});

$("side-capture").addEventListener("click", () => {
  showSideProgress("Initializing capture...", 10);
  const tags = parseTags($("side-tags").value);
  chrome.runtime.sendMessage({ type: "capture", tags });
});

$("side-morph").addEventListener("click", () => {
  showSideProgress("Initializing morph...", 10);
  chrome.runtime.sendMessage({ type: "morph" });
});

$("side-tube").addEventListener("click", () => {
  showSideProgress("Connecting to NouGenTube...", 10);
  chrome.runtime.sendMessage({ type: "tube" });
});

$("search-btn").addEventListener("click", async () => {
  const q = $("search-input").value.trim();
  if (!q) return;
  $("search-results").innerHTML = `<div class="meta">Searching...</div>`;
  chrome.runtime.sendMessage({ type: "search_shards", query: q }, (res) => {
    const box = $("search-results");
    box.innerHTML = "";
    if (!res?.ok) {
      box.innerHTML = `<div class="meta" style="color:var(--danger)">${res?.error || "Search failed"}</div>`;
      return;
    }
    const list = res.results || [];
    if (!list.length) {
      box.innerHTML = `<div class="meta">No matching shards.</div>`;
      return;
    }
    list.slice(0, 10).forEach((s) => {
      const item = document.createElement("div");
      item.className = "shard-item";
      const title = s.title || `Shard #${s.id || s.shard_id || "?"}`;
      const snippet = (s.content || s.snippet || "").slice(0, 80);
      item.innerHTML = `
        <div class="shard-title">${escapeHtml(title)}</div>
        <div class="shard-meta">${escapeHtml(snippet)}</div>
      `;
      box.appendChild(item);
    });
  });
});

$("search-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("search-btn").click();
});

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

refreshHealth();
refreshActiveTab();
setInterval(refreshActiveTab, 3000);
