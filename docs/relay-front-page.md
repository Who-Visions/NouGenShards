# Relay front page

The public page served at `GET /` (and `HEAD /`) by `relay-go`. Source: `relay-go/web/index.html`, embedded by `relay-go/web.go`.

## What it is

Static and public. It names no node, count, liveness or version, so it leaks nothing that `/_relay/status` withholds without the node's token. It states only facts the code backs, and `web_test.go` checks the numbers against `defaultMaxBody`, `defaultTimeout` and `Config.IdleTimeout`.

## Design

- **Brand:** NouGen Shards, "Obsidian Violet" (`NouGen/skills/design/brands/nougen-shards`). Dark-first, violet on obsidian, glow instead of shadow. The tokens in the page are that package's, unchanged; nothing was invented.
- **Both themes:** the bare `:root` is the dark palette; `prefers-color-scheme: light` only redefines tokens.
- **Contrast, measured:** dark: ink/night 16.3, muted/night 8.05, brand/night 5.09, white on fill 7.1. Light: ink 16.4, muted 6.7, brand/page 6.5, pass 5.5, fail 5.8. Every pair is at least 4.5:1.
- **Focus:** a double ring on every interactive element, through a zero-specificity `:where()` selector.
- **Motion:** none, so there is nothing to gate.
- **Layout source:** a Google Stitch screen generated from the same tokens. Its structure and spacing were kept. Its copy was not: it added claims the relay does not back ("network ingress: nominal", a version badge, an RFC number, a latency figure, "ed25519-sha256", "zero persistence"), and none of them are on the page.
- **Figma:** the design file is empty. The Figma MCP call limit on the Starter plan was reached on the first edit. The page does not depend on it.

## Security posture

One inline `<style>` block, pinned by hash in the CSP, and nothing else is allowed: `default-src 'self'; script-src 'none'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'; style-src 'sha256-…'`. Plus `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: no-referrer`. The page has no script, no webfonts, no inline style attributes and no remote loads; `web_test.go` fails if any appear.

## Routing

`ServeHTTP` gets one case, inside the existing "not a node route" branch: exactly `GET /` or `HEAD /`. Node routes (`/n/<id>/...`, `<id><host-suffix>`) and `/_relay/*` are unchanged. `/index.html`, `/x` and any other method on `/` stay 404.

One existing assertion changed on purpose: `TestRoutingMisses` listed `/` as a miss. It no longer is, so that row was removed with a comment.

## Visibility

Until the hostname cutover (spec section 6, stage 4), `relay.nougenai.com` belongs to the Cloudflare Worker relay, so this page is only visible on the canary host. A page on the live Worker is a change to `workers/relay/worker.js` and the go-live path, which is a separate PR.

## Notes for reviewers

- The page links to `docs/relay-go-spec.md` and `relay-go/` on `main`. Those exist there only after #1150 merges, so merge #1150 before the page is shown anywhere.
- `cache-control: public, max-age=300`: a proxy in front can serve the previous page for up to five minutes after a redeploy.
- The numbers on the page (8 MiB, 30 s, 20 s, 90 s) are the defaults and are labelled that way; operators can change the body cap and timeout with flags.
- Line endings are normalised to LF before hashing and serving, so the CSP hash holds on a CRLF checkout.
