#!/usr/bin/env bash
# Probe the YouTube transcript endpoint; run the roster batch once the IP block clears.
# Interval/attempts env-tunable: NOUGEN_YT_PROBE_INTERVAL (s), NOUGEN_YT_PROBE_MAX.
cd "$(dirname "$0")/.." || exit 1
INTERVAL="${NOUGEN_YT_PROBE_INTERVAL:-1800}"
MAX="${NOUGEN_YT_PROBE_MAX:-12}"
for i in $(seq 1 "$MAX"); do
  if PYTHONPATH=src python -c "from youtube_transcript_api import YouTubeTranscriptApi as Y; Y().fetch('X-h3qWWoZiE')" 2>/dev/null; then
    echo "[$i/$MAX] UNBLOCKED — running batch"
    PYTHONPATH=src python tools/nougentube_batch.py --days 30 --confirm
    exit $?
  fi
  echo "[$i/$MAX] still blocked; sleeping ${INTERVAL}s"
  sleep "$INTERVAL"
done
echo "gave up after $MAX probes"
exit 2
