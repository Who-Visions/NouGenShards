"""Typed, deterministic contract for NouGenMorph AMV render plans.

This module is deliberately renderer-independent. Remotion and FFmpeg adapters
consume the same validated manifest; neither renderer is allowed to choose
sources or editorial decisions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Literal


RightsStatus = Literal["authorized", "review", "blocked"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_project_uri(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
        or ".." in path.parts
    ):
        raise ValueError(f"{label} must be a safe project-relative path")


def round_ratio_ties_even(numerator: int, denominator: int) -> int:
    """Round an exact rational to nearest integer, resolving ties to even."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(numerator), denominator)
    doubled_remainder = 2 * remainder
    if doubled_remainder > denominator or (
        doubled_remainder == denominator and quotient % 2 == 1
    ):
        quotient += 1
    return sign * quotient


def impact_aligned_output_start_frame(
    *,
    anchor_sample_index: int,
    audio_sample_rate_hz: int,
    output_fps_num: int,
    output_fps_den: int,
    source_fps_num: int,
    source_fps_den: int,
    source_in_frame: int,
    impact_source_frame: int,
) -> int:
    """Place a source impact frame on an audio anchor using integer math.

    Returns the output start frame. It may be negative when the impact occurs
    too late in its source clip; the manifest validator will reject that edit.
    """
    if anchor_sample_index < 0 or source_in_frame < 0:
        raise ValueError("sample and source frame positions must be non-negative")
    if audio_sample_rate_hz <= 0 or output_fps_num <= 0 or output_fps_den <= 0:
        raise ValueError("audio sample rate and output frame rate must be positive")
    if source_fps_num <= 0 or source_fps_den <= 0:
        raise ValueError("source frame rate must be a positive rational")
    if impact_source_frame < source_in_frame:
        raise ValueError("impact_source_frame must be at or after source_in_frame")

    anchor_output_frame = round_ratio_ties_even(
        anchor_sample_index * output_fps_num,
        audio_sample_rate_hz * output_fps_den,
    )
    impact_output_offset = round_ratio_ties_even(
        (impact_source_frame - source_in_frame) * source_fps_den * output_fps_num,
        source_fps_num * output_fps_den,
    )
    return anchor_output_frame - impact_output_offset


def source_duration_to_output_frames(
    source_frame_count: int,
    source_fps_num: int,
    source_fps_den: int,
    output_fps_num: int,
    output_fps_den: int,
) -> int:
    """Convert a source-frame duration to output frames with ties-to-even."""
    if source_frame_count <= 0:
        raise ValueError("source_frame_count must be positive")
    if min(source_fps_num, source_fps_den, output_fps_num, output_fps_den) <= 0:
        raise ValueError("source and output frame rates must be positive rationals")
    return round_ratio_ties_even(
        source_frame_count * source_fps_den * output_fps_num,
        source_fps_num * output_fps_den,
    )


@dataclass(frozen=True)
class SourceAsset:
    """A project-local media file with content identity and rights evidence."""

    asset_id: str
    sha256: str
    project_uri: str
    fps_num: int
    fps_den: int
    duration_frames: int
    rights_status: RightsStatus
    rights_evidence_ref: str | None

    def __post_init__(self) -> None:
        if not self.asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character digest")
        _validate_project_uri(self.project_uri, "project_uri")
        if self.fps_num <= 0 or self.fps_den <= 0 or self.duration_frames <= 0:
            raise ValueError("source FPS and duration must be positive")
        if self.rights_status == "authorized" and (not self.rights_evidence_ref or not self.rights_evidence_ref.strip()):
            raise ValueError("authorized assets require non-empty rights_evidence_ref")
        if self.rights_status not in ("authorized", "review", "blocked"):
            raise ValueError("unsupported rights_status")


@dataclass(frozen=True)
class EditDecision:
    """A source interval placed on the integer-frame output timeline."""

    asset_id: str
    source_sha256: str
    shot_id: str
    source_in_frame: int
    source_out_frame: int
    output_start_frame: int
    output_end_frame: int
    rationale_evidence_refs: tuple[str, ...] = ()
    anchor_sample_index: int | None = None
    impact_source_frame: int | None = None

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase 64-character digest")
        if not self.asset_id.strip() or not self.shot_id.strip():
            raise ValueError("asset_id and shot_id must be non-empty")
        if not self.rationale_evidence_refs or any(not ref.strip() for ref in self.rationale_evidence_refs):
            raise ValueError("each edit requires non-empty rationale evidence references")
        if (self.anchor_sample_index is None) != (self.impact_source_frame is None):
            raise ValueError("anchor_sample_index and impact_source_frame must be set together")
        if self.anchor_sample_index is not None and self.anchor_sample_index < 0:
            raise ValueError("anchor_sample_index must be non-negative")
        if self.source_in_frame < 0 or self.output_start_frame < 0:
            raise ValueError("frame positions must be non-negative")
        if self.source_out_frame <= self.source_in_frame:
            raise ValueError("source frame range must be non-empty and half-open")
        if self.output_end_frame <= self.output_start_frame:
            raise ValueError("output frame range must be non-empty and half-open")


@dataclass(frozen=True)
class AMVManifest:
    """Canonical renderer input; all time positions use integer frames."""

    project_id: str
    audio_sha256: str
    audio_project_uri: str
    audio_sample_rate_hz: int
    output_fps_num: int
    output_fps_den: int
    output_width: int
    output_height: int
    duration_frames: int
    config_sha256: str
    assets: tuple[SourceAsset, ...]
    edits: tuple[EditDecision, ...]
    schema_version: str = "nougenmorph-amv/0.1"
    renderer: str = "renderer-neutral"
    renderer_config: dict[str, str | int | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id must be non-empty")
        if not _SHA256_RE.fullmatch(self.audio_sha256):
            raise ValueError("audio_sha256 must be a lowercase 64-character digest")
        if not _SHA256_RE.fullmatch(self.config_sha256):
            raise ValueError("config_sha256 must be a lowercase 64-character digest")
        if self.output_fps_num <= 0 or self.output_fps_den <= 0:
            raise ValueError("output frame rate must be a positive rational")
        if self.output_width <= 0 or self.output_height <= 0 or self.duration_frames <= 0:
            raise ValueError("output dimensions and duration must be positive")
        _validate_project_uri(self.audio_project_uri, "audio_project_uri")
        if self.audio_sample_rate_hz <= 0:
            raise ValueError("audio_sample_rate_hz must be positive")
        if len({asset.asset_id for asset in self.assets}) != len(self.assets):
            raise ValueError("asset_id values must be unique")
        assets = {asset.asset_id: asset for asset in self.assets}
        previous_start = -1
        for edit in self.edits:
            asset = assets.get(edit.asset_id)
            if asset is None:
                raise ValueError(f"edit references unknown asset_id: {edit.asset_id}")
            if edit.source_sha256 != asset.sha256:
                raise ValueError(f"edit source hash does not match asset: {edit.asset_id}")
            if edit.source_out_frame > asset.duration_frames:
                raise ValueError(f"edit exceeds source duration: {edit.asset_id}")
            expected_output_length = source_duration_to_output_frames(
                edit.source_out_frame - edit.source_in_frame,
                asset.fps_num,
                asset.fps_den,
                self.output_fps_num,
                self.output_fps_den,
            )
            if edit.output_end_frame - edit.output_start_frame != expected_output_length:
                raise ValueError("output duration does not match 1x source duration at output FPS")
            if edit.impact_source_frame is not None and not (
                edit.source_in_frame <= edit.impact_source_frame < edit.source_out_frame
            ):
                raise ValueError("impact_source_frame must lie inside the source interval")
            if edit.anchor_sample_index is not None and edit.impact_source_frame is not None:
                expected_start = impact_aligned_output_start_frame(
                    anchor_sample_index=edit.anchor_sample_index,
                    audio_sample_rate_hz=self.audio_sample_rate_hz,
                    output_fps_num=self.output_fps_num,
                    output_fps_den=self.output_fps_den,
                    source_fps_num=asset.fps_num,
                    source_fps_den=asset.fps_den,
                    source_in_frame=edit.source_in_frame,
                    impact_source_frame=edit.impact_source_frame,
                )
                if edit.output_start_frame != expected_start:
                    raise ValueError("output start does not align impact frame to anchor sample")
            if asset.rights_status != "authorized":
                raise ValueError(f"asset is not authorized for rendering: {edit.asset_id}")
            if edit.output_end_frame > self.duration_frames:
                raise ValueError("edit exceeds manifest duration")
            if edit.output_start_frame < previous_start:
                raise ValueError("edits must be ordered by output_start_frame")
            previous_start = edit.output_start_frame

    def to_canonical_json(self) -> str:
        """Serialize with stable key ordering and no floating-point time values."""
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def manifest_sha256(self) -> str:
        """Return the content hash of the canonical manifest representation."""
        return hashlib.sha256(self.to_canonical_json().encode("utf-8")).hexdigest()
