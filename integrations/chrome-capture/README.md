# NouGen Capture (Chrome extension)

Send a selection or page to the shard vault via the node's `POST /capture`.

Install: `chrome://extensions` -> Developer mode -> Load unpacked -> this folder.
Configure: open the extension's options, enter the node endpoint and token. The token
is kept in `chrome.storage.local` only; it is never in the source or manifest. Saving
requests host access for that one origin.

Use: right-click a selection or page -> Capture to shards, or `Alt+Shift+S`.
The notification reports `captured` from the response, not the HTTP status.

Test: `node --test integrations/chrome-capture/tests/capture.test.mjs`
