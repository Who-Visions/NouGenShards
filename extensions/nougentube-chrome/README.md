# NouGenTube (Chrome, MV3)

A side panel next to the YouTube player with Transcript, Summary, Chat and Highlights. It works like the Glasp and NoteGPT summarizers, but the AI runs on your own Ollama for $0, with NVIDIA build's free tier as an option.

## Install
1. Open `chrome://extensions` and turn on Developer mode.
2. Click **Load unpacked** and choose this folder.
3. Open any YouTube video. The panel appears to the right of the player.

## Features
- **Transcript.** It reads YouTube's own transcript panel. YouTube's direct caption endpoints now require a token, and this path avoids that. You get readable paragraphs of about 20 seconds each, a highlight on the line being spoken with auto-follow, search with match highlighting, and click-to-seek. The two API tiers remain as fallbacks.
- **Summary.** Styles: Key points, Deep dive, Chapters, Mind map (a collapsible tree), Step-by-step, TL;DR, Quiz, and a custom prompt. Length can be Short, Medium or Long. Output can be in 12 languages, including Kreyòl. Every timestamp is a link that jumps the video. Each result ends with a receipt line: model, token count, and where it ran.
- **Chat.** Grounded Q&A over the transcript. One-click prompts: Takeaways, Resources, Fact-check.
- **Highlights.** Star any transcript line. Highlights are saved per video in `chrome.storage.local`.
- **Export.** Markdown (summary, highlights and transcript, with youtu.be?t= links), TXT, or SRT.
- **Models.** Every local Ollama model appears in the picker. `NVIDIA · gemma-4-31b-it` uses build.nvidia.com: click ⚙ and paste an `nvapi-…` key. The key stays in this browser.

## NouGenOpen free fleet ($0, parallel)
Run the bridge, and **NouGenOpen · free fleet** appears first in the picker:
```
cd Outpost\NouGenOpen
set PYTHONPATH=src;..\NouGen\src
python -m nougen_open.cli serve --port 8765
```
- The bridge is OpenAI-compatible and listens only on 127.0.0.1:8765. It accepts requests from extensions and local tools and returns 403 to web pages.
- It rotates across Hugging Face, OpenRouter and Ollama Cloud keys from the Keymaker.
- **Long videos (over 14k characters):** the transcript is split at natural topic breaks (a gap of 3s or more, or a phrase like "moving on"). The pieces are summarized in parallel on free lanes via `/v1/nougen/map`, then combined in your chosen style. The result's last line shows how many chunks succeeded and on which providers.
- **Measured:** a deep dive of the 28-minute OBS video took 36s, with 13 chunks.

Ideas adopted from open-source summarizers:
- Grounded "shorter is better than invented" rule: molly554 (MIT).
- Topic-boundary chunking and "recommended to watch": DevRico003 (MIT).
- Map-reduce: bskrishna2006 (Apache-2.0).
- Tube-Brief has no license, so nothing was copied from it.

## Transcript tools, library chat and exports
- **Translate.** The Transcript tab has a language menu. Your model translates the transcript in batches of 30 lines, shown in place, saved per video, and used by Copy and the exports. Pick the original language to go back.
- **My library.** In Chat, switch from "This video" to "My library" to ask one question across every video you have shared to your vault. The bridge searches shards tagged `tube-report:` or `tube-morph:`; each answer lists its sources and marks the ones it cites.
- **Exports.** The download menu writes Markdown, TXT, SRT, TXT without timestamps, an Obsidian note (YAML front matter), a readable HTML page, a CSV of highlights and transcript, or one JSON file with everything.

See `docs/feature-matrix.md` for how this compares with Glasp and NoteGPT and what is still open.

## Videos without captions, and Batch
- **No captions.** When YouTube gives no transcript, the extension asks the NouGenOpen bridge, which downloads the audio and transcribes it on this computer (faster-whisper, free, up to 150 minutes). A "from audio" chip marks such a transcript, because names and numbers may be wrong. If YouTube refuses the audio too, the panel says so plainly instead of calling the video captionless.
- **Batch.** The Batch tab takes up to 20 YouTube links or a playlist link (a playlist of 50 adds its first 20) and writes one summary per video, one at a time, in the style you pick. Long videos are read in parts and combined. Each summary says whether its transcript came from captions or audio and checks its timestamps against the video. "Shard each" saves every finished summary and its transcript to your vault; Copy all, per-video Copy and Shard, and Continue after a failure are there too. Batch needs the bridge.
- Both depend on the bridge routes `/v1/nougen/transcript` and `/v1/nougen/playlist` (`pip install "nougen-open[tube]"`). YouTube rate-limits bursts: after many requests it answers captions with `IpBlocked` and audio with HTTP 403 for a while. NouGenTube reports that and does not try to get around it.

## Morph
The Morph tab reverses a video's intent: it asks what the video lets you build, and builds on what your vault already holds.
1. **Intents.** The model names the video's buildable ideas as short search phrases.
2. **Cross-reference.** The bridge looks each phrase up in NouGenShards (`POST /v1/nougen/recall`) and returns the matching shards. The video's own saved report is excluded. Results are over-fetched and split into two groups, vault knowledge (up to 10) and other saved videos (up to 4, one per video), so fresh video reports cannot crowd out older material.
3. **Plan.** For the target you pick (best fit, code architecture, app, website, skill/workflow, or "Something else" with your own words) it writes: Intent of the video, What the vault already has, Latest on the web, Morph plan, First build steps, Gaps, and a Valerion pass, the 21 steps of NouGenMorph orchestration (`NouGen/docs/architecture.md`), numbered in order. Shards are cited as `[id@dbN]`.
3b. **Latest on the web.** At the same time the bridge searches the live web for the top three intents (`POST /v1/nougen/web`: the three searches start on different providers, Google through SerpAPI, Exa and Tavily, then Context.dev, each used only if the bridge holds a key for it; a refused key is rested and the next is tried; keyless DuckDuckGo is the last resort; last-year freshness, top three pages read to text through the keyless Jina reader, cached 24 hours). The plan gets a "Latest on the web" section citing sources as `[w1]`, each linked to its page. Search keys live on the bridge (`SERPAPI_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `CONTEXT_DEV_API_KEY` in the environment, comma-separated for several, or in the keymaker), never in the extension.
4. **Check.** Code confirms every cited shard is one the vault returned, every cited web source is one the search found (and how many were read in full), all 21 Valerion steps appear numbered in order, every timestamp is inside the video, and no section is missing or empty (a cut-off plan is flagged). Grouped citations such as `[12@db3, 14@db3]` are read too. The results are written into the copied and saved plan. The checks live in `morph-core.js`, which has no browser dependencies.

"Shard it" saves the plan with the tag `tube-morph:<video id>`; a later morph of the same video says it was morphed before. "Copy build prompt" copies the plan as a prompt for a coding agent. If the bridge is not running the vault cannot be read: Morph still writes a plan from the video alone and marks it "Vault not read".

## Themes
The panel and the settings page use the Mono Violet colorways from the NouGenDesigns package (`designs/mono-violet/tokens.css`): Mono Violet dark, Mono Violet light, Arcade and Hardcade. "Auto" (the default) picks dark or light to match YouTube. Change it with ◐ in the panel header or on the settings page.

Arcade also uses continuous ("squircle") corners through the standard CSS `corner-shape` property, which Chrome supports from version 139; browsers without it show ordinary rounded corners. Electron's `-electron-corner-smoothing` is not used here: it only exists inside Electron and does nothing in a browser.

Following Electron's nativeTheme model, "Auto" matches YouTube's own theme when the page has one (its page colour), falls back to the system setting when it has none, and re-checks live when either changes: YouTube's theme switch, or the operating system flipping between light and dark while the page is open. The settings page follows the system the same way. The logic is in `theme-core.js` with `tests/theme-core.test.mjs`.

Accessibility follows the system too. With high contrast on (`prefers-contrast: more`) borders switch to the strong border colour and secondary text to full strength; in Windows forced-colors mode every control gets a visible system-colour border and the selected tab or action a highlight outline.

## Long jobs keep the computer awake
From Electron's powerSaveBlocker. A batch, a Morph, a translation, audio transcription or a long summary holds a "keep the system awake" request (never the screen) for as long as it runs, so a laptop does not sleep halfway through. The hold is one open connection to the background page: when the job ends, the panel closes, the tab navigates away or the page crashes, the connection closes and the hold is released. `power-core.js` keeps Electron's model on top of `chrome.power`: `start(type)` returns an id, `stop(id)` says whether it stopped, blockers overlap, and a stronger type wins until it stops. A worker that starts always lets go of any hold a dead one left behind. Switch it off under "Long jobs" in settings. It needs the `power` permission.

## Long jobs, seen from outside the tab
From Electron's BrowserWindow doc:
- **Progress on the toolbar button** (like `setProgressBar`): a batch shows `done/total`, a Morph `1/4` to `4/4`, a translation a percentage, on the extension button in any tab; it clears when the job ends. The button also brings the panel forward in the current tab, opening it if it was collapsed, and opens settings on a tab with no panel.
- **Closing is asked about** (like `close` with `preventDefault`): closing or reloading the tab while a batch, a Morph or a translation is running shows the browser's leave-this-page prompt, so a 20-video batch is not lost by accident.
- **Hidden tabs do not starve the worker** (like `backgroundThrottling`): browsers slow a hidden tab's timers, so while a job holds, the background worker also pings itself every 20 s instead of relying on the page. This is a safety net: on Chrome 157 an open connection alone kept the worker alive for the whole 400 s I measured (with and without the ping), so it matters for other Chrome versions, not that one.
- **First frame in the right colours** (like `backgroundColor`): the panel is built in the right theme before the saved choice loads, and the settings page starts in the system's scheme.

## Windows, displays and links
Three more lessons from Electron's system-preferences, screen and shell docs, applied the browser way:
- **Fit the space you actually have.** YouTube hides its side column in the one-column layout (a narrow window, or a high browser zoom). The panel used to vanish with it; it now sits under the player there, moves back when the window widens again, and is capped at 1400 px on very tall displays. Checked at 1280x560, 1920x1080 at 1x and 2x, 3840x2160 and 900x800.
- **Native controls follow the theme.** `color-scheme` and `accent-color` are set per theme, so scrollbars and form controls match instead of staying light, and the scroll that follows the video honours "reduce motion".
- **Links leave quietly.** Every link that opens a new tab is `noopener noreferrer` with no referrer, so a site you open from a Morph source never learns which video you were watching. Only http and https links are used. `tests/links.test.mjs` fails if a new external link forgets this.

## Icons
`icons/` holds the extension icon at 16, 32, 48 and 128 px: the same "N" on the Mono Violet gradient as the panel badge, drawn on a superellipse so it matches the Arcade corners. `python icons/make_icons.py` redraws them (needs Pillow). Several sizes are supplied for the same reason Electron's nativeImage takes several scale factors: each place that shows the icon picks the size it needs.

## Model routes and your own keys
Open ⚙ in the panel header for the settings page.
- **Provider keys.** Claude (Anthropic), OpenAI, Google Gemini, DeepSeek, OpenRouter, NVIDIA build, or any OpenAI-compatible endpoint. Paste a key and press "Test key and load models": the key is checked against the provider and the model list comes from the provider itself, so no model name is guessed. Keys are stored in this browser only (`chrome.storage.local`) and sent only to that provider.
- **Auto** (the default route) tries each available route in order and moves on when one fails or stays silent: the NouGenOpen free fleet, local Ollama, then your keyed providers. The order can be flipped to "my keys first". The summary's last line names the route that answered and how many failed before it.
- **Claude** is called through the Messages API directly with your key. No sampling parameters are sent (current Claude models reject them), and the server-side refusal fallback is requested on models that support it.

## Intelligence report, checker and shards
- **Intelligence report** (the default summary style) follows the Media Intelligence Architect format: Executive Summary, Key Insights & Technical Milestones, Strategic Action Items, Quality Control / Fact-Check, Notable Quotes.
- **Full Transcript Archive.** "Copy report + transcript" puts the report first and the complete transcript second. The extension builds the archive from the transcript itself, so it is always complete and word for word, and the model spends no tokens repeating it.
- **Checked against the transcript.** After every summary the extension checks, in code, that each quoted passage appears in the transcript word for word and that every timestamp is inside the video. Anything that fails is listed. This checks wording and times only, not whether the speaker is right.
- **Shard.** The header button saves the video to NouGenShards through the local bridge (`POST /v1/nougen/shard`): the full transcript, plus the report and the check results if a summary exists. Tags: `nougentube`, `tube-report:<video id>`.
- **Copy prompt + transcript for another AI** copies the Architect instructions with the transcript, for pasting into Gemini, ChatGPT or Claude.

## Transcript failsafes
The transcript comes from several independent sources, tried in order, and the whole ladder runs up to 3 times before any error shows:
1. **Saved copy.** The 40 most recent transcripts are kept in the browser, so a revisit loads at once. The "saved ↻" chip fetches it from YouTube again.
2. **YouTube's transcript panel**, both the classic and the modern layout, followed live as the page renders.
3. **The player's own captions.** `inject.js` runs in the page and passes along the caption track the player downloads. This works in background tabs. If captions are off, they are switched on for a moment and then put back.
4. **YouTube's caption service** called directly (usually blocked, kept as a last resort).

The error text says which case it is: the video has no captions at all, or YouTube has them but didn't return them. If the extension is updated while a tab stays open, that tab's panel asks for a refresh instead of failing.

## Notes
- Ollama returns 403 for `chrome-extension://` origins. `rules.json` (declarativeNetRequest) strips the Origin header on requests to localhost:11434, so you don't need to set `OLLAMA_ORIGINS`.
- YouTube renders the transcript only while the tab is visible. In a background tab the panel shows a waiting message and loads once you switch to the tab.
- The first local call can take about 2 minutes while Ollama loads the model. After that, a summary takes about 10–20 seconds on gemma4:e2b-qat.
