# NouGen: Capture, Tube, Morph (Chrome extension)

Send a selection or page to the shard vault via the node's `POST /capture`.

Install: `chrome://extensions` -> Developer mode -> Load unpacked -> this folder.
Configure: open the extension's options, enter the node endpoint and token. The token
is kept in `chrome.storage.local` only; it is never in the source or manifest. Saving
requests host access for that one origin.

Use: right-click a selection or page -> Capture to shards, or `Alt+Shift+S`.
The notification reports `captured` from the response, not the HTTP status.


Design: UI is styled from the NouGenDesign `nougen-core` tokens (`nougen-tokens.css` is a
verbatim copy of `designs/nougen-core/tokens.css`; refresh it by copying, do not edit it).

## v0.2: Tube and Morph

- **Tube**: on a YouTube page, "Send video to NouGenTube" calls the node's `nougentube_ingest`
  MCP tool (plain HTTP `POST /mcp/`, stateless; no handshake needed). The notification reports
  the node's own `counts`.
- **Morph**: distils the page's prose into extractive shards (original sentences only, in page
  order, 3 per shard, up to 12 sentences; no model, nothing invented) and captures each via
  `/capture`. If you type a destiny goal in the popup, it also creates a dormant destiny
  (`create_destiny`, trigger `url:<page>`) and links every captured shard as evidence
  (`link_destiny`). No goal typed means no destiny; the extension never invents intent.
- Needs the node fix in NouGenShards#739: `create_destiny` / `update_destiny` raised
  `TypeError` on every call before it. Until a node is restarted from that fix, Morph still
  saves shards and reports `destiny FAILED (...)` honestly.
- Icons ship in-repo (`.gitignore` excludes `*.png` otherwise); `tests/package.test.mjs` fails
  if any file the manifest or code names is missing.

Test: `node --test integrations/chrome-capture/tests/*.test.mjs`
