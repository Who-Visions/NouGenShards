"""Remotion Video Engineering helper and parameter pipeline for NouGen.

Provides composition schema validation, timeline calculation utilities,
and headless render command orchestration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class CompositionSpec:
    id: str
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration_in_frames: int = 300
    props: Dict[str, Any] = None

    @property
    def duration_in_seconds(self) -> float:
        return self.duration_in_frames / self.fps

    def to_remotion_cli_args(self, entrypoint: str = "src/index.ts", out_path: str = "out/output.mp4") -> List[str]:
        return [
            "npx",
            "remotion",
            "render",
            entrypoint,
            self.id,
            out_path,
            f"--props={self.props or {}}",
        ]


class RemotionTimelineCalculator:
    """Calculates frame-perfect timing for video sequences and subtitle alignment."""

    @staticmethod
    def seconds_to_frame(seconds: float, fps: int = 30) -> int:
        return int(round(seconds * fps))

    @staticmethod
    def frame_to_seconds(frame: int, fps: int = 30) -> float:
        return frame / fps

    @staticmethod
    def calculate_spring_steps(frame: int, fps: int = 30, damping: float = 10.0, stiffness: float = 100.0) -> float:
        """Simplified analytical approximation of spring progress in [0, 1]."""
        if frame <= 0:
            return 0.0
        t = frame / fps
        omega = math.sqrt(max(0.1, stiffness))
        zeta = damping / (2.0 * omega)
        if zeta < 1.0:
            decay = math.exp(-zeta * omega * t)
            omega_d = omega * math.sqrt(1.0 - zeta * zeta)
            val = 1.0 - decay * math.cos(omega_d * t)
            return max(0.0, min(1.5, val))
        decay = math.exp(-omega * t)
        return max(0.0, min(1.0, 1.0 - decay))

    @staticmethod
    def align_transcript_words(words: List[Dict[str, Any]], fps: int = 30) -> List[Dict[str, Any]]:
        """Maps timestamped words to exact timeline frames."""
        aligned = []
        for w in words:
            start_frame = int(round(float(w.get("start", 0.0)) * fps))
            end_frame = int(round(float(w.get("end", 0.0)) * fps))
            aligned.append({
                "word": w.get("word", ""),
                "start_frame": start_frame,
                "end_frame": max(start_frame + 1, end_frame),
                "duration_frames": max(1, end_frame - start_frame),
            })
        return aligned
