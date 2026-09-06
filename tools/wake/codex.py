"""Resume the explicitly registered Codex task through its native queue.

The native runtime serializes turns; a busy task receives a follow-up, never a
second model process. Queue acceptance is deliberately not a read receipt.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil

BINARY = os.environ.get('NOUGEN_CODEX_CLI') or shutil.which('codex')
if not BINARY or not Path(BINARY).is_file():
    raise ImportError('Codex CLI unavailable')


class Adapter:
    name = 'codex'
    aliases = ()

    def is_idle(self):
        # Queueing is safe while busy: Codex owns turn scheduling.
        return True

    def wake(self, text, event):
        path = Path(__file__).resolve().parents[2] / 'src/nougen_shards/codex_pipe.py'
        spec = importlib.util.spec_from_file_location('nougen_codex_delivery', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.deliver(text, {'original_sender': event.get('sender', 'nougen-wake')})
        return {**result, 'woken': False, 'wake_requested': result.get('queue_accepted', False)}
