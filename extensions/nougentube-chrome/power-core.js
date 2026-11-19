// A powerSaveBlocker for the extension. No DOM and no chrome.* of its own (the power API is passed in), so it runs in node too.
// Loaded by background.js through importScripts.
// Same model as Electron's powerSaveBlocker: start(type) returns an id, stop(id) says whether it stopped, isStarted(id) says
// whether it still holds, blockers overlap, and when they disagree the stronger type wins until it stops.
// chrome.power has one global request and no ids, so this keeps the books and only tells it what actually changes.
(function (root) {
  const RANK = { "prevent-app-suspension": 1, "prevent-display-sleep": 2 };
  const LEVEL = { "prevent-app-suspension": "system", "prevent-display-sleep": "display" };   // chrome.power's names for them

  function createPowerBlocker(power) {
    const held = new Map();        // id -> type
    let next = 1, applied = null;  // applied: the type the system was last asked for, or null for none

    function apply() {
      let top = null;
      for (const type of held.values()) if (!top || RANK[type] > RANK[top]) top = type;
      if (top === applied) return;
      applied = top;
      try { if (top) power.requestKeepAwake(LEVEL[top]); else power.releaseKeepAwake(); } catch (e) { /* no power API, or no permission: the job still runs */ }
    }

    return {
      start(type) {
        if (!RANK[type]) throw new Error("unknown power save blocker type: " + type);
        const id = next++;
        held.set(id, type); apply();
        return id;
      },
      stop(id) { const had = held.delete(id); apply(); return had; },
      isStarted(id) { return held.has(id); },
      // For a worker that has just started: any hold a dead worker left in the system is not tracked, so let go of it.
      reset() { held.clear(); applied = null; try { power.releaseKeepAwake(); } catch (e) { /* nothing to release */ } },
    };
  }

  const api = { createPowerBlocker };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.createPowerBlocker = createPowerBlocker;
})(typeof self !== "undefined" ? self : globalThis);
