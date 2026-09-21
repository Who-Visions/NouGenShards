#!/usr/bin/env python3
"""Run the canonical Relay watcher against the handoff-bearing clone."""
import os

os.environ.setdefault("NOUGEN_RELAY_DIR", r"C:\Users\super\Outpost\NouGenRelay")

import relay_watch_node as impl

raise SystemExit(impl.main())
