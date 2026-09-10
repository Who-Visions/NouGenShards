---
name: video-transcribe
description: Transcribe and summarize a video or podcast from a URL (YouTube, TikTok, Bilibili, Apple Podcasts, SoundCloud, 30+ platforms) or from a local media/.txt file. Use when the user shares a video/podcast link or media file and wants a transcript, summary, translation, or the original video downloaded. Triggers on "transcribe", "summarize this video", "what does this video say", "get the transcript", "转录", "视频摘要".
---

# Video Transcribe

Runs this repo's pipeline headlessly: platform subtitles when available (seconds),
local Whisper as fallback, then optimize -> translate -> summarize.

## Before running

The command must be run from the AI Video Transcriber repository root and needs the
project virtualenv plus `ffmpeg`. Verify once per session:

```bash
ls venv/bin/python && command -v ffmpeg
```

- No venv: run `./install.sh`, or `python3 -m venv venv && venv/bin/pip install -r requirements.txt`.
- No ffmpeg: install it first with `brew install ffmpeg` on macOS or `sudo apt install ffmpeg` on Debian/Ubuntu. Do not proceed without it; audio extraction will fail.

## Run it

```bash
venv/bin/python transcribe.py "<URL or file path>" --json
```

Always pass `--json`: it puts machine-readable output on stdout and keeps progress
chatter on stderr. Parse the JSON rather than scraping log lines.

Useful flags:

| Flag | When to use |
|------|-------------|
| `-l, --summary-language <code>` | Summary language: `en`, `zh`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `ja`, `ko`, `ar`. Default `en` |
| `--no-llm` | No API key is available, or the user only wants the raw transcript. Skips optimize/translate/summarize |
| `--no-video` | The user does not want the source video kept |
| `--whisper-model small` | Accuracy matters more than speed. `tiny` to `large`, default `base` |
| `-o <dir>` | Write the Markdown somewhere other than `./temp` |

The LLM steps need an OpenAI-compatible key via `OPENAI_API_KEY` and optionally
`OPENAI_BASE_URL`. Without one the pipeline still transcribes but falls back to
basic formatting; prefer `--no-llm` when the user only needs the transcript.

Provider settings:

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_TRANSLATION_MODEL="gpt-4o"  # optional
```

For a one-off run, `transcribe.py` also accepts `--api-key`, `--base-url`, and
`--model`. Prefer environment variables when possible so API keys are not written
to shell history.

## Reading the result

```json
{
  "title": "...",
  "no_speech": false,
  "detected_language": "en",
  "files": { "raw": "...", "transcript": "...", "summary": "...", "translation": "..." },
  "media": { "path": "...", "kind": "video", "size_bytes": 2243691 }
}
```

Read the `transcript` and `summary` paths to get the content. `translation` is
present only when the source language differs from the summary language.

## Critical: `no_speech`

When `"no_speech": true` the source contains no speech. There is no transcript,
summary, or translation. The pipeline deliberately skips the LLM so that nothing
gets invented.

If you see this, tell the user the video has no speech. Do not guess at the
content, infer it from the title, or describe what the video probably says.

## Failure modes

- Exit `2`: bad input, such as a missing file, unsupported extension, or empty text file. Report the message and fix the argument.
- Exit `1`: download/transcode failure, usually an unreachable URL, region-blocked/private video, or missing ffmpeg. Report the actual error.
- First run downloads Whisper weights, so it can look stalled for a minute.
- Long videos are slow in Whisper mode. Warn the user before starting if no platform subtitles are available.
