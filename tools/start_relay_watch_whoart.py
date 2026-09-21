#!/usr/bin/env python3
"""Run the canonical Relay watcher against the handoff-bearing clone."""
import os
from pathlib import Path

relay_dir = Path(__file__).resolve().parents[2] / "NouGenRelay"
os.environ.setdefault("NOUGEN_RELAY_DIR", str(relay_dir))

import relay_watch_node as impl

raise SystemExit(impl.main())
