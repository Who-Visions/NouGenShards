# Hugging Face Space (Docker SDK) — NouGenShards FastAPI + Gradio node.
# Drafted by Fleet Sol-Ai (QB), finalized/hardened by Coach (Apollo).
# Serves the token-auth node API and the mounted Cortex HUD on port 7860.
FROM python:3.10-slim

# HF Spaces run the container as a non-root user (uid 1000).
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install the package from pyproject (pulls fastapi, uvicorn, gradio, mcp, ...).
COPY --chown=user:user . /app
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# app.py writes persistent state to /data when SPACE_ID is set. Provision a
# writable /data so the node still boots if HF persistent storage is off.
RUN mkdir -p /data && chown -R user:user /data

USER user
EXPOSE 7860

# app.py exposes `app` (FastAPI) with the Gradio Cortex HUD mounted at "/".
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
