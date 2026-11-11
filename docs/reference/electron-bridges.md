# Electron bridges: NouGen apps to Electron APIs

Each row links a NouGen integration to the Electron docs page it follows. The docs are sharded into the vault
under domain `electron-docs` (303 pages, `tools/shard_electron_docs.py`, source `canon/electron-docs`, from
electron/electron `docs/`). Recall with `nougen recall "<api>"`. To refresh: sparse-clone electron/electron `docs/` and re-run the tool;
capture dedupes unchanged pages by content hash.

Grep counts in the docs (deep grep, 2026-11-11): contextBridge 44 files, shell.openExternal 22, autoUpdater 11,
nativeImage 13, MessageChannelMain 6, ipcRenderer.postMessage 5, setWindowOpenHandler 5, setZoomLevel 5,
will-attach-webview 3, workAreaSize 4, powerSaveBlocker 2.

## NouGenNews (`Who-Visions/NouGenNews`)

| Integration | Electron doc | Where | PR / state |
|---|---|---|---|
| Preload exposes a narrow API, never raw ipcRenderer | `api/context-bridge.md` | `electron/preload.js` | in feat/core |
| Read-aloud WAV over a MessagePort, not base64 invoke | `tutorial/message-ports.md`, `api/message-channel-main.md` | `electron/ttsport.js`, `electron/preload.js` (`ttsSynth`, `openTtsPort`) | #15 merged |
| Sender check on the port (app's own top-level frame only) | `tutorial/message-ports.md` | `electron/ttsport.js` `isAppFrame` | #15 merged |
| Guest page in the sidebar: attach checks, popups denied, navigation limited to http(s) | `api/webview-tag.md`, `api/window-open.md` | `electron/main.js` `will-attach-webview`, `will-navigate` | #17 merged |
| Denied window.open, links open in place | `api/window-open.md` | `electron/main.js` `setWindowOpenHandler` | in feat/core |
| Keyboard zoom | `api/web-frame.md` (WebContents zoom level) | `electron/zoom.js` | #19 merged; saved zoom in #36 |
| Window fits the work area; minimum size | `api/screen.md` (workAreaSize, DIP), `api/browser-window.md` (minWidth/minHeight) | `electron/window-size.js`, `electron/main.js` | #22, #28 merged |
| Tablet: one pane below 900px, 44px touch targets | (CSS: `api/corner-smoothing-css.md` not used; responsive CSS) | `renderer/components/NewsView.css`, `MenuBar.css` | #29 merged; menu bar wrap in #36 |
| Keep the system awake during read-aloud | `api/power-save-blocker.md` (`prevent-app-suspension` for audio) | `electron/keepawake.js`, `renderer/lib/speech.js` | #26, #32 merged |
| Auto-update, off unless packaged with a feed | `api/auto-updater.md` | `electron/updater.js` | merged via #21 (electron-updater + NSIS); #16 closed as superseded |
| External links: fixed allowlist or https-only | `api/shell.md` (openExternal) | `electron/handlers.js` | audit clean (leg 084432) |
| App icon | `api/native-image.md` (ICO 16-256, @2x PNG) | packaging (other lane, PR 33) | open |

## Not used (checked against the docs)

- `api/system-preferences.md`: the app is fixed dark; accent colour is cosmetic (skipped, leg 084523 handled by another lane).
- `api/image-view.md`: a splash only matters with a BaseWindow refactor; not done.
- `api/touch-bar.md`: macOS-only hardware; no tablet use.

## Open gaps

- Tablet layout and the menu bar wrap were checked in a browser on a stubbed renderer copy, not in a built app.
- The vault holds more than one copy of the Electron docs: several lanes sharded them the same day under
  different titles (`electron/electron: docs/...`, `Electron docs: ...`, and this tool's plain page titles).
  Recall returns all copies. This is accepted: the same docs were sent to every lane on purpose.
