# Hugging Face Space (Docker SDK) — NouGenShards FastAPI + Gradio node.
# Drafted by Fleet Sol-Ai (QB), finalized/hardened by Coach (Apollo).
# Serves the token-auth node API and the mounted Cortex HUD on port 7860.
# python:3.10 is at end-of-life (final security release Oct 2026 cycle);
# 3.12 is supported through Oct 2028 and matches the CI matrix ceiling.
FROM python:3.12-slim

# HF Spaces run the container as a non-root user (uid 1000).
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app

# FFmpeg is used by the bounded local Whisper transcription tool.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install the pinned base dependencies first, then the local package without
# re-resolving them. Install only the optional transcript and Whisper runtime
# dependencies afterward. Regenerate the base lock with `uv pip compile
# --universal pyproject.toml -o requirements.txt`.
COPY --chown=user:user . /app
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps . \
    && pip install --no-cache-dir 'youtube-transcript-api>=0.6' 'yt-dlp>=2024.1.1' 'faster-whisper>=1.1.0'

# app.py writes persistent state to /data when SPACE_ID is set. Provision a
# writable /data so the node still boots if HF persistent storage is off.
RUN mkdir -p /data && chown -R user:user /data

USER user
EXPOSE 7860

# app.py exposes `app` (FastAPI) with the Gradio Cortex HUD mounted at "/".
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
