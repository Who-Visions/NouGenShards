# Third-party notices

Code in this repository that originates elsewhere, with its licence and what
was taken. Adding to this file is part of taking someone's code — an
unattributed port is a licence problem and, just as importantly, it hides where
to look when upstream fixes a bug we inherited.

---

## claude-watch

- **Upstream:** https://github.com/devinilabs/claude-watch
- **Licence:** MIT — Copyright (c) 2026 claude-watch contributors
- **Taken:** `parse_vtt` and `dedupe_cues` from `scripts/transcribe.py`,
  ported into `src/nougen_shards/transcript.py`
- **Adopted:** 2026-09-08

### What it is and why it is here

WebVTT parsing plus a four-pattern dedupe for *rolling* captions. YouTube's
auto-captions repeat most of the previous cue and add a few words, so a naive
parse stores the same sentence several times. Measured on a 15.3-minute video:

    cues parsed          826  ->  207 after dedupe
    naive characters  47,216  ->  15,755
    duplication removed              66.6%

Two thirds of every naively captured transcript was duplicate text — vault
bloat, and recall dilution, since a phrase repeated by the caption track
outranks a phrase actually said once.

The port reproduces upstream's output exactly on the same input (826 -> 207,
15,755 characters, 66.6%), which is how the port was checked rather than
assumed.

### What was deliberately NOT taken

Only the two functions. The upstream project is a full video-to-notes pipeline
(`yt-dlp` + `ffmpeg` scene detection + Whisper fallback + Claude synthesis);
none of that is vendored here. Fetching a VTT stays the caller's problem, so
this module has no network dependency and stays testable offline.

Worth recording for anyone adopting upstream directly: **a captions-only path
needs neither `ffmpeg` nor any paid transcription API.** That fast path is not
advertised, and it is the one most nodes want — a machine with no `ffmpeg`
installed can still capture full transcripts at zero API cost.

### Structure kept on purpose

The ported functions keep upstream's branch order and their
`_ROLLING_OVERLAP_MIN = 10` constant, so an upstream fix stays easy to follow
and apply. The branch order is load-bearing: the rolling-extension check must
precede the contained-tail check, or new words are silently truncated instead
of kept. `tests/test_transcript.py` pins that.
