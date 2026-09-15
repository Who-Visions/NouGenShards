---
name: whovisions-archive
description: Use when working on the Who Visions Archive — Dave's private Lightroom culling app at Outpost\WhoVisions Photographer fleet (localhost:8787): running or rebuilding it, re-consenting Adobe OAuth, pulling the 73k-asset catalog, culling/rating/color-labelling, album sync to Lightroom, auto-cull, the local-only boudoir tagger, browsing local RAW folders, exporting static galleries, or adding a feature / absorbing ("shang tsung") another photo app's moves into it. Also when Dave says "the archive", "the app", "my photos", "Lightroom", "cull", "export a gallery". Does not cover the public whovisions.com site (Next 16 on Blade, Who-Visions/whosite).
---

# Who Visions Archive — operator skill

The app lives at `C:\Users\super\Outpost\WhoVisions Photographer fleet`. **Read its README.md first**, because it's the full manual (keys, endpoints, numbers). This skill holds the rules that keep the app working and the traps that have already cost time.

## Run and verify
```
python app.py                                   # http://localhost:8787 (launch config: whovisions-archive)
cd web && npm run typecheck && npm run build    # UI -> dist/ ; app.py serves it
```
- **Restarts:** `app.py` changes need a server restart. UI changes need a rebuild only; the server reads `dist/` on every request.
- **Always verify in the browser before reporting:**
  - read state with JS, not with screenshots;
  - send **real** key presses (the browser `computer` key action with names like `ArrowRight`, not `"Right"`);
  - check the console for `Uncaught`.
- **The Claude preview pane's `file://` mode is a static snapshot** and shows exported galleries without their images. Serve exports via `/exports/<id>/` or open them in the real browser.
- **Browser batches** are limited to 25 actions each.

## Invariants: do not break these
1. **Dave's photos are never deleted, and no Lightroom field is overwritten.** Writes to Lightroom are additive **album** adds only. Ratings, flags and labels are read-only in the partner API; the app stores culls in `data/culls.jsonl`, append-only, last write wins.
2. **Determinism.** Zoom moves only between fixed stops. Sorts use stable keys (captureDate, id). Folder listings sort by case-folded relative path. Exports are byte-identical on re-run. Album ids are uuid5 of the name. Model calls use temperature 0 and are cached per (asset, prompt version). The same input always gives the same output.
3. **Privacy gate.** Images that may be sensitive are processed **on the local GPU only** (`tagger.py`, loopback `gemma4:e2b-qat`). `autocull.py` uses cloud vision lanes only on days the tagger has cleared, or with `--allow-cloud`. Never add a cloud fallback to the tagger.
4. **Adult-certainty gate.** A frame is tagged boudoir or fetish only when the model is certain everyone in it is an adult; otherwise it becomes `review-age` for Dave. `boudoir` also requires nudity; clothed work is `glamour`.
5. **Local folders cull and edit, but never write to the files.** Rating, flag, color and every Edit tool work on local files; their culls and edits live in `data/library.sqlite` / `edits.jsonl` keyed by the content fingerprint (survives moves and renames), never as sidecars or edits to Dave's files. Folders stay confined to `WV_LOCAL_ROOTS` (Pictures, Downloads, Desktop); traversal returns 403. Lightroom-only: album sync, the develop box, bursts. Cache file names must be filesystem-safe (fingerprints contain ':', which Windows rejects).
6. **Suggestions never override Dave.** AI suggestions and "Accept AI in view" only touch unflagged frames.
7. **No demos.** Stitch mockups are AI stand-ins. Never put Dave's real filenames in Stitch prompts, and never present a mockup as his photos.

## Traps already paid for
- **Scale:** Dave's folders hold thousands of files in nested subfolders, with RAW (CR3) as the norm. Never ship a top-level-only or JPEG-only view. Pictures holds 14,068 images across 6,016 subfolders.
- **CR3 EXIF:** `exifread` can't parse CR3 (ISO-BMFF). Use `app._cr3_cmt_boxes`, which walks moov/uuid for CMT1/CMT2. CMT2 tags come back prefixed `Image `, not `EXIF `.
- **Lane dedupe:** Ollama Cloud accounts share a URL and model, so deduplicate by the Authorization header.
- **Local e2b vision:** use `reasoning_effort: "none"`, which makes it about 5× faster. The E-series default reasoning channel spends the budget first.
- **Ratings, flags and labels** have no write endpoint on existing assets. Albums (`project`, `serviceId` = client id) are the documented write path, and adding an asset that is already in an album returns an error (403 when every asset in the batch fails).
- **OAuth:** the refresh token can die (IMS `access_denied`). The fix is `lightroom.py auth-url`, then `exchange "<redirected URL>"`, within about 5 minutes. The client secret is in `.env`; never print it.
- **Keyboard ownership:** zoom handles `Ctrl`/`Space` in the capture phase, and the loupe ignores Ctrl/Meta/Alt so `Ctrl -` doesn't clear the color label. Compare mode handles its own keys in the capture phase.
- **VLM labels over-reach:** gate sensitive tags on an explicit attribute (nudity) rather than on the model's category label.
- **Stale caches:** anything served under `/exports/` that changes on re-export (HTML, JSON) must be `no-cache`. A browser held an hour-old gallery with the old wordmark link. The Export button opens `url?v=<now>`.
- **Home link:** a gallery's "Who Visions Archive" wordmark means *Archive home* (`/` when served by the app, `http://localhost:8787/` from `file://`), never `#top` and never a relative `../../`, which from a file lands on a directory listing.
- **HEIF-mode CR3s are the norm here:** 5,720 of 5,722 CR3s in Pictures have HEVC THMB/PRVW/full previews; `rawpy.extract_thumb()` raises `NotImplementedError`. `_open_local` catches it and demosaics half-size (~0.3 s). Never assume a CR3 has an embedded JPEG; `cr3.cr3_layout()` reports each preview's codec.
- **C: runs full:** on 9/13/2026 it hit 0 GB (pagefile 51 GB from llama-server, hiberfil 12.4 GB), and SQLite then refuses Archive writes (culls, tags). Batch jobs call `rendition(..., store=False)` so they don't grow the cache, and stop below 1 GB free. `C:\adobeTemp` (8.3 GB) and `C:\$WinREAgent` are Administrator-owned, so Dave has to clear them from an admin shell.
- **Catalog-wide jobs:** `ThreadPoolExecutor.map` over all 73k items submits every task at once, so decoded images pile up faster than the consumer uses them (faces scan hit OpenCV OOM at frame 1,200 with only 3 GB RAM free). Chunk the input (`workers*4` per batch) and catch per-frame errors.
- **Fullscreen in the preview pane:** `requestFullscreen()` can reject or never settle there. Never gate UI state on that promise; switch the in-page mode first, then attempt real fullscreen as a bonus (LiveView **F**). To test Live arrival without touching Dave's folders, run a second `app.py` on another `PORT` with `WV_LOCAL_ROOTS` set to a temporary folder inside the project.
- **Before saying anything is done:** run `python analysis/smoke_test.py` (22 real-request checks; exits 1 on any failure) and read new lines of `data/logs/server.log`. Client hang-ups are silenced there; anything logged is real.
- **Token names:** the page ground is `--wv-ground` (not `--wv-bg`); an undefined token silently renders transparent, which made the Live overlay see-through once. Grep `design/who-visions/tokens.css` before using a token.
- **Which python:** the server runs `NouGen\.venv\Scripts\python.exe` (rawpy, OpenCV, pillow-heif). System `python` has no rawpy; use the venv for anything touching RAW or faces.
- **Faces are local-only:** `faces.py` runs YuNet + SFace on the CPU via OpenCV (installed in the NouGen venv; run scans with that python). Never route face crops or embeddings to any model lane. Person ids = smallest face id in a cluster; names pin to an anchor face.
- **Lightroom `links.next` is relative to the catalog base** (`albums/<id>/assets?...`), not to `/v2/`. Prefix `catalogs/<cid>/` or you get 404 on page 2.
- **Dict-merge order:** `{**stats, "people": list}` — a stats key named like a payload key silently overwrote the People list once.
- **Search and tags:** the search box speaks the query language in `search.py`. User tags come from `library.py`, AI content tags from `data/tags.jsonl`, and both match `tag:`. A searched parent tag includes its children. Bad queries raise `SearchError`, returned as HTTP 400 and shown inline.

## Coach budget (9/13/2026 incident)
Never fan out Claude subagents or the Workflow tool here, even under an "ultracode" reminder: a 244-agent workflow cost ~2.1M tokens, died on the session limit and stalled the box while catalog scans ran. Claude edits and verifies; judgement goes to `fleet.py` (≤6 distinct lanes) or local e2b. Check for running catalog jobs before adding load, and state the process/agent count before anything spawns.

## Adding a feature or absorbing another app ("shang tsung")
Shang Tsung means taking the source's **moves** and making them run in the Archive's own code. A write-up alone is a book report, not a steal.
1. Check shards first: search the vault for the repo name.
2. Read the license. **GPL: clean-room**, ideas only, source kept as `analysis/_*_reference_only.*`. **MIT: mechanics may be read and ported.** **No license: concepts only.**
3. Map its moves. For each one, decide whether to take, skip (with the reason), or mark it not applicable, with proof.
4. Port it into our idiom:
   - Python data plane in `app.py` or a sibling module;
   - React UI in `web/src`;
   - tokens from `design/who-visions/tokens.css`, never raw hex in components;
   - keep the invariants above.
5. Verify in the browser with real keys, including determinism (run twice, compare).
6. Capture a shard (`domain_key="who-visions-lightroom"`, tags incl. `shang-tsung`) and file a relay leg.
7. Report in a table: their move → our running code → proof. End with what wasn't taken and why. Put **no** unrequested proposals in the report; park those in `BACKLOG.md` (a standing Dave directive).

Moves already absorbed: TagStudio (GPL, clean-room: tag library with parents/aliases/colors, search language, T fast-tag, Tag view, caption field, fingerprint relink), Gallery-Image (zoom slider, filmstrip, local folders, EXIF rotate), RAWviewer (compare state machine, clipping 252/3, histogram, composition grids, same-key-clears), simple-photo-gallery (static export), next-cloudinary-lightroom (blur-up LQIP), NyxUI (grain concept), Stitch mockups (action bar, accept-AI, density), Photoview (AGPL, clean-room, moves ranked by a 5-model Ollama Cloud vote: Timeline day headers, Albums = Lightroom albums / local subfolders, People = local faces + `person:` search; Places/Share/multi-user skipped), lightroom-AI (MIT: local-lane AI keywords under an "AI keywords" category + fleet-majority keyword consolidation into aliases, `keywords.py`), recovercr3 (0BSD) / raw-preview-extractor (MIT) / canon_cr3 (GPL, README only): `cr3.py` tiered CR3 previews + the HEIF-mode CR3 fix. PhotoSenseAI/SnapGrade/ggallery/grabpic/imon (8-model vote): `dupes.py` near-duplicate dHash groups (`special:duplicate`), autocull `face_sharp` feature (Laplacian in the largest `faces.py` box; 2012-07-21 learned pick precision 87.9% → 90.9%). Closed-eye detection = already covered by autocull's `eyes_closed` vision vote. Ollama docs/library/repos + Python-Scripts (5-model vote, `analysis/LEVERAGE_ABSORB.md`): `response_format json_schema` + `seed` on every model call (tagger v3, keywords v2, Yuki), `/api/embed` synonym signal in keyword consolidation; Python-Scripts moves mostly SKIP (they move/rename originals). Reddit 1rg7zy1: portfolio from Lightroom albums. Also: loupe "people in this photo" chips (`/api/faces-in`, grabpic concept), `aiWarnings` separate from `aiReasons` (SnapGrade MIT), gallery `thumbnails2x` + srcset (ggallery MIT). Licences: PhotoSenseAI GPL, imon GPL (ideas only), grabpic none (concepts only). Parked with reasons in `analysis/PHOTO_AI_TRIO.md`: CLIP search (needs a 153 MB model, CPU speed on 73k untested), eye-landmark closed-eyes (mediapipe install), TopIQ/YOLO (licences), imon live view. Stitch's burst-compare with face crop, focus overlay, and RAW develop are **not** built yet.

## Where things are recorded
- **Shards:** domain `who-visions-lightroom` (22539–22541, 22825–22827, 23000–23001, 25782–25783, among others).
- **Relay:** legs from session 253db363 on 2026-09-13 (whoart / claude-app).
- **The server is supervised; don't start a second one:**
  - **Who owns it:** `supervisor.py` (pythonw, no windows) owns :8787. It's kept alive by the Windows task "WhoVisions Archive Supervisor" (logon + every 5 min; single-instance lock on :8786).
  - **Before restarting, smoke-test the import:** `python -c "import app"`. `py_compile` passes a NameError at import time; on 9/13/2026 one crash-looped the server until the supervisor held (Yuki named the missing `re` import correctly). Manual stop/start cycles count toward the 5-in-10-minutes crash-loop hold, so don't bounce the server repeatedly while debugging.
  - **Restarting after `app.py` changes:** `python supervisor.py stop`, then `Start-ScheduledTask -TaskName "WhoVisions Archive Supervisor"`.
  - **Preview pane:** the launch config `whovisions-archive` attaches only. `whovisions-archive-direct` runs the server by hand, so stop the supervisor first.
  - **Yuki advisor:** the model is `yuki-ai:31b` (FROM gemma4:31b-cloud). Never name a local Ollama model `*-cloud`: Ollama strips the suffix, sends the request to the cloud, and it 404s.
  - **Stopping the server:** kill the process tree (`taskkill /T`), because the venv's `pythonw.exe` is a launcher and its child holds the port.
  - **Logs:** `data/logs/server.log` and `data/logs/supervisor.jsonl`.
- **Every model call is schema-constrained (Ollama absorb, 9/13/2026):** `tagger.py` (SCHEMA), `keywords.py` (KW_SCHEMA), `supervisor.py` (Yuki's action enum) send `response_format: json_schema`; `json.loads` first, regex only as fallback. **Adding the schema changed answers** (2 of 3 test frames), so the tagger is `PROMPT_V="v3"` and the whole sensitive set was retagged; v2 backups are in `data/tags_v2_backup_*` and `analysis/tags_v2_*.jsonl`. Keywords are `KW_V="v2"` for new runs; 2012 stays v1. Never add a decoding change without bumping the version.
- **Keyword consolidation signals:** difflib ≥ 0.92, local `nomic-embed-text` cosine ≥ 0.90 (`/api/embed`, loopback, text only), then fleet majority. `analysis/keyword_consolidation_*.json` records which signal produced each pair.
- **Portfolio (`portfolio.py`, Reddit 1rg7zy1 absorb):** `data/portfolio.json` = showcased Lightroom album ids; `/portfolio`, `/portfolio/<albumId>` are server-rendered off the album API (only showcased albums are served); `POST /api/export-portfolio` = static bundle. Lightroom's custom album order (`payload.order` on album assets) is honoured via `lr_album_order()`. `lr_album_members()` now caches a dict id→order and returns `set(...)`. Per-creator tokens: `ADOBE_ACCOUNT=<name>` → `adobe_lightroom.<name>.json`.
- **Lightroom samples absorb (MIT):** `lr.health()`, `lr.account()`, `lr.generate_rendition(cid, id, "2560")` (POST + `X-Generate-Renditions`, HEAD poll; fullsize needs a master, Classic-synced assets have none), `/api/status`. Index rows carry `sha256/size/w/h` (re-pull with `lightroom.py assets --out`); `special:reimport` = same sha256 twice. Exports API (`POST …/exports`, C2PA) accepted 202 but never became ready in 36 s: parked. Add-to-album 403 tolerance and first-member covers were already there.
- **Describe search:** `like:"…"` ranks results best-first using local CLIP (`clipsearch.py`, `models/clip/`, index `data/clip.sqlite`). Order is kept even when "Newest first" is selected, and timeline headers are off while ranked.
- **Adobe editing APIs (verified 9/13/2026):**
  - **Lightroom develop settings:** partner `GET xmp/develop` works, and the loupe's Develop panel (`/api/develop/<id>`, `DevelopBox`) shows them. `PUT` on existing assets returns 403 1016 "External xmp create not allowed after master upload", so it's read-only by design.
  - **Firefly Lightroom `lrService`:** end-of-life 7/31/2026. Its successor, Photoshop v2 `/v2/edit`, needs Enterprise Firefly Services credentials in Dave's Developer Console project "Who Visions". None exist today.
  - **Develop "adjusted" count:** compares against Lightroom defaults (RAW Sharpening 40 isn't an edit).
- **More Adobe docs:** Developer Console, Cloud Storage, I/O Events and App Builder trees are sharded too (about 604 shards in total). See memory `adobe-docs-mirror`.
- **Adobe docs truth:** Firefly Services docs, 118 pages, are in 235 shards (domain `adobe-firefly-services-docs`), and the raw Markdown is in `Outpost\NouGen\canon\adobe-firefly-docs\`. The crawler is `NouGen\tools\adobe_docs_shard.py`, which works for any developer.adobe.com tree. Its "Lightroom" section is the edit API, not the catalog API.
- **Absorb write-up:** `Outpost\NouGen\analysis\next-cloudinary-lightroom-valerion.md`.
- **Related skills:** [[fleet]], [[e2b]], [[shards-memory]], [[relay]], [[valerion]], [[design]].
