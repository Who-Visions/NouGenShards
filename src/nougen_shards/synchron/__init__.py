"""SYNCHRON -- NouGen Serendipity Engine, deterministic core.

Detects unexpected convergence between independently sourced events and
emits sealed, reproducible receipts. Evidence-aware, not superstition:

  * independence gate rejects coincidences caused by the user's own search;
  * rarity and every penalty come from a supplied base-rate SNAPSHOT, never
    from vibes -- an empty snapshot means "unknown", which scores as common;
  * anti-apophenia penalties run on every candidate before it is classified.

Pure functions only. No clock reads, no network, no model calls: the caller
passes the evidence snapshot (including ``as_of_ms``), so the same snapshot +
config always yields byte-identical receipts.
"""
from .model import BaseRates, Config, Event, Snapshot, Window
from .score import classify, features, score_pair
from .receipt import build_receipt, seal, verify
from .engine import detect
from .learning import recalibrate, reward

__all__ = ["BaseRates", "Config", "Event", "Snapshot", "Window", "classify", "features",
           "score_pair", "build_receipt", "seal", "verify", "detect", "recalibrate", "reward"]
