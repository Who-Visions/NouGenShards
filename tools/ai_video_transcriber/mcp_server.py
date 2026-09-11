#!/usr/bin/env python3
"""
AI Video Transcriber —— MCP 服务（stdio）。

把转录管线暴露为 MCP 工具，让 Claude Code、Claude Desktop、Codex 等任何
支持 MCP 的客户端都能作为原生工具调用，而不必自己拼 shell 命令。

安装依赖：
    pip install "mcp>=2.0"

Claude Code 注册：
    claude mcp add video-transcriber -- /abs/path/venv/bin/python /abs/path/mcp_server.py

Codex 注册（~/.codex/config.toml）：
    [mcp_servers.video-transcriber]
    command = "/abs/path/venv/bin/python"
    args = ["/abs/path/mcp_server.py"]

手动冒烟测试：
    python3 mcp_server.py --selftest
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from mcp.server import MCPServer  # noqa: E402

import transcribe as cli  # noqa: E402  复用命令行那套编排，避免两份实现

DEFAULT_OUTPUT_DIR = os.getenv("TRANSCRIBE_OUTPUT_DIR", str(PROJECT_ROOT / "temp"))

mcp = MCPServer(
    name="video-transcriber",
    title="AI Video Transcriber",
    instructions=(
        "Transcribe and summarize videos/podcasts from 30+ platforms (YouTube, TikTok, "
        "Bilibili, Apple Podcasts, SoundCloud...) or from local media/text files. "
        "Uses platform subtitles when available and falls back to local Whisper. "
        "If a video contains no speech the tool reports no_speech=true and returns no "
        "summary — never invent transcript content in that case."
    ),
)


def _args_namespace(**overrides: Any) -> argparse.Namespace:
    """构造与命令行等价的参数对象，保证 MCP 与 CLI 行为完全一致。"""
    defaults = dict(
        source="",
        summary_language="en",
        output_dir=DEFAULT_OUTPUT_DIR,
        keep_video=True,
        no_llm=False,
        whisper_model=os.getenv("WHISPER_MODEL_SIZE", "base"),
        video_max_height=int(os.getenv("VIDEO_MAX_HEIGHT", "720")),
        api_key=None,
        base_url=None,
        model=None,
        json=True,   # 抑制人类可读输出
        quiet=True,  # 进度信息不能污染 stdio 上的 MCP 协议流
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@mcp.tool(
    name="transcribe_video",
    title="Transcribe a video, podcast, or media file",
    description=(
        "Transcribe and summarize a video/podcast URL (YouTube, TikTok, Bilibili, "
        "Apple Podcasts, SoundCloud, and 30+ more) or a local media/.txt file. "
        "Returns the transcript text, a summary, an optional translation, and paths to "
        "the Markdown files written to disk. Set no_llm=true to get only the raw "
        "transcript with no API key required. When the source has no speech at all, "
        "no_speech is true and transcript/summary are empty — trust that rather than "
        "guessing what was said."
    ),
)
async def transcribe_video(
    source: Annotated[str, Field(description="Video/podcast URL, or an absolute path to a local media or .txt file")],
    summary_language: Annotated[
        Literal["en", "zh", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "ar"],
        Field(description="Language for the summary (and translation, if the source differs)"),
    ] = "en",
    no_llm: Annotated[bool, Field(description="Skip optimize/translate/summarize; return the raw transcript only. Needs no API key")] = False,
    keep_video: Annotated[bool, Field(description="Also download and keep the original video file")] = False,
    whisper_model: Annotated[
        Literal["tiny", "base", "small", "medium", "large"],
        Field(description="Whisper model size; larger is more accurate but slower"),
    ] = "base",
    output_dir: Annotated[Optional[str], Field(description="Directory for the generated Markdown files")] = None,
) -> dict:
    args = _args_namespace(
        source=source,
        summary_language=summary_language,
        no_llm=no_llm,
        keep_video=keep_video,
        whisper_model=whisper_model,
        output_dir=output_dir or DEFAULT_OUTPUT_DIR,
    )

    try:
        result = await cli.run(args)
    except cli.TranscribeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # 下载/转码失败等
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    files = result.get("files", {})

    def read(kind: str) -> str:
        path = files.get(kind)
        if not path:
            return ""
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return ""

    return {
        "ok": True,
        "title": result["title"],
        "no_speech": result["no_speech"],
        "detected_language": result["detected_language"],
        "summary_language": result["summary_language"],
        # 正文直接回给模型，省掉一次读文件的往返
        "transcript": read("transcript"),
        "summary": read("summary"),
        "translation": read("translation"),
        "files": files,
        "media": result.get("media"),
    }


async def _selftest() -> int:
    """不启协议流，直接检查工具是否注册正确、schema 是否成型。"""
    tools = await mcp.list_tools()
    print(f"registered tools: {len(tools)}")
    for t in tools:
        print(f"  - {t.name}: {(t.description or '')[:70]}…")
        props = (t.input_schema or {}).get("properties", {})
        print(f"    params: {list(props)}")
        required = (t.input_schema or {}).get("required", [])
        print(f"    required: {required}")
    ok = len(tools) == 1 and tools[0].name == "transcribe_video"
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    # stdio 传输下 stdout 属于 JSON-RPC 协议流，任何库把日志写到 stdout 都会把它冲坏。
    # force=True 会掀掉 faster-whisper 等依赖在 import 时装上的 handler，统一钉到 stderr。
    import logging

    logging.basicConfig(
        level=os.getenv("MCP_LOG_LEVEL", "WARNING").upper(),
        stream=sys.stderr,
        format="%(levelname)s:%(name)s:%(message)s",
        force=True,
    )

    if "--selftest" in sys.argv:
        sys.exit(asyncio.run(_selftest()))
    mcp.run(transport="stdio")
