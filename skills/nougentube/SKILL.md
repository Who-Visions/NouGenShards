---
name: nougentube
description: Use when the operator gives a YouTube URL, video id or pasted transcript and wants it "nougentubed", sharded, morphed, or recalled; when asked what the fleet already knows about a video; or before absorbing any transcript into code. Covers the ingest pipeline (NouGen/tools/nougentube.py, era-stamped, tube:<id> dedupe), the Whisper fallback when captions are off, the recall-before-morph rule that stops three lanes morphing the same video, and the verbatim capture path for pasted text.
---

# NouGenTube

One video, one canonical shard set, many morphs on top. The mistake this skill exists to stop:
on 2026-09-21 three lanes each morphed `tYugqJ9YytQ` within 20 minutes because nobody recalled first.

## 1. Recall before anything

```
shards_search("tube:<id>")            # nougentube's verbatim capture, era-stamped
shards_search("<title words> morph")  # earlier morphs / distillations by any lane
```
If a verbatim shard exists, do not re-ingest. If a morph exists, build on it (cite its id); do not
write a competing summary. If only your angle is new (e.g. "how this maps to NouGenMix"), capture
that as a thin shard that cites the existing ones.

## 2. Ingest (verbatim, era-stamped)

```
cd C:\Users\super\Outpost\NouGen
set NOUGEN_VAULT_DIR=C:\Users\super\.nougen\shards     # never rely on cwd resolution
python tools\nougentube.py <url-or-playlist> [--dry-run] [--limit N]
```
- Captures at the video's TRUE publish date (`original_timestamp`), tagged `tube:<id>`, split at
  ~30k chars with overlap; playlists expand; a failed transcript yields a `no-transcript` stub, an
  unknown date is tagged `era-unknown`. `--dry-run` writes nothing.
- The title in the log is the truth about which video the id points to. If it does not match the
  transcript the operator pasted, the URL is wrong: say so and capture the pasted text verbatim
  (`shards_capture`, event_type INGEST, tags `nougentube, verbatim, era-unknown`).
- "shard written WITHOUT embedding" on the first call is a cold-start miss; check
  `curl localhost:11434/api/embeddings` and let the backfill pick it up.

## 3. Captions off: Whisper fallback

`tools\ai_video_transcriber` (skill `video-transcribe`): platform subtitles first, local Whisper
second. `venv\Scripts\python transcribe.py "<url>" --json --no-llm` gives the raw transcript;
then capture it with the tags above plus `whisper`. yt-dlp on this box can be bot-blocked
("page needs to be reloaded"); if both tiers fail, ask the operator to paste the transcript.

## 4. Morph (nougenmorph / valerion)

Ideas only, never the wording. Land: a theory module with provenance labels and tests where the
content is mechanics (see the `nougenmix` skill), or a `docs/*-valerion.md` where it is
framing; one shard citing the `tube:<id>` shard; a relay leg if other lanes need it.

## 5. Shard hygiene

- Title the shard by what a future lane will search for, not by the video's title.
- Keep claims labelled: "the video claims" vs "verified by the fleet".
- If the operator pasted a transcript, the id they gave may be wrong; never trust a URL over
  the text in hand.
