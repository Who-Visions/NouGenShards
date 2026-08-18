/**
 * NouGenShards — Gemini sharding lane (Apps Script) v3.
 *
 * Gemini exposes no conversation API, but Gemini Advanced exports to Docs.
 * This script turns that one click into federation: everything landing in
 * the watched Drive folder is captured into the shard grid over the node's
 * token-gated REST surface.
 *
 * v3 exposes the WHOLE node API, not just capture. Every endpoint in app.py
 * has a callable wrapper here, so this file is both a sweep daemon and a
 * general-purpose NouGenShards client you can drive from the editor:
 *
 *   GET  /health      -> ngsHealth()        node readiness, unauthenticated
 *   POST /search      -> ngsSearch()        federated recall
 *   POST /capture     -> ngsCapture()       single shard
 *   POST /sync/push   -> ngsPush()          bulk ingest (the sweep's fast path)
 *   GET  /sync/pull   -> ngsPull()          full vault export
 *
 * v3 over v2 — the four blocking fixes:
 *   1. HTTP 200 no longer read as "stored". /capture always returns 200 with
 *      {status, captured}; core.capture() returns false on dedup AND on a
 *      sqlite IntegrityError. v2 ledgered failed writes as done. Now the body
 *      is parsed and `captured` is recorded as its own ledger state.
 *   2. Ledger persists incrementally (every FLUSH_EVERY files) behind a wall
 *      clock budget. v2 wrote once at the end, so an Apps Script timeout threw
 *      away the whole sweep and the next run redid it — forever, on a big
 *      backlog. A truncated sweep now resumes instead of restarting.
 *   3. Watch folder is pinned by ID. getFoldersByName() matches ANY accessible
 *      folder with that name, including one shared TO this account — and this
 *      folder's contents become agent-readable memory. Name lookup now runs at
 *      most once, requires ownership, and refuses to guess when ambiguous.
 *   4. The Advanced Drive Service is detected at runtime. v2's PDF branch threw
 *      ReferenceError when it was not enabled, which the retry ledger read as a
 *      poison file and quarantined. Unsupported files are now marked skipped.
 *
 * Also: bulk push batching (~20x fewer round trips), real subfolder recursion,
 * original_timestamp so date windows reflect the conversation not the sweep,
 * lane-artifact guard against backup/capture feedback loops, and a dashboard()
 * that reports node health alongside lane health.
 *
 * SECURITY — read before pointing this at a shared folder.
 * This is an ingestion pipe into the substrate agents recall from. Anything in
 * the watched folder becomes fleet-wide agent context, which is the classic
 * indirect prompt injection surface: a Gemini export summarising a poisoned
 * page carries that page's text into memory. Every shard from this lane is
 * tagged `untrusted-source` and `via:gemini-export`. Recall consumers must
 * treat those tags as data-never-instructions. Keep the watch folder private.
 *
 * SETUP (once):
 *   1. Project Settings -> Script Properties:
 *        NGS_URL         = https://shards.nougenai.com
 *        NGS_TOKEN       = <node token — lives here, never in code>
 *        GEMINI_FOLDER   = Gemini Exports      (name; only used to create/pin)
 *        SCAN_SUBFOLDERS = true                (optional)
 *        USE_BULK_PUSH   = false               (optional, default false --
 *                                              true loses era-true timestamps
 *                                              on an unpatched node)
 *      GEMINI_FOLDER_ID is written automatically on first run — do not set it
 *      by hand unless you are pointing the lane at an existing folder.
 *   2. Editor -> Services -> + -> Drive API (v3). REQUIRED for PDF OCR only;
 *      without it PDFs are skipped cleanly rather than failing.
 *   3. Run setupTrigger() once, authorize when prompted.
 *   4. Run dashboard() — confirm token_set, node reachable, folder pinned.
 *   5. Run testCapture() — confirm SMOKE PASSED.
 */

var PROPS = PropertiesService.getScriptProperties();

var DEFAULT_URL     = 'https://shards.nougenai.com';
var MAX_CHUNK       = 6000;               // chars per shard — keeps recall sharp
var MAX_RETRIES     = 3;                  // per-file failures before quarantine
var LEDGER_KEY      = '__ledger';
var LEDGER_MAX_BYTES = 8500;              // Script Property values cap near 9KB
var TIME_BUDGET_MS  = 4.5 * 60 * 1000;    // leave headroom under the 6 min kill
var FLUSH_EVERY     = 5;                  // ledger writes per N files processed
var PUSH_BATCH      = 20;                 // shards per /sync/push call
var MAX_DEPTH       = 5;                  // subfolder recursion cap
var LANE_TAGS       = ['gemini', 'apps-script-lane', 'via:gemini-export',
                       'untrusted-source'];
var BACKUP_PREFIX   = 'nougenshards-backup-';
var BACKUP_FOLDER   = 'NouGenShards Backups';

var TEXTUAL_MIMES = {
  'text/plain': 1, 'text/markdown': 1, 'text/csv': 1,
  'application/json': 1, 'text/html': 1, 'text/xml': 1
};

// ====================================================================
// TRANSPORT — every endpoint goes through here
// ====================================================================

/**
 * One HTTP call against the node, with auth, retry policy and body parsing.
 * Returns {ok, code, body, fatal} and never throws on an HTTP status: callers
 * branch on `ok` so a flapping tunnel cannot wedge a sweep.
 */
function ngsRequest_(method, path, payload, opts) {
  opts = opts || {};
  var base = String(PROPS.getProperty('NGS_URL') || DEFAULT_URL).replace(/\/+$/, '');
  var token = PROPS.getProperty('NGS_TOKEN');
  if (!token && !opts.noAuth) {
    throw new Error('NGS_TOKEN script property is not set. Fix it in the UI: '
      + 'Project Settings (gear icon, left rail) -> Script Properties -> '
      + 'Add script property -> name NGS_TOKEN, value = the node\'s NGS_NODE_TOKEN. '
      + 'Then run dashboard() to confirm. No code edit is needed or sufficient.');
  }

  var params = { method: method, muteHttpExceptions: true, headers: {} };
  // The node authenticates on X-NGS-Token, not Bearer. verify_token() compares
  // it with hmac.compare_digest and 503s when NGS_NODE_TOKEN is unset upstream.
  if (token) params.headers['X-NGS-Token'] = token;
  if (payload !== null && payload !== undefined) {
    params.contentType = 'application/json';
    params.payload = JSON.stringify(payload);
  }

  var attempts = opts.attempts || 3;
  var last = { code: 0, text: '' };

  for (var i = 1; i <= attempts; i++) {
    var res = UrlFetchApp.fetch(base + path, params);
    var code = res.getResponseCode();
    last = { code: code, text: res.getContentText() };

    if (code >= 200 && code < 300) {
      return { ok: true, code: code, body: parseJson_(last.text) };
    }
    // Auth and schema rejections are deterministic — retrying burns the clock
    // and, on a sweep, walks good files toward quarantine for no reason.
    if (code === 401 || code === 403) {
      console.error('%s %s -> HTTP %s: token rejected. Check NGS_TOKEN. Not retrying.',
        method, path, code);
      return { ok: false, code: code, body: parseJson_(last.text), fatal: true };
    }
    if (code === 422) {
      console.error('%s %s -> HTTP 422: node rejected the payload shape. Not retrying. %s',
        method, path, last.text.slice(0, 300));
      return { ok: false, code: code, body: parseJson_(last.text), fatal: true };
    }
    if (code === 503) {
      console.warn('%s %s -> HTTP 503: node reports write-auth unconfigured ' +
        '(NGS_NODE_TOKEN unset upstream). Retrying in case it is mid-deploy.', method, path);
    } else {
      console.warn('%s %s attempt %s -> HTTP %s', method, path, i, code);
    }
    if (i < attempts) Utilities.sleep(1500 * i);
  }
  return { ok: false, code: last.code, body: parseJson_(last.text) };
}

function parseJson_(text) {
  try { return JSON.parse(text); } catch (e) { return text; }
}

// ====================================================================
// PUBLIC API — one wrapper per node endpoint
// ====================================================================

/** GET /health — unauthenticated readiness report. Safe to call anytime. */
function ngsHealth() {
  var r = ngsRequest_('get', '/health', null, { noAuth: true, attempts: 2 });
  if (!r.ok) return { ok: false, code: r.code };
  return { ok: true, code: r.code, health: r.body };
}

/**
 * POST /search — federated recall. Returns the shard list.
 * A FEDERATION_STATUS trailer may be appended by the node when part of the
 * corpus errored mid-sweep; it is surfaced separately rather than silently
 * counted as a result, because it means the answer has holes.
 */
function ngsSearch(query, limit) {
  if (typeof query !== 'string' || !query.trim()) {
    throw new Error('ngsSearch(query, limit) needs a query string. ' +
      'From the editor use searchShards("your query") instead — Run passes no arguments.');
  }
  var r = ngsRequest_('post', '/search', { query: query, limit: limit || 5 });
  if (!r.ok) return { ok: false, code: r.code, results: [], federation: null };
  var rows = Array.isArray(r.body) ? r.body : [];
  var federation = null;
  var results = rows.filter(function (row) {
    if (row && row.event_type === 'FEDERATION_STATUS') { federation = row; return false; }
    return true;
  });
  return { ok: true, code: r.code, results: results, federation: federation };
}

/**
 * POST /capture — one shard.
 * HTTP 200 does NOT mean stored. The node answers {status, captured} and
 * core.capture() returns false both on content dedup (benign, the shard is
 * already in the grid) and on a sqlite IntegrityError (a genuinely failed
 * write). The response cannot separate them, so `captured` is surfaced verbatim
 * and the caller decides — the sweep records it as its own ledger state rather
 * than pretending 200 was success.
 */
function ngsCapture(title, content, tags, opts) {
  if (typeof title !== 'string' || !title.trim() ||
      typeof content !== 'string' || !content.trim()) {
    throw new Error('ngsCapture(title, content, tags, opts) needs a title and content. ' +
      'From the editor use testCapture() instead — Run passes no arguments.');
  }
  opts = opts || {};
  var body = {
    event_type: opts.eventType || 'KNOWLEDGE',
    title: title,
    content: content,
    tags: tags || LANE_TAGS
  };
  if (opts.originalTimestamp) body.original_timestamp = opts.originalTimestamp;

  var r = ngsRequest_('post', '/capture', body);
  if (!r.ok) return { ok: false, captured: false, code: r.code };
  return {
    ok: true,
    captured: Boolean(r.body && r.body.captured),
    code: r.code,
    body: r.body
  };
}

/**
 * POST /sync/push — bulk ingest. The sweep's fast path: one round trip per
 * PUSH_BATCH shards instead of per shard, which is what keeps a large backlog
 * inside the Apps Script execution budget.
 * Returns the node's own {count, skipped}; skipped folds dedup together with
 * rejected rows, so treat it as informational, not as a failure count.
 */
function ngsPush(shards) {
  // The editor's Run button calls with no arguments, so `shards` arrives
  // undefined, JSON.stringify drops the key, and the node answers 422
  // "Field required" — a schema error that reads like a bug in the payload
  // builder rather than "this function takes an argument".
  if (!Array.isArray(shards) || !shards.length) {
    throw new Error('ngsPush(shards) needs a non-empty array of shard objects ' +
      '{event_type,title,content,tags}. It is called by the sweep, not by hand — ' +
      'to drive things from the editor use dashboard(), testCapture(), ' +
      'searchShards("query") or syncGeminiExports().');
  }
  var r = ngsRequest_('post', '/sync/push', { shards: shards });
  if (!r.ok) return { ok: false, code: r.code, count: 0, skipped: 0 };
  return {
    ok: true,
    code: r.code,
    count: (r.body && r.body.count) || 0,
    skipped: (r.body && r.body.skipped) || 0
  };
}

/** GET /sync/pull — full vault export. Large; two attempts, no tight retry. */
function ngsPull() {
  var r = ngsRequest_('get', '/sync/pull', null, { attempts: 2 });
  if (!r.ok) return { ok: false, code: r.code, shards: [] };
  var shards = Array.isArray(r.body) ? r.body : (r.body && r.body.shards) || [];
  return { ok: true, code: r.code, shards: shards };
}

// ====================================================================
// SWEEP
// ====================================================================

function syncGeminiExports() {
  var t0 = Date.now();

  // Fail fast on missing config. Without this a token-less lane sweeps an empty
  // folder, never reaches a network call, and logs an all-zero success — which
  // reads as "healthy, nothing to do" when it actually means "cannot talk to the
  // node at all". A sweep that cannot possibly capture must say so.
  var pre = preflight_();
  if (!pre.ok) {
    pre.problems.forEach(function (p) { console.error('CONFIG: %s', p); });
    console.error('sweep aborted — fix the above, then run dashboard() to confirm.');
    return { aborted: true, problems: pre.problems };
  }

  var folder = getOrCreateFolder_();
  var ledger = readLedger_();
  // DEFAULT OFF, deliberately. /sync/push does NOT forward original_timestamp
  // to core.capture() -- verified live against blade 2026-08-18: a shard sent
  // stamped 2020-01-01 came back stamped at push time. /capture DOES honour it.
  // Because capture() dedups on a content hash, a wrongly-stamped shard can
  // never be corrected -- the re-push is a silent no-op. So the lane trades
  // throughput for a date it can only get right once.
  // Flip USE_BULK_PUSH=true only against a node carrying the Space's fix
  // (commit 14ca0388), which never landed in the public repo.
  var bulk = truthy_(PROPS.getProperty('USE_BULK_PUSH'), false);
  if (bulk) {
    console.warn('USE_BULK_PUSH=true: /sync/push drops original_timestamp on an ' +
      'unpatched node, so shards will be stamped at sweep time PERMANENTLY ' +
      '(dedup blocks any later correction). Confirm the node has the fix.');
  }
  var stats = { captured: 0, deduped: 0, unchanged: 0, skipped: 0,
                failed: 0, quarantined: 0, deferred: 0,
                push_count: 0, push_skipped: 0 };

  var recurse = truthy_(PROPS.getProperty('SCAN_SUBFOLDERS'), false);
  var files = collectFiles_(folder, recurse ? MAX_DEPTH : 0);
  var pending = [];
  var processed = 0;

  for (var i = 0; i < files.length; i++) {
    // Budget guard. v2 wrote the ledger only after the whole loop, so a timeout
    // discarded every capture it had already made and the next run repeated
    // them — a backlog larger than one execution window never converged.
    if (Date.now() - t0 > TIME_BUDGET_MS) {
      stats.deferred = files.length - i;
      console.log('time budget reached — %s file(s) deferred to the next sweep',
        stats.deferred);
      break;
    }

    var entry = files[i];
    var file = entry.file;
    var id = file.getId();
    var rec = ledger[id] || {};

    if (rec.quarantined) { stats.quarantined++; continue; }
    if (rec.permanentSkip) { stats.skipped++; continue; }

    var modified = String(file.getLastUpdated().getTime());
    if (rec.modified === modified && rec.ok) { stats.unchanged++; continue; }

    try {
      var got = extractText_(file);

      if (!got.text || !got.text.trim()) {
        // Distinguish "cannot ever read this" from "read it and it was empty".
        // v2 ledgered neither, so every unsupported file was re-extracted every
        // sweep — for PDFs that meant a full OCR copy+delete every 15 minutes.
        if (got.reason === 'error') { bumpFailure_(ledger, id, file.getName(), stats); }
        else {
          ledger[id] = { name: shortName_(file), ok: true, permanentSkip: true,
                         reason: got.reason || 'empty', modified: modified,
                         at: nowIso_() };
          stats.skipped++;
        }
        if (++processed % FLUSH_EVERY === 0) writeLedger_(ledger);
        continue;
      }

      var digest = md5_(got.text);
      if (rec.digest === digest && rec.ok) {
        // Touched but textually identical (re-export, comment churn).
        rec.modified = modified;
        ledger[id] = rec;
        stats.unchanged++;
        if (++processed % FLUSH_EVERY === 0) writeLedger_(ledger);
        continue;
      }

      var shards = buildShards_(file, got.text, entry.dirName);

      if (bulk) {
        pending.push({ id: id, name: shortName_(file), modified: modified,
                       digest: digest, shards: shards });
        if (countShards_(pending) >= PUSH_BATCH) flushPending_(pending, ledger, stats);
      } else {
        captureDirect_(shards, id, shortName_(file), modified, digest, ledger, stats);
      }
    } catch (e) {
      console.warn('error on "%s": %s', file.getName(), e);
      bumpFailure_(ledger, id, file.getName(), stats);
    }

    if (++processed % FLUSH_EVERY === 0) writeLedger_(ledger);
  }

  flushPending_(pending, ledger, stats);
  writeLedger_(ledger);

  console.log(
    'gemini sweep in %sms | captured %s, deduped %s, unchanged %s, skipped %s, ' +
    'failed %s, quarantined %s, deferred %s | node counted %s new / %s skipped',
    Date.now() - t0, stats.captured, stats.deduped, stats.unchanged, stats.skipped,
    stats.failed, stats.quarantined, stats.deferred, stats.push_count, stats.push_skipped);

  return stats;
}

/** Turn one file's text into shard payloads carrying full provenance. */
function buildShards_(file, text, dirName) {
  var chunks = chunk_(text, MAX_CHUNK);
  var exported = Utilities.formatDate(file.getLastUpdated(), 'UTC',
    "yyyy-MM-dd'T'HH:mm:ss'Z'");
  var tags = LANE_TAGS.concat([
    'src-file:' + file.getId(),
    'src-mime:' + file.getMimeType(),
    'src-folder:' + dirName,
    'exported:' + exported
  ]);

  return chunks.map(function (body, idx) {
    return {
      event_type: 'KNOWLEDGE',
      title: '[GEMINI] ' + file.getName() +
             (chunks.length > 1 ? ' (' + (idx + 1) + '/' + chunks.length + ')' : ''),
      content: body,
      tags: tags,
      // Stamp the shard at the export's true era, not at sweep time, so date
      // windows and coverage histograms reflect when the conversation happened.
      original_timestamp: exported
    };
  });
}

function flushPending_(pending, ledger, stats) {
  if (!pending.length) return;

  var shards = [];
  pending.forEach(function (p) { shards = shards.concat(p.shards); });

  var r = ngsPush(shards);
  stats.push_count += r.count;
  stats.push_skipped += r.skipped;

  pending.forEach(function (p) {
    if (r.ok) {
      ledger[p.id] = { modified: p.modified, digest: p.digest, ok: true, fails: 0,
                       chunks: p.shards.length, name: p.name, at: nowIso_() };
      stats.captured += p.shards.length;
    } else {
      bumpFailure_(ledger, p.id, p.name, stats);
    }
  });
  pending.length = 0;
}

/** Per-shard path (USE_BULK_PUSH=false): finer reporting, many more round trips. */
function captureDirect_(shards, id, name, modified, digest, ledger, stats) {
  var allOk = true, anyStored = false;
  for (var i = 0; i < shards.length; i++) {
    var s = shards[i];
    var r = ngsCapture(s.title, s.content, s.tags,
      { eventType: s.event_type, originalTimestamp: s.original_timestamp });
    if (!r.ok) { allOk = false; break; }
    if (r.captured) { anyStored = true; stats.captured++; } else { stats.deduped++; }
  }
  if (allOk) {
    ledger[id] = { modified: modified, digest: digest, ok: true, fails: 0,
                   chunks: shards.length, stored: anyStored, name: name, at: nowIso_() };
  } else {
    bumpFailure_(ledger, id, name, stats);
  }
}

function countShards_(pending) {
  return pending.reduce(function (n, p) { return n + p.shards.length; }, 0);
}

// ====================================================================
// FILE DISCOVERY + EXTRACTION
// ====================================================================

/** Depth-limited walk. v2 advertised recursion but only ever read one level. */
function collectFiles_(root, depth) {
  var out = [];
  (function walk(dir, level) {
    var files = dir.getFiles();
    while (files.hasNext()) {
      var f = files.next();
      if (isLaneArtifact_(f.getName())) continue;  // never re-ingest our own output
      out.push({ file: f, dirName: dir.getName() });
    }
    if (level <= 0) return;
    var subs = dir.getFolders();
    while (subs.hasNext()) walk(subs.next(), level - 1);
  })(root, depth);
  return out;
}

/**
 * Backups written by backupVaultToDrive() are vault exports. Sweeping one back
 * in would re-ingest the entire grid as a single shard, so lane output is
 * excluded by name regardless of which folder it is sitting in.
 */
function isLaneArtifact_(name) {
  return name.indexOf(BACKUP_PREFIX) === 0;
}

/** Returns {text, reason} — reason explains a null so the caller can ledger it. */
function extractText_(file) {
  var mime = file.getMimeType();
  try {
    if (mime === MimeType.GOOGLE_DOCS) {
      return { text: DocumentApp.openById(file.getId()).getBody().getText() };
    }
    if (mime === MimeType.GOOGLE_SHEETS) {
      // Gemini data exports land as Sheets; flatten tabs to labelled CSV.
      var ss = SpreadsheetApp.openById(file.getId());
      return { text: ss.getSheets().map(function (sh) {
        return '## ' + sh.getName() + '\n' +
          sh.getDataRange().getDisplayValues().map(function (r) {
            return r.join(', ');
          }).join('\n');
      }).join('\n\n') };
    }
    if (TEXTUAL_MIMES[mime]) {
      return { text: file.getBlob().getDataAsString() };
    }
    if (mime === MimeType.PDF) {
      // Drive's OCR needs the Advanced Drive Service. v2 assumed it; when it was
      // not enabled the ReferenceError read as a poison file and the retry
      // ledger quarantined a perfectly good PDF after three sweeps.
      if (!driveAdvancedAvailable_()) {
        return { text: null, reason: 'pdf-needs-drive-service' };
      }
      var tmp = Drive.Files.create(
        { name: '__ngs_ocr_tmp', mimeType: MimeType.GOOGLE_DOCS },
        file.getBlob(), { ocrLanguage: 'en' });
      try {
        return { text: DocumentApp.openById(tmp.id).getBody().getText() };
      } finally {
        try { Drive.Files.remove(tmp.id); }
        catch (e) { console.warn('OCR temp %s not removed: %s', tmp.id, e); }
      }
    }
    return { text: null, reason: 'unsupported:' + mime };
  } catch (e) {
    console.warn('cannot read %s (%s): %s', file.getName(), mime, e);
    return { text: null, reason: 'error', error: String(e) };
  }
}

function driveAdvancedAvailable_() {
  try { return typeof Drive !== 'undefined' && Boolean(Drive.Files); }
  catch (e) { return false; }
}

// ====================================================================
// LEDGER
// ====================================================================

function readLedger_() {
  try { return JSON.parse(PROPS.getProperty(LEDGER_KEY) || '{}'); }
  catch (e) { console.warn('ledger unreadable, starting fresh: %s', e); return {}; }
}

function writeLedger_(ledger) {
  var json = JSON.stringify(ledger);
  // Script Property values cap near 9KB. Evicting an ok entry only costs a
  // re-capture next sweep, which the node dedups — so eviction is safe, but a
  // permanently oversized ledger means permanent churn. dashboard() reports the
  // byte count so that is visible before it becomes the steady state.
  while (json.length > LEDGER_MAX_BYTES) {
    var evictable = Object.keys(ledger)
      .filter(function (k) { return ledger[k].ok && !ledger[k].permanentSkip; })
      .sort(function (a, b) {
        return String(ledger[a].at || '').localeCompare(String(ledger[b].at || ''));
      });
    if (!evictable.length) break;
    delete ledger[evictable[0]];
    json = JSON.stringify(ledger);
  }
  PROPS.setProperty(LEDGER_KEY, json);
}

function bumpFailure_(ledger, id, name, stats) {
  var entry = ledger[id] || { name: name };
  entry.name = entry.name || name;
  entry.ok = false;
  entry.fails = (entry.fails || 0) + 1;
  entry.at = nowIso_();
  if (entry.fails >= MAX_RETRIES) {
    if (!entry.quarantined) stats.quarantined++;   // count the flip, not the state
    entry.quarantined = true;
    console.error('QUARANTINED after %s failures: %s — fix, then requeue("%s")',
      entry.fails, name, id);
  } else {
    stats.failed++;
  }
  ledger[id] = entry;
}

/** Un-quarantine one file id, or every quarantined+skipped file with requeue(). */
function requeue(fileId) {
  var ledger = readLedger_();
  var n = 0;
  Object.keys(ledger).forEach(function (k) {
    if (fileId && k !== fileId) return;
    delete ledger[k].quarantined;
    delete ledger[k].permanentSkip;
    ledger[k].fails = 0;
    n++;
  });
  writeLedger_(ledger);
  console.log('requeued %s entr%s', n, n === 1 ? 'y' : 'ies');
}

// ====================================================================
// ADMIN
// ====================================================================

/**
 * One-shot helper to write NGS_TOKEN into Script Properties.
 *
 * TRADEOFF — read before using. A token pasted into this literal lives in the
 * script body AND in Apps Script's version history, readable by anyone with
 * edit access to the project. Version history cannot be selectively purged, so
 * a token that lands there is committed until the token itself is rotated.
 * Project Settings -> Script Properties stores the same value without ever
 * putting it in source, which is why SETUP step 1 points there.
 *
 * If you use this anyway: blank the literal immediately after one run. The
 * property persists on its own — the source does not need to keep the value.
 */
function setupToken() {
  var token = 'INSERT_NGS_TOKEN_HERE';

  if (!token || token === 'INSERT_NGS_TOKEN_HERE') {
    throw new Error('setupToken(): replace the placeholder with the node token, or ' +
      'set NGS_TOKEN via Project Settings -> Script Properties (preferred — it ' +
      'keeps the secret out of source and out of version history).');
  }

  PROPS.setProperty('NGS_TOKEN', token);
  console.warn('NGS_TOKEN set (%s chars). Now blank the literal above — the ' +
    'property persists without it, but version history keeps whatever you saved.',
    token.length);

  var pre = preflight_();
  console.log(pre.ok ? 'preflight OK — run testCapture() next.'
                     : 'still blocked: ' + pre.problems.join(' | '));
  return pre.ok;
}

/**
 * Resolve the watch folder by pinned ID, falling back to a one-time name lookup.
 * getFoldersByName() matches every folder this account can reach, including one
 * shared TO it by someone else — and whatever it returns becomes agent-readable
 * memory. So the name branch accepts only a folder this account owns, refuses
 * to guess between duplicates, and pins the ID so it runs at most once.
 */
function getOrCreateFolder_() {
  var pinned = PROPS.getProperty('GEMINI_FOLDER_ID');
  if (pinned) {
    try { return DriveApp.getFolderById(pinned); }
    catch (e) {
      console.warn('GEMINI_FOLDER_ID %s unreadable (%s) — re-resolving by name', pinned, e);
    }
  }

  var name = PROPS.getProperty('GEMINI_FOLDER') || 'Gemini Exports';
  var me = Session.getEffectiveUser().getEmail();
  var owned = [];
  var it = DriveApp.getFoldersByName(name);
  while (it.hasNext()) {
    var f = it.next();
    try {
      var owner = f.getOwner();
      if (owner && owner.getEmail() === me) owned.push(f);
      else console.warn('ignoring folder "%s" not owned by %s', name, me);
    } catch (e) {
      console.warn('skipping folder "%s": owner unreadable (%s)', name, e);
    }
  }

  if (owned.length > 1) {
    throw new Error('Ambiguous watch folder: ' + owned.length + ' folders named "' +
      name + '" are owned by this account. Set GEMINI_FOLDER_ID explicitly.');
  }

  var folder = owned[0] || DriveApp.createFolder(name);
  PROPS.setProperty('GEMINI_FOLDER_ID', folder.getId());
  console.log('watch folder pinned: "%s" -> %s', name, folder.getUrl());
  return folder;
}

/**
 * Config gate. Checked before a sweep and surfaced by dashboard(), so the two
 * failure modes that look identical in a log — "nothing to do" and "cannot
 * reach the node" — are told apart before they are mistaken for each other.
 */
function preflight_() {
  var problems = [];
  if (!PROPS.getProperty('NGS_TOKEN')) {
    problems.push('NGS_TOKEN script property is not set. ' +
      'Project Settings -> Script Properties -> Add property. ' +
      'Value is the node\'s NGS_NODE_TOKEN (HF Space -> Settings -> Secrets).');
  }
  var health = null;
  try { health = ngsHealth(); } catch (e) { /* reported below as unreachable */ }
  if (!health || !health.ok) {
    problems.push('node unreachable at ' +
      (PROPS.getProperty('NGS_URL') || DEFAULT_URL) +
      (health ? ' (HTTP ' + health.code + ')' : '') + '. Check NGS_URL.');
  } else if (health.health && health.health.node_token_configured === false) {
    problems.push('node reports NGS_NODE_TOKEN unset upstream: every write ' +
      'returns 503 (deny-by-default). Fix on the node, not here.');
  }
  return { ok: problems.length === 0, problems: problems };
}

function setupTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'syncGeminiExports') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('syncGeminiExports').timeBased().everyMinutes(15).create();
  getOrCreateFolder_();
  console.log('trigger installed: syncGeminiExports every 15 min');
}

/** Lane health AND node health in one call. */
function dashboard() {
  var ledger = readLedger_();
  var ids = Object.keys(ledger);
  var pick = function (fn) {
    return ids.filter(fn).map(function (k) { return ledger[k].name || k; });
  };

  var node = ngsHealth();
  var pre = preflight_();
  var report = {
    ready: pre.ok,
    blocking: pre.problems,
    lane: {
      ngs_url: PROPS.getProperty('NGS_URL') || (DEFAULT_URL + ' (default)'),
      token_set: Boolean(PROPS.getProperty('NGS_TOKEN')),
      folder_name: PROPS.getProperty('GEMINI_FOLDER') || 'Gemini Exports (default)',
      folder_id: PROPS.getProperty('GEMINI_FOLDER_ID') || '(not yet pinned)',
      subfolders: truthy_(PROPS.getProperty('SCAN_SUBFOLDERS'), false),
      bulk_push: truthy_(PROPS.getProperty('USE_BULK_PUSH'), false),
      drive_advanced_service: driveAdvancedAvailable_()
    },
    ledger: {
      tracked_files: ids.length,
      quarantined: pick(function (k) { return ledger[k].quarantined; }),
      permanently_skipped: pick(function (k) { return ledger[k].permanentSkip; }),
      failing: ids.filter(function (k) {
        return !ledger[k].ok && !ledger[k].quarantined;
      }).map(function (k) {
        return (ledger[k].name || k) + ' (' + ledger[k].fails + 'x)';
      }),
      bytes: (PROPS.getProperty(LEDGER_KEY) || '').length,
      bytes_cap: LEDGER_MAX_BYTES
    },
    node: node.ok ? {
      reachable: true,
      status: node.health.status,
      total_shards: node.health.total_shards,
      persistent_storage: node.health.persistent_storage,
      node_token_configured: node.health.node_token_configured,
      warnings: node.health.warnings
    } : { reachable: false, http_code: node.code }
  };

  console.log(JSON.stringify(report, null, 2));
  return report;
}

/** Readable recall from the editor: searchShards('gateway token'). */
function searchShards(query, limit) {
  var r = ngsSearch(query, limit || 5);
  if (!r.ok) { console.error('search failed: HTTP %s', r.code); return r; }
  console.log('%s result(s) for "%s"', r.results.length, query);
  r.results.forEach(function (s, i) {
    console.log('%s. [%s] %s\n   %s', i + 1, s.event_type, s.title,
      String(s.content || '').slice(0, 200).replace(/\n/g, ' '));
  });
  if (r.federation) console.warn('COVERAGE HOLE: %s', r.federation.title);
  return r;
}

/**
 * Full vault export to Drive via /sync/pull.
 * Writes to a SEPARATE folder: a backup dropped in the watch folder would be
 * swept straight back into the grid on the next run.
 */
function backupVaultToDrive() {
  var r = ngsPull();
  if (!r.ok) { console.error('pull failed: HTTP %s', r.code); return null; }

  var stamp = Utilities.formatDate(new Date(), 'UTC', "yyyy-MM-dd'T'HHmmss'Z'");
  var name = BACKUP_PREFIX + stamp + '.json';
  var folder;
  var it = DriveApp.getFoldersByName(BACKUP_FOLDER);
  folder = it.hasNext() ? it.next() : DriveApp.createFolder(BACKUP_FOLDER);

  var file = folder.createFile(name, JSON.stringify(r.shards), MimeType.PLAIN_TEXT);
  console.log('backed up %s shard(s) -> %s', r.shards.length, file.getUrl());
  return file.getUrl();
}

function testCapture() {
  var health = ngsHealth();
  if (!health.ok) {
    console.log('SMOKE FAILED — node unreachable (HTTP %s). Check NGS_URL.', health.code);
    return false;
  }
  var r = ngsCapture(
    '[GEMINI] apps-script lane smoke test',
    'If you can recall this, the Gemini sharding lane is live. ' + nowIso_(),
    LANE_TAGS.concat(['smoke-test']));

  if (!r.ok) {
    console.log('SMOKE FAILED — capture returned HTTP %s. Run dashboard().', r.code);
    return false;
  }
  // captured:false here is almost certainly dedup from a previous smoke run.
  console.log('SMOKE PASSED — node accepted the shard (captured=%s%s). ' +
    'Confirm with searchShards("apps-script lane smoke test")',
    r.captured, r.captured ? '' : ', i.e. already present — re-run after editing the text');
  return true;
}

// ====================================================================
// UTILS
// ====================================================================

function chunk_(text, size) {
  if (text.length <= size) return [text];
  var out = [], buf = '';
  text.split(/\n\n+/).forEach(function (para) {
    if (buf && (buf.length + 2 + para.length) > size) { out.push(buf); buf = para; }
    else { buf = buf ? buf + '\n\n' + para : para; }
    while (buf.length > size) { out.push(buf.slice(0, size)); buf = buf.slice(size); }
  });
  if (buf) out.push(buf);
  return out;
}

function md5_(text) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, text, Utilities.Charset.UTF_8)
    .map(function (b) { return ((b & 0xff) + 0x100).toString(16).slice(1); })
    .join('');
}

function truthy_(value, fallback) {
  if (value === null || value === undefined || value === '') return Boolean(fallback);
  return ['true', '1', 'yes', 'on'].indexOf(String(value).toLowerCase()) !== -1;
}

function nowIso_() { return new Date().toISOString(); }

function shortName_(file) { return file.getName().slice(0, 60); }
