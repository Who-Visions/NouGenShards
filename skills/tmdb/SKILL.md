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

## Library compiler (NouGenFlix, 2026-10-27)

- `node tools/compile-library.cjs <root> --out <dir> --apply --assets [--exclude a,b]` in `Outpost/DriveNetflix`. Hard-links (never copies/moves) every video into `Movies/`, `Anime Movies/`, `TV Shows/`, `Anime/` as `Title (Year)` and `Show/Season XX/Show - SxxEyy`; writes `library.json`, per-title `.assets/` (6 posters, 6 backdrops, 2 logos, OMDb poster, trailer/BTS links), and the sidecars the app reads with no lookup: `poster.jpg`, `backdrop.jpg`, `movie.nfo`/`tvshow.nfo`.
- Lookups: TMDB `search` then `/{kind}/{id}?append_to_response=images,videos&include_image_language=en,null`, 6 at a time, cached in `.cache.json` (misses cached too; fleet answers cached so reruns are stable). Movie matches are rejected when the year is more than 1 off the file name's year.
- Unmatched names go to the free fleet via `tools/resolve_titles.py` (NouGenOpen `FleetWorker.map`, batches of 8, `max_tokens=2048`), then `tools/library-overrides.json` (key `<kind>|<cleaned title lower>`) for anything still wrong.
- Shelf-aware TV grouping: series folder decides show; season from nearest `Sxx`/`Season N` folder; episode from the number in the name; absolute numbering (001-220) is folded into seasons using TMDB `seasons[].episode_count`, only for files past the season's count and never onto a held slot; Extras/Featurettes -> Season 00. Anime = Anime shelf or TMDB Japanese-language Animation.
- Verify with `node tools/audit-library.cjs <root> <dir>`: every source placed or skipped (samples), every placed file same dev:ino as source, numbering gaps, art on disk -> `AUDIT.txt`. The app's scan (`electron/library.js`, `roots.js`) dedupes by dev:ino and prefers the compiled copy, so scanning `E:\` shows each title once with clean names.
- Trap: Python heredoc patches that write `\b`/`\n` into JS regexes land as raw bytes 0x08/0x0A; verify with `bytes.count(b"\x08")` and `node --check` after every patch.
