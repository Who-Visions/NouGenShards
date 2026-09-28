"""Universal Deterministic NouGenVeo Prompt Compiler & Background Parity Engine.

Implements relay directives:
- 20260926T061631Z: Universal deterministic Veo prompt compiler (runtime, FPS, frame math, continuity).
- 20260926T071416Z: Universal background parity engine locking scene geometry, parallax, lighting, horizon, and avoiding background replacement.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

DEFAULT_FPS = 24

@dataclass
class SceneEnvironmentLock:
    horizon_ratio: float = 0.38  # Upper third line
    vanishing_point: tuple[float, float] = (0.5, 0.38)
    lighting_key: str = "low-angle amber backlight with cool ambient cyan fill"
    color_palette: List[str] = field(default_factory=lambda: ["#0a0e14", "#d97706", "#06b6d4"])
    weather_condition: str = "thin atmospheric dust, dry caldera haze"
    geometry_anchors: List[str] = field(default_factory=lambda: [
        "pyramid caldera rim left-to-right",
        "central tear apex rift at center-depth"
    ])
    locked_text_elements: List[str] = field(default_factory=list)

@dataclass
class VeoShotSpecification:
    duration_seconds: float
    fps: int = DEFAULT_FPS
    action_intent: str = ""
    camera_motion: str = "slow lateral dolly with parallax preservation"
    dof_setting: str = "f/2.8 shallow focus tracking foreground subject"
    environment: SceneEnvironmentLock = field(default_factory=SceneEnvironmentLock)
    continuity_prior_state: Optional[str] = None

    @property
    def total_frames(self) -> int:
        return int(math.ceil(self.duration_seconds * self.fps))

def compile_veo_prompt(spec: VeoShotSpecification) -> Dict[str, Any]:
    """Compiles a deterministic, production-ready prompt and metadata block for Veo."""
    continuity_prefix = (
        f"[CONTINUITY RESTRICTION]: Strict seamless continuation from prior frame: {spec.continuity_prior_state}. "
        if spec.continuity_prior_state else ""
    )

    env = spec.environment
    anchors_str = ", ".join(env.geometry_anchors)
    
    background_lock_clause = (
        f"[BACKGROUND PARITY LOCK]: Do NOT regenerate background geometry or shift horizon. "
        f"Horizon fixed at {int(env.horizon_ratio*100)}% frame height. "
        f"Geometry anchors locked: {anchors_str}. "
        f"Lighting locked: {env.lighting_key}. "
        f"Atmosphere locked: {env.weather_condition}. "
        f"Camera move: {spec.camera_motion}; compute plausible parallax without texture popping or object spawning."
    )

    full_compiled_prompt = (
        f"{continuity_prefix}"
        f"[SCENE ACTION]: {spec.action_intent.strip()} "
        f"[CINEMATOGRAPHY]: {spec.camera_motion}, {spec.dof_setting}, 24fps film cadence, 4K resolution. "
        f"{background_lock_clause}"
    )

    return {
        "prompt": full_compiled_prompt,
        "timing": {
            "duration_seconds": spec.duration_seconds,
            "fps": spec.fps,
            "total_frames": spec.total_frames
        },
        "parity_rules_enforced": [
            "zero_horizon_drift",
            "no_background_regeneration",
            "geometry_anchor_lock",
            "deterministic_parallax_dolly"
        ]
    }
