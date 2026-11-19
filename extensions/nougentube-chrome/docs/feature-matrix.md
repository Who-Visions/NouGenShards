# NouGenTube vs Glasp and NoteGPT

Compiled 2026-11-11 from each product's own public pages (Glasp: YouTube Summary, pricing, reader; NoteGPT: YouTube summarizer, transcript, AI notes, mind map, pricing). Summarised in our own words; raw page text is not kept in the repo.

Legend: **yes** = shipped, **partial** = shipped with a stated limit, **no** = not built, **n/a** = out of scope for a YouTube side panel.

| Capability | Glasp | NoteGPT | NouGenTube | Notes |
|---|---|---|---|---|
| Summary beside the player | yes | yes (web app and extension) | yes | Own side panel inside the watch page |
| Choice of AI model | ChatGPT, Claude, Gemini, Mistral | built-in models | **yes, wider** | Local Ollama, NouGenOpen free fleet, NVIDIA, Claude, OpenAI, Gemini, DeepSeek, OpenRouter, any OpenAI-compatible endpoint; Auto falls through them |
| Custom prompt, length | yes | limited | yes | Nine styles plus a custom prompt and three lengths |
| Output language | yes | 60+ languages | yes | Fifteen languages plus Auto |
| Click a point to jump the video | yes | yes | yes | Every timestamp seeks |
| Full transcript, copy with timestamps | yes | yes | yes | Exact `Title - YouTube / URL / Transcript: (mm:ss)` format |
| Transcript in another language | yes | yes (subtitle translation) | **yes (new)** | Translated in batches by your model, shown in place, saved per video, used by copy and export |
| Highlights with notes | yes | partial | yes | Star lines; highlights are exported |
| Export | MD, HTML, CSV, JSON; Notion, Obsidian, Roam, mem.ai sync | TXT, copy without timestamps | **yes (new)** | MD, TXT, SRT, TXT without timestamps, Obsidian note, HTML, CSV, JSON. No Notion or Roam sync; Shard to NouGenShards is the native store |
| Chat about the video | yes | yes | yes | Answers cite timestamps |
| Chat across everything you saved | yes ("chat with your highlights") | no | **yes (new)** | My library: answers from saved reports in the vault, each with a verified shard citation |
| Mind map | no | yes (editable, PNG) | partial | Interactive map in the panel; no PNG export or editing |
| Videos with no captions | n/a | yes (AI transcription, up to 150 min) | **yes (new)** | Local faster-whisper through the bridge, up to 150 minutes, $0; marked "from audio"; refuses when the disk is nearly full |
| Batch or playlist summaries | no | yes (up to 20 videos) | **yes (new)** | Batch tab: up to 20 links or a playlist, one summary each, long videos read in parts, optional save of each to the vault |
| Articles, PDFs, audio, files | yes (articles, PDFs) | yes (files, audio, PDF, images) | n/a | Out of scope for a YouTube panel |
| Mobile apps | yes | yes | n/a | Chrome extension only |
| Public highlights (crowd layer) | yes | no | n/a | Different model: private vault |
| Sign-in, cloud storage | yes | yes | n/a for now | Per-tenant vault is deferred by the operator |

## Where NouGenTube goes further (neither competitor has these)

- **Morph:** turns a video into a plan for code, an app, a site or a skill, built on the user's own vault, the live web and the 21 Valerion steps, with every citation verified in code.
- **Intelligence report with a deterministic checker:** quotes must appear verbatim in the transcript, timestamps must be inside the video, and a missing or cut-off section is flagged.
- **Shard:** one button saves the report and the full transcript to the user's own NouGenShards vault, so later videos and agents recall it.
- **Failsafe routes:** a transcript ladder of four tiers and a model ladder that moves on when a route fails or stays silent.
- **$0 by default:** local and free-fleet routes first; keys are the user's own and stay on the device or the local bridge.

## Gaps still open, in order of value

1. Mind map PNG export and editing.
2. Speech-to-text quality: the default `base` model is fast but mishears; `small` is better and slower.
3. A smarter wait when YouTube rate-limits: the batch reports the block and lets the user press Continue; it does not schedule its own retry.
