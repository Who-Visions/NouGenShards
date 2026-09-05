FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

# Run as a non-root user. The dam holds captured shard intent, so a container
# escape here reaches the spool; root is not needed to bind 7860 or to read
# /app. Trivy DS-0002 blocks the build without this.
RUN useradd --create-home --uid 10001 dam && chown -R dam:dam /app
USER dam

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
