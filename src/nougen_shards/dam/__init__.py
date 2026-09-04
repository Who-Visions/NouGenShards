"""Temporal shard capture dam — durable spool between front door and reservoirs.

Vocabulary (relay leg 20260904T040803Z):
  reservoir  primary shard databases; the only source of truth
  dam        encrypted durable write spool; holds INTENT, never truth
  spillway   replay worker that releases queued events back to the reservoir
  gate       policy deciding when a failed write is diverted into the dam
  gauge      backpressure metrics (queued, oldest age, bytes)
  silt       quarantine for tampered or unidentifiable events
"""
from .dam import Dam
from .gate import Decision, classify
from .spillway import Spillway
from .preflight import Preflight, PreflightFailure
from .store import DamStore, HFDamStore, LocalDamStore

__all__ = ["Dam", "Preflight", "PreflightFailure", "Spillway", "DamStore", "LocalDamStore", "HFDamStore",
           "classify", "Decision"]
