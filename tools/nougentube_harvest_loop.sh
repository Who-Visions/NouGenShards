#!/usr/bin/env bash
# Chip away at the roster across rate-limit windows until a full clean pass.
# Env: NOUGEN_YT_PROBE_INTERVAL (default 1800s), NOUGEN_YT_MAX_CYCLES (default 24).
cd "$(dirname "$0")/.." || exit 1
INTERVAL="${NOUGEN_YT_PROBE_INTERVAL:-1800}"
MAX="${NOUGEN_YT_MAX_CYCLES:-24}"
for cycle in $(seq 1 "$MAX"); do
  until PYTHONPATH=src python -c "from youtube_transcript_api import YouTubeTranscriptApi as Y; Y().fetch('X-h3qWWoZiE')" 2>/dev/null; do
    echo "[cycle $cycle] blocked; sleeping ${INTERVAL}s"
    sleep "$INTERVAL"
  done
  echo "[cycle $cycle] unblocked — harvesting"
  PYTHONPATH=src python tools/nougentube_batch.py --days 30 --confirm
  rc=$?
  if [ "$rc" -eq 0 ]; then echo "CLEAN PASS — harvest complete"; exit 0; fi
  if [ "$rc" -ne 3 ]; then echo "batch failed rc=$rc"; exit "$rc"; fi
  echo "[cycle $cycle] circuit opened — cooling down ${INTERVAL}s"
  sleep "$INTERVAL"
done
echo "max cycles reached"; exit 2
