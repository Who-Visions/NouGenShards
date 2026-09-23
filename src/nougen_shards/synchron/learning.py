"""Learning loop: reward surfaced hits, nudge feature weights, stay deterministic.

Pure functions. ``recalibrate`` returns a new Config; nothing is mutated and the
caller decides whether to adopt it (a new Config has a new digest, so receipts
made under the old weights stay reproducible).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from .model import Config


def reward(created_artifact: bool = False, changed_decision: bool = False,
           triggered_research: bool = False, dismissed_as_noise: bool = False) -> float:
    return (1.0 * created_artifact + 0.7 * changed_decision
            + 0.4 * triggered_research - 0.5 * dismissed_as_noise)


def recalibrate(cfg: Config, features: Mapping[str, float], r: float,
                lr: float = 0.05, floor: float = 0.01) -> Config:
    """Move weights toward features present in rewarded hits (away when r < 0); sum stays 1."""
    w = {k: max(floor, v + lr * r * float(features.get(k, 0.0))) for k, v in cfg.weights}
    total = sum(w.values())
    return replace(cfg, weights=tuple((k, w[k] / total) for k, _ in cfg.weights))
