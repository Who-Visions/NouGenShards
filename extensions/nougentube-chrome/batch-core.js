// Batch's pure logic: reading video ids and building what an item saves to the vault. No DOM, no chrome.* calls.
// Loaded before content.js (manifest order); content.js reads it as NGT_BATCH.
(function (root) {
  const ID = /^[A-Za-z0-9_-]{11}$/;

  // A video id is exactly 11 characters from [A-Za-z0-9_-]. Anything else (quotes, angle brackets, spaces) is never an id,
  // so an id can be written into HTML or a link without being able to carry markup.
  const isVideoId = s => ID.test(String(s == null ? "" : s));

  // The id from a watch, short, embed, shorts or live link, or from a bare id; null when there is none.
  function idOf(s) {
    const text = String(s == null ? "" : s);
    const m = text.match(/(?:youtu\.be\/|[?&]v=|\/shorts\/|\/embed\/|\/live\/)([A-Za-z0-9_-]{11})/) || text.trim().match(/^([A-Za-z0-9_-]{11})$/);
    return m ? m[1] : null;
  }

  // What an item saves: the summary and, while the transcript is still in memory, the transcript. The transcript is not kept
  // across a reload (it can be large), so a later save has the summary only, and says so rather than silently omitting it.
  function shardContent(item, url, transcript) {
    const head = item.title + " - YouTube\n" + url + "\n\n" + item.text;
    return transcript ? { content: head + "\n\n---\n\nTranscript:\n" + transcript, summaryOnly: false } : { content: head, summaryOnly: true };
  }

  const api = { isVideoId, idOf, shardContent };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.NGT_BATCH = api;
})(typeof self !== "undefined" ? self : globalThis);
