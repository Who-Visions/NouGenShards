#!/usr/bin/env python3
"""
AI Video Transcriber —— 无头命令行入口。

供人和 AI agent 直接调用，不需要启动 Web 服务、不需要浏览器、没有 SSE：
一条命令跑完「取字幕 / 转录 → 优化 → 翻译 → 摘要」，把 Markdown 写到磁盘，
并在 stdout 打印结果路径（`--json` 时打印机器可读的结构）。

用法：
    python3 transcribe.py <URL 或本地文件> [选项]

示例：
    python3 transcribe.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python3 transcribe.py talk.mp4 --summary-language en --json
    python3 transcribe.py notes.txt --no-video --quiet
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# 让 backend/ 里的模块可以按平铺名互相 import（与 uvicorn 在 backend/ 下启动一致）
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from pipeline import (  # noqa: E402
    NO_SPEECH_NOTICE,
    UPLOAD_ALLOWED_EXT,
    media_kind,
    sanitize_title_for_filename,
    transcribed_speech,
    txt_to_raw_transcript_markdown,
)
from summarizer import Summarizer  # noqa: E402
from transcriber import Transcriber  # noqa: E402
from translator import Translator  # noqa: E402
from video_processor import VideoProcessor  # noqa: E402

logger = logging.getLogger("transcribe")


class TranscribeError(RuntimeError):
    """预期内的失败（输入非法、下载失败等），只打印信息不打印堆栈。"""


def _log(msg: str, quiet: bool) -> None:
    """进度信息一律走 stderr，保证 stdout 只有最终结果，便于管道与 --json。"""
    if not quiet:
        print(msg, file=sys.stderr, flush=True)


def _looks_like_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


async def _extract_from_url(args, vp, transcriber, out_dir, quiet):
    """链接输入：优先字幕，无字幕则下载并转录。返回 (raw_script, title, media_path)。"""
    media_task = None
    if args.keep_video:
        stem = f"video_{sanitize_title_for_filename(args.source)[:20] or 'src'}"
        media_task = asyncio.create_task(
            vp.download_video(args.source, out_dir, stem, args.video_max_height)
        )

    _log("· 检测字幕…", quiet)
    subtitle_text, sub_title, sub_lang = await vp.fetch_subtitles(args.source, out_dir)

    media_path = None
    if subtitle_text:
        _log(f"· 命中字幕（{sub_lang}），跳过 Whisper", quiet)
        transcriber.last_detected_language = sub_lang
        raw_script, title = subtitle_text, sub_title or "unknown"
    else:
        _log("· 无字幕，改用 Whisper", quiet)
        audio_path = title = None

        # 已经在下载原视频时，直接从它抽音轨，避免同一个视频下载两遍
        if media_task is not None:
            video_path, media_title = await media_task
            if video_path:
                media_path = video_path
                try:
                    audio_path = await vp.normalize_local_media_to_m4a(
                        Path(video_path), out_dir
                    )
                    title = media_title or sub_title or "unknown"
                    _log("· 复用原视频抽取音轨", quiet)
                except Exception as e:
                    logger.warning(f"从原视频抽音轨失败，回退独立音频下载: {e}")
                    audio_path = None

        if audio_path is None:
            _log("· 下载音频…", quiet)
            audio_path, title = await vp.download_and_convert(
                args.source, out_dir, prefetched_title=sub_title or None
            )

        _log("· 转录中（Whisper）…", quiet)
        raw_script = await transcriber.transcribe(audio_path)

    if media_task is not None and media_path is None:
        video_path, _ = await media_task
        media_path = video_path

    return raw_script, title, media_path


async def _extract_from_file(args, vp, transcriber, out_dir, quiet):
    """本地文件输入：.txt 直接进文本管线，音视频先转码再转录。"""
    src = Path(args.source).expanduser().resolve()
    if not src.is_file():
        raise TranscribeError(f"文件不存在: {src}")

    ext = src.suffix.lower()
    if ext not in UPLOAD_ALLOWED_EXT:
        raise TranscribeError(
            f"不支持的文件类型 {ext or '(无扩展名)'}；"
            f"支持: {', '.join(sorted(UPLOAD_ALLOWED_EXT))}"
        )

    title = sanitize_title_for_filename(src.stem) or "upload"

    if ext == ".txt":
        body = src.read_text(encoding="utf-8", errors="replace")
        if not body.strip():
            raise TranscribeError("文本文件为空")
        transcriber.last_detected_language = None
        return txt_to_raw_transcript_markdown(body), title, None

    _log("· 转码音频…", quiet)
    audio_path = await vp.normalize_local_media_to_m4a(src, out_dir)
    _log("· 转录中（Whisper）…", quiet)
    raw_script = await transcriber.transcribe(audio_path)

    # 本地原件本身就是「原视频」，无需再下载
    return raw_script, title, str(src) if args.keep_video else None


async def run(args) -> dict:
    quiet = args.quiet or args.json
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    vp = VideoProcessor()
    transcriber = Transcriber(model_size=args.whisper_model)
    summarizer = Summarizer(api_key=args.api_key, base_url=args.base_url, model=args.model)
    translator = Translator(api_key=args.api_key, base_url=args.base_url, model=args.model)

    is_url = _looks_like_url(args.source)
    extract = _extract_from_url if is_url else _extract_from_file
    raw_script, title, media_path = await extract(args, vp, transcriber, out_dir, quiet)

    source_ref = args.source if is_url else f"upload:{Path(args.source).name}"
    safe_title = sanitize_title_for_filename(title)
    stem = safe_title[:60] or "untitled"

    written = {}

    def write(kind: str, text: str) -> str:
        path = out_dir / f"{kind}_{stem}.md"
        path.write_text(text, encoding="utf-8")
        written[kind] = str(path)
        return str(path)

    write("raw", (raw_script or "") + f"\n\nsource: {source_ref}\n")

    result = {
        "source": args.source,
        "title": title,
        "no_speech": False,
        "detected_language": None,
        "summary_language": args.summary_language,
        "files": written,
        "media": None,
    }
    if media_path and Path(media_path).exists():
        p = Path(media_path)
        result["media"] = {
            "path": str(p),
            "kind": media_kind(p.suffix.lower()),
            "size_bytes": p.stat().st_size,
        }

    # 无语音短路：绝不能把空文稿交给 LLM，否则它会编造出整段不存在的对话
    if not transcribed_speech(raw_script):
        _log("· 未检测到语音，跳过优化/翻译/摘要", quiet)
        result["no_speech"] = True
        result["detected_language"] = (
            transcriber.get_detected_language(raw_script) or ""
        ).strip() or None
        write("transcript", f"# {title}\n\n{NO_SPEECH_NOTICE}\n\nsource: {source_ref}\n")
        return result

    if args.no_llm:
        _log("· --no-llm：仅输出转录文本", quiet)
        write("transcript", f"# {title}\n\n{raw_script}\n\nsource: {source_ref}\n")
        return result

    _log("· 优化转录文本…", quiet)
    script = await summarizer.optimize_transcript(raw_script)
    write("transcript", f"# {title}\n\n{script}\n\nsource: {source_ref}\n")

    detected = (transcriber.get_detected_language(raw_script) or "").strip()
    if not detected:
        detected = translator.infer_language_code(raw_script)
    detected = translator.normalize_lang_code(detected) or detected
    result["detected_language"] = detected

    if translator.languages_differ_for_translation(detected, args.summary_language):
        _log(f"· 翻译 {detected} → {args.summary_language}…", quiet)
        translation = await translator.translate_text(
            script, args.summary_language, detected
        )
        write("translation", f"# {title}\n\n{translation}\n\nsource: {source_ref}\n")

    _log("· 生成摘要…", quiet)
    summary = await summarizer.summarize(script, args.summary_language, title)
    write("summary", f"{summary}\n\nsource: {source_ref}\n")

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transcribe.py",
        description="Transcribe and summarize a video/podcast URL or a local media/text file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法：")[-1],
    )
    p.add_argument("source", help="视频/播客 URL，或本地音视频/.txt 文件路径")
    p.add_argument("-l", "--summary-language", default=os.getenv("SUMMARY_LANGUAGE", "en"),
                   help="摘要输出语言，默认 en")
    p.add_argument("-o", "--output-dir", default="./temp",
                   help="Markdown 与媒体输出目录，默认 ./temp")
    p.add_argument("--no-video", dest="keep_video", action="store_false",
                   help="不下载/不保留原视频（只要文本时更快更省空间）")
    p.add_argument("--no-llm", action="store_true",
                   help="只输出转录文本，跳过优化/翻译/摘要（无需 API Key）")
    p.add_argument("--whisper-model", default=os.getenv("WHISPER_MODEL_SIZE", "base"),
                   choices=["tiny", "base", "small", "medium", "large"],
                   help="Whisper 模型大小，默认 base")
    p.add_argument("--video-max-height", type=int,
                   default=int(os.getenv("VIDEO_MAX_HEIGHT", "720")),
                   help="原视频下载清晰度上限，默认 720")
    p.add_argument("--api-key", default=None, help="OpenAI 兼容 API Key，默认读 OPENAI_API_KEY")
    p.add_argument("--base-url", default=None, help="OpenAI 兼容地址，默认读 OPENAI_BASE_URL")
    p.add_argument("--model", default=None, help="使用的模型 ID，默认服务端/环境默认值")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON（供程序/agent 解析）")
    p.add_argument("-q", "--quiet", action="store_true", help="不打印进度信息")
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.WARNING if (args.quiet or args.json) else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        stream=sys.stderr,
    )

    try:
        result = asyncio.run(run(args))
    except TranscribeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("aborted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{result['title']}")
        if result["no_speech"]:
            print("  (no speech detected — summary and translation skipped)")
        for kind, path in result["files"].items():
            print(f"  {kind:11} {path}")
        if result["media"]:
            mb = result["media"]["size_bytes"] / (1024 * 1024)
            print(f"  {result['media']['kind']:11} {result['media']['path']} ({mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
