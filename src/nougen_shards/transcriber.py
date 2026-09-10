"""
NouGen Core Media & Audio Transcription Subsystem (Shang Tsung Transcriber).

Bakes audio/video downloading (yt-dlp, 30+ platforms), subtitle extraction,
Faster-Whisper local speech-to-text, and automatic NouGen 9-DB FTS5 sharding
directly into the nougen_shards core package.
"""

import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yt_dlp
from faster_whisper import WhisperModel

from . import core as shards

# Media MIME & extensions
VIDEO_EXT = frozenset({".mp4", ".mkv", ".webm", ".mov", ".flv"})
AUDIO_EXT = frozenset({".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"})
ALLOWED_MEDIA_EXT = VIDEO_EXT | AUDIO_EXT | frozenset({".txt"})


def sanitize_slug(title: str, max_len: int = 80) -> str:
    """Sanitize title for files and shard slugs."""
    if not title:
        return "untitled"
    safe = re.sub(r"[^\w\-\s]", "", title)
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    return safe[:max_len] or "untitled"


class TranscribeEngine:
    """Core audio transcription engine utilizing Faster-Whisper."""

    def __init__(self, model_size: str = "base", device: str = "auto", compute_type: str = "default"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            dev = self.device
            c_type = self.compute_type
            if dev == "auto":
                try:
                    import ctranslate2
                    if ctranslate2.get_cuda_device_count() > 0:
                        dev = "cuda"
                        c_type = "float16" if c_type == "default" else c_type
                    else:
                        dev = "cpu"
                        c_type = "int8" if c_type == "default" else c_type
                except Exception:
                    dev = "cpu"
                    c_type = "int8"
            self._model = WhisperModel(self.model_size, device=dev, compute_type=c_type)
        return self._model

    def transcribe_file(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe an audio file synchronously."""
        model = self._get_model()
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        collected_segments = []
        full_text_parts = []
        for s in segments:
            collected_segments.append({
                "start": s.start,
                "end": s.end,
                "text": s.text.strip(),
            })
            full_text_parts.append(s.text.strip())

        return {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "text": " ".join(full_text_parts),
            "segments": collected_segments,
        }


class NouGenTranscriber:
    """Complete media downloader, transcriber, and automatic shard ingester."""

    def __init__(self, output_dir: Optional[str] = None, whisper_model: str = "base"):
        self.output_dir = Path(output_dir or (Path.home() / ".nougen" / "transcripts")).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = TranscribeEngine(model_size=whisper_model)

    def extract_or_download_audio(self, source: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        Process a URL or local file into a 16kHz mono audio stream.
        Returns (audio_path, title, metadata_dict).
        """
        is_url = source.startswith(("http://", "https://"))

        if not is_url:
            p = Path(source).resolve()
            if not p.is_file():
                raise FileNotFoundError(f"Local file not found: {source}")
            title = p.stem
            out_audio = self.output_dir / f"{sanitize_slug(title)}_{uuid.uuid4().hex[:6]}.m4a"
            
            cmd = [
                "ffmpeg", "-y", "-nostdin", "-i", str(p),
                "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "aac", "-b:a", "128k",
                str(out_audio),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not out_audio.is_file():
                if p.suffix.lower() in AUDIO_EXT:
                    return str(p), title, {"source": source, "is_local": True}
                raise RuntimeError(f"FFmpeg audio extraction failed: {res.stderr[:500]}")
            return str(out_audio), title, {"source": source, "is_local": True}

        out_tmpl = str(self.output_dir / "%(title).70s_%(id)s.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "128",
            }],
            "postprocessor_args": ["-ac", "1", "-ar", "16000", "-movflags", "+faststart"],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(source, download=True)
            title = meta.get("title", "Online Media")
            filename = ydl.prepare_filename(meta)
            audio_path = Path(filename).with_suffix(".m4a")
            if not audio_path.is_file():
                audio_path = Path(filename)
            return str(audio_path), title, {
                "source": source,
                "uploader": meta.get("uploader"),
                "duration": meta.get("duration"),
                "platform": meta.get("extractor_key", "web"),
                "webpage_url": meta.get("webpage_url", source),
            }

    def process_and_shard(
        self,
        source: str,
        language: Optional[str] = None,
        auto_shard: bool = True,
        domain_key: str = "media/transcripts",
    ) -> Dict[str, Any]:
        """
        Full Shang Tsung pipeline:
        1. Extract/download audio
        2. Transcribe with Whisper
        3. Format Markdown artifact
        4. Auto-shard directly into NouGen 9-DB cluster
        """
        audio_path, title, meta = self.extract_or_download_audio(source)
        res = self.engine.transcribe_file(audio_path, language=language)

        text = res["text"]
        detected_lang = res["language"]
        segments = res["segments"]

        md_lines = [
            f"# {title}",
            "",
            f"- **Source**: [{source}]({source})",
            f"- **Platform**: `{meta.get('platform', 'local')}`",
            f"- **Detected Language**: `{detected_lang}`",
            f"- **Duration**: `{res.get('duration', 0):.1f}s`",
            "",
            "## Full Transcript",
            "",
            text,
            "",
            "## Timed Segments",
            "",
        ]
        for seg in segments:
            m_start, s_start = divmod(int(seg["start"]), 60)
            m_end, s_end = divmod(int(seg["end"]), 60)
            md_lines.append(f"- **`[{m_start:02d}:{s_start:02d} -> {m_end:02d}:{s_end:02d}]`**: {seg['text']}")

        full_md = "\n".join(md_lines)
        out_file = self.output_dir / f"{sanitize_slug(title)}.md"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(full_md)

        shard_id = None
        if auto_shard and text.strip():
            tags = ["transcript", "audio", "video", str(meta.get("platform", "media")).lower()]
            if detected_lang:
                tags.append(detected_lang)
            
            ok = shards.capture(
                event_type="KNOWLEDGE",
                title=f"Transcript: {title[:70]}",
                content=full_md,
                tags=tags,
                domain_key=domain_key,
                source_uri=source,
            )
            shard_id = "captured" if ok else "existing"

        return {
            "title": title,
            "source": source,
            "language": detected_lang,
            "text": text,
            "transcript_file": str(out_file),
            "audio_file": audio_path,
            "meta": meta,
            "sharded": shard_id,
        }
