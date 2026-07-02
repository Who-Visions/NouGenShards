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

# Install exact pinned dependencies from the compiled lockfile first (fully
# reproducible builds - regenerate with `uv pip compile --universal
# pyproject.toml -o requirements.txt`), then the package itself without
# re-resolving.
COPY --chown=user:user . /app
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

# app.py writes persistent state to /data when SPACE_ID is set. Provision a
# writable /data so the node still boots if HF persistent storage is off.
RUN mkdir -p /data && chown -R user:user /data

USER user
EXPOSE 7860

# app.py exposes `app` (FastAPI) with the Gradio Cortex HUD mounted at "/".
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
