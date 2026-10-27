---
name: tmdb
description: Use for any TMDB or OMDb movie/TV lookup — titles, IDs, air dates, posters — and when a TMDB call returns 401. Covers the keymaker names, Bearer-vs-v3 key trap, and tools/tmdb.py.
---

# TMDB / OMDb

- Keymaker names: `TMDB_READ_ACCESS_TOKEN` (v4 JWT, send as `Authorization: Bearer`), `TMDB_API_KEY` (v3 32-hex, `?api_key=` only), `OMDB_API_KEY`. Check the keymaker before asking anyone.
- Trap 1: a v3 key sent as a Bearer token gets HTTP 401. Only a JWT-shaped value is a Bearer token.
- Trap 2: an HTTP helper that ignores its init argument drops the header and also 401s. DriveNetflix `electron/network.js` did this until 2026-10-27.
- Trap 3: Windows Python prints CRLF, so split keymaker output on `\r?\n`.
- OMDb keys work only after the emailed activation link is opened (`Invalid API key!` until then).
- CLI: `python tools/tmdb.py check | search "<title>" [movie|tv] | find <imdb_id>`.
- Docs (developer.themoviedb.org) return 403 to plain fetches; use the in-app Browser pane.
