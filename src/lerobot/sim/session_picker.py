#!/usr/bin/env python

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import (
    BoardCorners,
    CURRENT_GRIPPER_REFERENCE_PROFILE,
    SIM_CAMERA_CALIBRATION_PROFILES,
    _board_corners_override,
    _load_json_object,
    _load_ranked_session_summary_payload,
    _resolve_summary_referenced_path,
    load_sim_camera_profile_overrides,
)


@dataclass(frozen=True)
class RankedSimCalibrationCandidate:
    """Operator-facing row from a ranked simulator calibration session."""

    summary_path: Path
    rank: int
    candidate_id: str
    rank_score: float | None
    total_penalty: float | None
    all_smokes_ok: bool
    smoke_failures: tuple[str, ...]
    candidate_path: Path
    candidate_artifact_dir: Path | None
    artifact_paths: dict[str, Path]
    base_profile: str
    board_corners_xy: BoardCorners
    reference_image_path: Path | None
    profile_overrides: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "candidate_id": self.candidate_id,
            "rank_score": self.rank_score,
            "total_penalty": self.total_penalty,
            "all_smokes_ok": self.all_smokes_ok,
            "smoke_failures": list(self.smoke_failures),
            "candidate_path": str(self.candidate_path),
            "candidate_artifact_dir": str(self.candidate_artifact_dir) if self.candidate_artifact_dir else None,
            "artifact_paths": {key: str(path) for key, path in self.artifact_paths.items()},
            "base_profile": self.base_profile,
            "board_corners_xy": [[float(x), float(y)] for x, y in self.board_corners_xy],
            "reference_image_path": str(self.reference_image_path) if self.reference_image_path else None,
            "profile_overrides": self.profile_overrides,
        }


@dataclass(frozen=True)
class RankedSimCalibrationSession:
    summary_path: Path
    candidates: tuple[RankedSimCalibrationCandidate, ...]

    def select(
        self,
        *,
        rank: int = 1,
        candidate_id: str | None = None,
    ) -> RankedSimCalibrationCandidate:
        if candidate_id is not None:
            wanted = str(candidate_id).strip()
            if not wanted:
                raise ValueError("sim calibration candidate id must be non-empty.")
            matches = [candidate for candidate in self.candidates if candidate.candidate_id == wanted]
            if not matches:
                known = ", ".join(candidate.candidate_id for candidate in self.candidates)
                raise ValueError(
                    f"Candidate id {wanted!r} was not found in ranked simulator calibration summary "
                    f"{self.summary_path}. Known candidate ids: {known or '(none)'}."
                )
            if len(matches) > 1:
                raise ValueError(
                    f"Candidate id {wanted!r} appears more than once in ranked simulator calibration summary "
                    f"{self.summary_path}."
                )
            return matches[0]

        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise ValueError(f"sim calibration rank must be a positive integer, got {rank!r}.")
        matches = [candidate for candidate in self.candidates if candidate.rank == rank]
        if not matches:
            available = ", ".join(str(candidate.rank) for candidate in self.candidates)
            raise ValueError(
                f"Rank {rank} was not found in ranked simulator calibration summary {self.summary_path}; "
                f"available ranks: {available or '(none)'}."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Rank {rank} appears more than once in ranked simulator calibration summary {self.summary_path}."
            )
        return matches[0]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "summary_path": str(self.summary_path),
            "candidate_count": len(self.candidates),
            "candidates": [candidate.to_jsonable() for candidate in self.candidates],
        }


def load_ranked_sim_calibration_session(summary_path: str | Path) -> RankedSimCalibrationSession:
    """Load ranked simulator calibration candidates for UI/listing use."""

    resolved_summary_path = Path(summary_path).expanduser().resolve()
    payload = _load_ranked_session_summary_payload(resolved_summary_path)
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        raise ValueError(f"Ranked simulator calibration summary {resolved_summary_path} must contain a non-empty ranking list.")

    candidate_payloads = _candidate_payloads_by_id(payload, summary_path=resolved_summary_path)
    rows = tuple(
        _candidate_from_ranking_entry(
            index=index,
            entry=entry,
            candidate_payloads=candidate_payloads,
            summary_path=resolved_summary_path,
        )
        for index, entry in enumerate(ranking, start=1)
    )
    return RankedSimCalibrationSession(summary_path=resolved_summary_path, candidates=rows)


def _candidate_payloads_by_id(payload: dict[str, Any], *, summary_path: Path) -> dict[str, dict[str, Any]]:
    candidates = payload.get("candidates")
    if candidates is None:
        return {}
    if not isinstance(candidates, list):
        raise ValueError(f"candidates in ranked simulator calibration summary {summary_path} must be a list.")

    by_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] in ranked simulator calibration summary {summary_path} must be an object.")
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError(
                f"candidates[{index}] in ranked simulator calibration summary {summary_path} must include candidate_id."
            )
        if candidate_id in by_id:
            raise ValueError(
                f"Candidate id {candidate_id!r} appears more than once in candidates for ranked simulator "
                f"calibration summary {summary_path}."
            )
        by_id[candidate_id] = candidate
    return by_id


def _candidate_from_ranking_entry(
    *,
    index: int,
    entry: Any,
    candidate_payloads: dict[str, dict[str, Any]],
    summary_path: Path,
) -> RankedSimCalibrationCandidate:
    if not isinstance(entry, dict):
        raise ValueError(f"ranking[{index - 1}] in ranked simulator calibration summary {summary_path} must be an object.")

    candidate_id = entry.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError(f"ranking[{index - 1}] in ranked simulator calibration summary {summary_path} must include candidate_id.")

    rank = _positive_rank(entry.get("rank", index), source=f"ranking entry {candidate_id!r}", summary_path=summary_path)
    candidate_payload = candidate_payloads.get(candidate_id, {})
    candidate_path = _candidate_path(entry=entry, candidate_payload=candidate_payload, summary_path=summary_path)
    candidate_file_payload = _load_json_object(candidate_path, label="simulator camera profile candidate")
    profile_overrides = load_sim_camera_profile_overrides(candidate_path)
    base_profile = _base_profile(candidate_payload=candidate_payload, candidate_file_payload=candidate_file_payload, candidate_path=candidate_path)
    board_corners_xy = _board_corners(candidate_payload=candidate_payload, profile_overrides=profile_overrides, candidate_path=candidate_path)
    reference_image_path = _reference_image_path(
        candidate_payload=candidate_payload,
        candidate_file_payload=candidate_file_payload,
        profile_overrides=profile_overrides,
        base_profile=base_profile,
        candidate_path=candidate_path,
        summary_path=summary_path,
    )

    return RankedSimCalibrationCandidate(
        summary_path=summary_path,
        rank=rank,
        candidate_id=candidate_id,
        rank_score=_optional_float(entry.get("rank_score")),
        total_penalty=_optional_float(entry.get("total_penalty")),
        all_smokes_ok=bool(entry.get("all_smokes_ok")),
        smoke_failures=_smoke_failures(entry.get("smoke_failures"), candidate_id=candidate_id, summary_path=summary_path),
        candidate_path=candidate_path,
        candidate_artifact_dir=_optional_summary_path(
            entry.get("candidate_artifact_dir") or candidate_payload.get("candidate_artifact_dir"),
            summary_path=summary_path,
        ),
        artifact_paths=_artifact_paths(entry=entry, candidate_payload=candidate_payload, summary_path=summary_path),
        base_profile=base_profile,
        board_corners_xy=board_corners_xy,
        reference_image_path=reference_image_path,
        profile_overrides=profile_overrides,
    )


def _candidate_path(*, entry: dict[str, Any], candidate_payload: dict[str, Any], summary_path: Path) -> Path:
    raw_candidate_path = entry.get("candidate_path") or candidate_payload.get("candidate_path")
    artifact_paths = entry.get("artifact_paths")
    if not raw_candidate_path and isinstance(artifact_paths, dict):
        raw_candidate_path = artifact_paths.get("candidate_path")
    if not isinstance(raw_candidate_path, str) or not raw_candidate_path.strip():
        raise ValueError(
            f"Ranking entry {entry.get('candidate_id')!r} in {summary_path} must include candidate_path."
        )
    candidate_path = _resolve_summary_referenced_path(raw_candidate_path, summary_path=summary_path)
    if not candidate_path.is_file():
        raise ValueError(
            f"Candidate {entry.get('candidate_id')!r} from ranked simulator calibration summary "
            f"{summary_path} does not exist: {candidate_path}"
        )
    return candidate_path


def _base_profile(
    *,
    candidate_payload: dict[str, Any],
    candidate_file_payload: dict[str, Any],
    candidate_path: Path,
) -> str:
    base_profile = str(
        candidate_payload.get("base_profile")
        or candidate_file_payload.get("base_profile")
        or CURRENT_GRIPPER_REFERENCE_PROFILE
    )
    if base_profile not in SIM_CAMERA_CALIBRATION_PROFILES:
        known_profiles = ", ".join(sorted(SIM_CAMERA_CALIBRATION_PROFILES))
        raise ValueError(f"Unknown base profile {base_profile!r} in selected candidate {candidate_path}. Known profiles: {known_profiles}")
    return base_profile


def _board_corners(
    *,
    candidate_payload: dict[str, Any],
    profile_overrides: dict[str, Any],
    candidate_path: Path,
) -> BoardCorners:
    raw_corners = candidate_payload.get("board_corners_xy") or profile_overrides.get("board_corners_xy")
    if raw_corners is None:
        raise ValueError(f"Candidate {candidate_path} must include board_corners_xy for ranked session listing.")
    return _board_corners_override(raw_corners, source=candidate_path)


def _reference_image_path(
    *,
    candidate_payload: dict[str, Any],
    candidate_file_payload: dict[str, Any],
    profile_overrides: dict[str, Any],
    base_profile: str,
    candidate_path: Path,
    summary_path: Path,
) -> Path | None:
    raw_path = (
        candidate_payload.get("reference_image_path")
        or candidate_file_payload.get("reference_image_path")
        or profile_overrides.get("reference_image_path")
        or SIM_CAMERA_CALIBRATION_PROFILES[base_profile].get("reference_image_path")
    )
    if not isinstance(raw_path, (str, Path)):
        return None
    return _resolve_reference_path(str(raw_path), candidate_path=candidate_path, summary_path=summary_path)


def _resolve_reference_path(value: str, *, candidate_path: Path, summary_path: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    candidates = [
        summary_path.parent / path,
        Path.cwd() / path,
        candidate_path.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _artifact_paths(
    *,
    entry: dict[str, Any],
    candidate_payload: dict[str, Any],
    summary_path: Path,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for source in (entry.get("artifact_paths"), candidate_payload.get("artifact_paths")):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                paths[key] = _resolve_summary_referenced_path(value, summary_path=summary_path)
    for key in ("candidate_path", "candidate_artifact_dir"):
        value = entry.get(key) or candidate_payload.get(key)
        if isinstance(value, str) and value.strip():
            paths.setdefault(key, _resolve_summary_referenced_path(value, summary_path=summary_path))
    return paths


def _optional_summary_path(value: Any, *, summary_path: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _resolve_summary_referenced_path(value, summary_path=summary_path)


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def _positive_rank(value: Any, *, source: str, summary_path: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"rank for {source} in ranked simulator calibration summary {summary_path} must be a positive integer.")
    return int(value)


def _smoke_failures(value: Any, *, candidate_id: str, summary_path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"smoke_failures for candidate {candidate_id!r} in {summary_path} must be a list.")
    return tuple(str(item) for item in value)
