const $ = (id) => document.getElementById(id);
const send = async (type) => {
  $("msg").textContent = "Started. A notification reports the result.";
  await chrome.runtime.sendMessage({ type, goal: $("goal").value });
};
$("capture").addEventListener("click", () => send("capture"));
$("tube").addEventListener("click", () => send("tube"));
$("morph").addEventListener("click", () => send("morph"));
$("opts").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
