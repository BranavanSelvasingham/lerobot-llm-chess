#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "reference_capture_manifest"
SCHEMA = "lerobot.sim.reference_capture_manifest_check.v1"
MANIFEST_SCHEMA = "lerobot.sim.reference_capture_manifest.v1"
OUTPUT_JSON_NAME = "reference_capture_manifest_check.json"
OUTPUT_CSV_NAME = "reference_capture_manifest_checklist.csv"
OUTPUT_README_NAME = "README.md"

IMAGE_EXTENSIONS = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"})
VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"})
SIDECAR_EXTENSIONS = frozenset({".csv", ".json", ".toml", ".yaml", ".yml"})

DEPTH_CAPTURE_KEYS = (
    "depth_reference_captures",
    "depth_reference_capture",
    "depth_captures",
    "depth_references",
    "depth_reference",
)
PICK_PLACE_CAPTURE_KEYS = (
    "pick_place_video_captures",
    "pick_place_video_capture",
    "pick_place_videos",
    "pick_place_video",
    "pick_place_captures",
)
MEDIA_LIST_KEYS = ("media", "captures", "reference_media")
MEDIA_PATH_KEYS = (
    "media_path",
    "relative_path",
    "path",
    "file_path",
    "depth_media_path",
    "depth_image_path",
    "rgb_media_path",
    "rgb_image_path",
    "video_path",
    "pick_place_video_path",
)
SIDECAR_PATH_KEYS = (
    "sidecar_path",
    "sidecar",
    "depth_sidecar_path",
    "depth_reference_sidecar_path",
    "depth_reference_path",
    "real_depth_path",
    "calibration_data_path",
    "calibration_sidecar_path",
    "capture_metadata_path",
    "metadata_path",
    "camera_intrinsics_path",
    "real_intrinsics_path",
    "intrinsics_path",
    "camera_extrinsics_path",
    "real_extrinsics_path",
    "extrinsics_path",
    "board_pose_path",
    "real_board_pose_path",
    "board_corner_detections_path",
    "distance_measurements_path",
)
PATH_MAP_KEYS = ("media_paths", "sidecar_paths", "calibration_data_paths", "capture_metadata_paths")
PROVENANCE_KEYS = (
    "capture_operator",
    "operator",
    "capture_date",
    "capture_date_utc",
    "captured_at",
    "source",
    "source_device",
    "camera_id",
)
REVIEW_KEYS = (
    "reviewed_by",
    "review_date",
    "review_date_utc",
    "review_status",
    "review_notes",
    "approved_by",
)
BOARD_POSE_KEYS = (
    "board_camera_pose_notes",
    "board_pose_notes",
    "camera_pose_notes",
    "board_pose",
    "camera_pose",
    "board_to_camera",
    "camera_to_board",
    "board_corner_notes",
)
CAMERA_METADATA_KEYS = (
    "camera_intrinsics",
    "camera_intrinsics_or_capture_metadata",
    "capture_metadata",
    "camera_metadata",
    "intrinsics",
    "camera_matrix_px",
    "image_size_px",
)
DEPTH_TARGET_KEYS = (
    "measured_depth_targets",
    "measured_distance_targets",
    "metric_references",
    "depth_targets",
    "distance_measurements",
    "measured_distance_m",
    "measured_depth_m",
    "depth_m",
    "distance_m",
    "reference_distance_m",
)
GRIPPER_VISIBILITY_KEYS = (
    "gripper_arm_visibility_notes",
    "gripper_visibility_notes",
    "gripper_visibility",
    "arm_visibility",
    "gripper_notes",
)

REQUIRED_FIELD_ROWS = (
    (
        "manifest",
        "schema",
        "Manifest schema marker, preferably lerobot.sim.reference_capture_manifest.v1.",
    ),
    (
        "manifest",
        "media_assets_copied_into_repo=false",
        "Explicit local-only/no-copy policy; the checker never copies media assets.",
    ),
    (
        "manifest",
        "provenance",
        "Capture operator/date/source or equivalent top-level provenance fields.",
    ),
    (
        "manifest",
        "review",
        "Reviewer/date/status or equivalent top-level review fields.",
    ),
    (
        "depth_reference_captures[]",
        "capture_id",
        "Stable identifier for each real depth-reference capture.",
    ),
    (
        "depth_reference_captures[]",
        "media_path",
        "Local image/depth media path; relative paths resolve against the manifest directory.",
    ),
    (
        "depth_reference_captures[]",
        "depth_sidecar_path",
        "Local JSON/YAML/CSV sidecar path for real depth or distance measurements.",
    ),
    (
        "depth_reference_captures[]",
        "measured_depth_targets",
        "Measured distance/depth targets, metric_references, or distance_m/depth_m fields.",
    ),
    (
        "depth_reference_captures[]",
        "board_camera_pose_notes",
        "Board/camera pose notes or board/camera transform placeholders.",
    ),
    (
        "depth_reference_captures[]",
        "camera_intrinsics_or_capture_metadata",
        "Camera intrinsics, capture metadata, or paths to those sidecars.",
    ),
    (
        "pick_place_video_captures[]",
        "capture_id",
        "Stable identifier for each real pick/place video capture.",
    ),
    (
        "pick_place_video_captures[]",
        "media_path",
        "Local video path; relative paths resolve against the manifest directory.",
    ),
    (
        "pick_place_video_captures[]",
        "gripper_arm_visibility_notes",
        "Notes on fingers, wrist, arm, pickup, release, and occlusion visibility.",
    ),
    (
        "pick_place_video_captures[]",
        "board_camera_pose_notes",
        "Board/camera pose notes or transform placeholders for the video capture.",
    ),
    (
        "pick_place_video_captures[]",
        "capture_metadata_path",
        "Sidecar path for frame timing, camera metadata, or reviewed event markers.",
    ),
)

MISSING_CAPTURE_DIAGNOSTICS = (
    "missing_depth_reference",
    "missing_pick_place_video",
    "missing_depth_sidecar",
    "missing_provenance_review",
    "media_assets_copied_into_repo=false",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check a local-only real-reference capture manifest for the depth and "
            "pick/place-video inputs needed before calibration-grade SimCamera tuning."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest-path", type=Path, default=None)
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def object_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in ensure_list(value) if isinstance(item, dict)]


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def path_kind(path_value: str) -> str:
    suffix = Path(path_value).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in SIDECAR_EXTENSIONS:
        return "sidecar"
    return "unknown"


def resolve_manifest_path(value: str, manifest_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (manifest_dir / path).resolve()


def repo_relative(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def path_check(
    *,
    value: str,
    source: str,
    category: str,
    manifest_dir: Path,
) -> dict[str, Any]:
    resolved = resolve_manifest_path(value, manifest_dir)
    return {
        "source": source,
        "category": category,
        "declared_path": value,
        "resolved_path": str(resolved),
        "repo_relative_path": repo_relative(resolved),
        "path_kind": path_kind(value),
        "exists": resolved.exists(),
        "is_file": resolved.is_file(),
    }


def collect_path_values(entry: dict[str, Any], *, category: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    path_keys = MEDIA_PATH_KEYS if category == "media" else SIDECAR_PATH_KEYS
    for key in path_keys:
        value = entry.get(key)
        for item in string_list(value):
            rows.append((key, item, category))
    for map_key in PATH_MAP_KEYS:
        value = entry.get(map_key)
        if not isinstance(value, dict):
            continue
        for nested_key in sorted(value):
            nested_value = value[nested_key]
            nested_category = "media" if map_key == "media_paths" else "sidecar"
            if category != nested_category:
                continue
            for item in string_list(nested_value):
                rows.append((f"{map_key}.{nested_key}", item, category))
    return rows


def collect_entry_paths(
    entry: dict[str, Any],
    *,
    entry_source: str,
    manifest_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    media_checks = [
        path_check(value=value, source=f"{entry_source}.{key}", category="media", manifest_dir=manifest_dir)
        for key, value, _category in collect_path_values(entry, category="media")
    ]
    sidecar_checks = [
        path_check(value=value, source=f"{entry_source}.{key}", category="sidecar", manifest_dir=manifest_dir)
        for key, value, _category in collect_path_values(entry, category="sidecar")
    ]

    # Existing reference-media manifests often use depth_reference_path for a JSON sidecar.
    for key in ("depth_reference_path", "real_depth_path"):
        value = entry.get(key)
        for item in string_list(value):
            kind = path_kind(item)
            if kind in {"image", "video"}:
                media_checks.append(
                    path_check(
                        value=item,
                        source=f"{entry_source}.{key}",
                        category="media",
                        manifest_dir=manifest_dir,
                    )
                )
            elif not any(row["source"] == f"{entry_source}.{key}" for row in sidecar_checks):
                sidecar_checks.append(
                    path_check(
                        value=item,
                        source=f"{entry_source}.{key}",
                        category="sidecar",
                        manifest_dir=manifest_dir,
                    )
                )
    return dedupe_path_checks(media_checks), dedupe_path_checks(sidecar_checks)


def dedupe_path_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for row in rows:
        key = (str(row["source"]), str(row["declared_path"]), str(row["category"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def has_any_field(entry: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(is_nonempty(entry.get(key)) for key in keys)


def has_provenance(payload: dict[str, Any]) -> bool:
    provenance = payload.get("provenance")
    return (isinstance(provenance, dict) and bool(provenance)) or has_any_field(payload, PROVENANCE_KEYS)


def has_review(payload: dict[str, Any]) -> bool:
    review = payload.get("review")
    return (isinstance(review, dict) and bool(review)) or has_any_field(payload, REVIEW_KEYS)


def has_depth_targets(entry: dict[str, Any]) -> bool:
    for key in DEPTH_TARGET_KEYS:
        value = entry.get(key)
        if is_nonempty(value):
            return True
    return False


def has_camera_metadata(entry: dict[str, Any]) -> bool:
    return has_any_field(entry, CAMERA_METADATA_KEYS) or any(
        is_nonempty(entry.get(key)) for key in ("camera_intrinsics_path", "real_intrinsics_path", "capture_metadata_path")
    )


def has_board_pose_notes(entry: dict[str, Any]) -> bool:
    return has_any_field(entry, BOARD_POSE_KEYS) or any(
        is_nonempty(entry.get(key)) for key in ("board_pose_path", "real_board_pose_path", "board_corner_detections_path")
    )


def has_gripper_visibility_notes(entry: dict[str, Any]) -> bool:
    return has_any_field(entry, GRIPPER_VISIBILITY_KEYS)


def entry_id(entry: dict[str, Any], *, fallback: str) -> str:
    for key in ("capture_id", "id", "name"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def capture_text(entry: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key, value in entry.items():
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, list):
            chunks.extend(item for item in value if isinstance(item, str))
    return " ".join(chunks).lower()


def media_entry_matches_depth(entry: dict[str, Any]) -> bool:
    targets = set(string_list(entry.get("calibration_targets")))
    tags = set(string_list(entry.get("declared_tags"))) | set(string_list(entry.get("reference_tags")))
    text = capture_text(entry)
    return bool(
        targets & {"depth", "depth_reference", "depth_distance", "workspace_geometry"}
        or tags & {"depth", "depth_reference", "depth_distance", "metric_depth"}
        or "depth" in text
        or "distance" in text
    )


def media_entry_matches_pick_place(entry: dict[str, Any]) -> bool:
    text = capture_text(entry)
    media_type = str(entry.get("media_type") or "").lower()
    has_video = media_type == "video" or any(
        path_kind(path) == "video"
        for _key, path, _category in collect_path_values(entry, category="media")
    )
    return has_video and any(token in text for token in ("pick", "place", "grasp", "release", "approach", "retreat"))


def extract_capture_entries(manifest: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in keys:
        entries.extend(object_list(manifest.get(key)))
    return entries


def extract_media_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in MEDIA_LIST_KEYS:
        entries.extend(object_list(manifest.get(key)))
    return entries


def local_only_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    copied_value = manifest.get("media_assets_copied_into_repo")
    copy_requested = manifest.get("copy_media_into_repo")
    policy = manifest.get("local_only_no_copy_policy")
    if isinstance(policy, dict):
        policy_present = bool(policy)
        policy_enabled = policy.get("enabled")
        acknowledged = policy.get("operator_acknowledged", policy.get("acknowledged"))
    else:
        policy_present = policy is not None
        policy_enabled = policy
        acknowledged = policy
    policy_ok = (
        copied_value is False
        and copy_requested is not True
        and bool(policy_present)
        and policy_enabled is not False
        and acknowledged is not False
    )
    return {
        "media_assets_copied_into_repo": False,
        "manifest_declares_media_assets_copied_into_repo": copied_value,
        "manifest_declares_copy_media_into_repo": copy_requested,
        "local_only_no_copy_policy_present": bool(policy_present),
        "local_only_no_copy_policy_enabled": policy_enabled,
        "local_only_no_copy_policy_acknowledged": acknowledged,
        "ok": policy_ok,
    }


def normalize_capture(
    *,
    entry: dict[str, Any],
    kind: str,
    index: int,
    manifest_dir: Path,
    inherited_provenance: bool,
    inherited_review: bool,
) -> dict[str, Any]:
    fallback = f"{kind}_{index}"
    source = f"{kind}[{index}]"
    media_checks, sidecar_checks = collect_entry_paths(entry, entry_source=source, manifest_dir=manifest_dir)
    capture_provenance = has_provenance(entry) or inherited_provenance
    capture_review = has_review(entry) or inherited_review
    media_exists = bool(media_checks) and all(bool(row["exists"] and row["is_file"]) for row in media_checks)
    sidecar_exists = bool(sidecar_checks) and all(bool(row["exists"] and row["is_file"]) for row in sidecar_checks)
    required_checks = {
        "capture_id": is_nonempty(entry.get("capture_id") or entry.get("id")),
        "media_path": bool(media_checks),
        "media_file_exists": media_exists,
        "board_camera_pose_notes": has_board_pose_notes(entry),
        "camera_intrinsics_or_capture_metadata": has_camera_metadata(entry),
        "provenance": capture_provenance,
        "review": capture_review,
    }
    if kind == "depth_reference_captures":
        required_checks["sidecar_path"] = bool(sidecar_checks)
        required_checks["sidecar_file_exists"] = sidecar_exists
        required_checks["measured_depth_targets"] = has_depth_targets(entry)
    if kind == "pick_place_video_captures":
        required_checks["sidecar_path"] = bool(sidecar_checks)
        required_checks["sidecar_file_exists"] = sidecar_exists
        required_checks["gripper_arm_visibility_notes"] = has_gripper_visibility_notes(entry)
    missing_fields = sorted(key for key, present in required_checks.items() if not present)
    return {
        "kind": kind,
        "index": index,
        "capture_id": entry_id(entry, fallback=fallback),
        "required_checks": required_checks,
        "missing_fields": missing_fields,
        "media_path_checks": media_checks,
        "sidecar_path_checks": sidecar_checks,
        "provenance_present": capture_provenance,
        "review_present": capture_review,
        "board_camera_pose_notes_present": required_checks["board_camera_pose_notes"],
        "camera_intrinsics_or_capture_metadata_present": required_checks[
            "camera_intrinsics_or_capture_metadata"
        ],
        "gripper_arm_visibility_notes_present": required_checks.get("gripper_arm_visibility_notes"),
        "measured_depth_targets_present": required_checks.get("measured_depth_targets"),
    }


def build_required_field_rows(status: str) -> list[dict[str, Any]]:
    return [
        {
            "section": section,
            "entry_id": "",
            "field": field,
            "required": True,
            "status": status,
            "diagnostic": description,
            "value": "",
        }
        for section, field, description in REQUIRED_FIELD_ROWS
    ]


def field_rows_for_capture(capture: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    checks = capture.get("required_checks")
    checks = checks if isinstance(checks, dict) else {}
    for field in sorted(checks):
        present = bool(checks[field])
        rows.append(
            {
                "section": capture.get("kind"),
                "entry_id": capture.get("capture_id"),
                "field": field,
                "required": True,
                "status": "present" if present else "missing",
                "diagnostic": "" if present else f"missing_{field}",
                "value": str(present).lower(),
            }
        )
    for path_row in capture.get("media_path_checks") or []:
        if not isinstance(path_row, dict):
            continue
        rows.append(
            {
                "section": capture.get("kind"),
                "entry_id": capture.get("capture_id"),
                "field": path_row.get("source"),
                "required": True,
                "status": "exists" if path_row.get("exists") and path_row.get("is_file") else "missing",
                "diagnostic": "" if path_row.get("exists") and path_row.get("is_file") else "missing_media_path",
                "value": path_row.get("resolved_path"),
            }
        )
    for path_row in capture.get("sidecar_path_checks") or []:
        if not isinstance(path_row, dict):
            continue
        rows.append(
            {
                "section": capture.get("kind"),
                "entry_id": capture.get("capture_id"),
                "field": path_row.get("source"),
                "required": True,
                "status": "exists" if path_row.get("exists") and path_row.get("is_file") else "missing",
                "diagnostic": "" if path_row.get("exists") and path_row.get("is_file") else "missing_sidecar_path",
                "value": path_row.get("resolved_path"),
            }
        )
    return rows


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / OUTPUT_JSON_NAME
    csv_path = output_dir / OUTPUT_CSV_NAME
    readme_path = output_dir / OUTPUT_README_NAME
    required_rows = build_required_field_rows("not_supplied")

    base_summary: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": True,
        "summary_path": str(summary_path),
        "csv_path": str(csv_path),
        "readme_path": str(readme_path),
        "output_dir": str(output_dir),
        "repo_root": str(REPO_ROOT),
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "openai_skipped": True,
        "media_assets_copied_into_repo": False,
        "copied_media_paths": [],
        "ready_for_calibration_grade_simcamera_tuning": False,
        "required_capture_sidecar_fields": [
            {"section": section, "field": field, "description": description}
            for section, field, description in REQUIRED_FIELD_ROWS
        ],
    }

    if args.manifest_path is None:
        return {
            **base_summary,
            "status": "reference_capture_manifest_not_supplied",
            "manifest_path": None,
            "diagnostics": ["reference_capture_manifest_not_supplied", *MISSING_CAPTURE_DIAGNOSTICS],
            "field_rows": required_rows,
            "notes": [
                "No manifest was supplied; this run only emits the required fields and template guidance.",
                "Missing real depth-reference and pick/place-video captures remain open.",
            ],
        }

    manifest_path = args.manifest_path.expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()
    else:
        manifest_path = manifest_path.resolve()
    manifest_dir = manifest_path.parent

    if not manifest_path.exists():
        unavailable_rows = build_required_field_rows("manifest_unavailable")
        return {
            **base_summary,
            "status": "reference_capture_manifest_unavailable",
            "manifest_path": str(manifest_path),
            "diagnostics": ["reference_capture_manifest_unavailable", *MISSING_CAPTURE_DIAGNOSTICS],
            "field_rows": unavailable_rows,
            "notes": [
                "The requested manifest path does not exist.",
                "No media or sidecar files were copied or read beyond checking path availability.",
            ],
        }

    try:
        manifest = read_json_object(manifest_path)
    except Exception as exc:
        parse_rows = build_required_field_rows("manifest_parse_error")
        return {
            **base_summary,
            "ok": False,
            "status": "reference_capture_manifest_parse_error",
            "manifest_path": str(manifest_path),
            "diagnostics": ["reference_capture_manifest_parse_error", str(exc), *MISSING_CAPTURE_DIAGNOSTICS],
            "field_rows": parse_rows,
            "notes": [
                "The manifest could not be parsed as a JSON object.",
                "No media or sidecar files were copied.",
            ],
        }

    inherited_provenance = has_provenance(manifest)
    inherited_review = has_review(manifest)
    depth_entries = extract_capture_entries(manifest, DEPTH_CAPTURE_KEYS)
    pick_place_entries = extract_capture_entries(manifest, PICK_PLACE_CAPTURE_KEYS)
    for entry in extract_media_entries(manifest):
        if media_entry_matches_depth(entry):
            depth_entries.append(entry)
        if media_entry_matches_pick_place(entry):
            pick_place_entries.append(entry)

    depth_captures = [
        normalize_capture(
            entry=entry,
            kind="depth_reference_captures",
            index=index,
            manifest_dir=manifest_dir,
            inherited_provenance=inherited_provenance,
            inherited_review=inherited_review,
        )
        for index, entry in enumerate(depth_entries, start=1)
    ]
    pick_place_captures = [
        normalize_capture(
            entry=entry,
            kind="pick_place_video_captures",
            index=index,
            manifest_dir=manifest_dir,
            inherited_provenance=inherited_provenance,
            inherited_review=inherited_review,
        )
        for index, entry in enumerate(pick_place_entries, start=1)
    ]
    policy = local_only_policy(manifest)
    all_path_checks = [
        path_row
        for capture in [*depth_captures, *pick_place_captures]
        for key in ("media_path_checks", "sidecar_path_checks")
        for path_row in capture.get(key, [])
        if isinstance(path_row, dict)
    ]
    missing_paths = [
        path_row
        for path_row in all_path_checks
        if not bool(path_row.get("exists") and path_row.get("is_file"))
    ]
    depth_ready = bool(depth_captures) and all(not capture["missing_fields"] for capture in depth_captures)
    pick_place_ready = bool(pick_place_captures) and all(
        not capture["missing_fields"] for capture in pick_place_captures
    )
    all_captures = [*depth_captures, *pick_place_captures]
    provenance_review_ready = bool(all_captures) and all(
        bool(capture.get("provenance_present")) and bool(capture.get("review_present"))
        for capture in all_captures
    )
    depth_sidecar_ready = bool(depth_captures) and all(
        bool(capture["required_checks"].get("sidecar_path"))
        and bool(capture["required_checks"].get("sidecar_file_exists"))
        and bool(capture["required_checks"].get("measured_depth_targets"))
        for capture in depth_captures
    )
    ready = (
        depth_ready
        and pick_place_ready
        and provenance_review_ready
        and depth_sidecar_ready
        and not missing_paths
        and bool(policy["ok"])
    )

    diagnostics: list[str] = []
    if not depth_captures:
        diagnostics.append("missing_depth_reference")
    if not pick_place_captures:
        diagnostics.append("missing_pick_place_video")
    if not depth_sidecar_ready:
        diagnostics.append("missing_depth_sidecar")
    if not provenance_review_ready:
        diagnostics.append("missing_provenance_review")
    if missing_paths:
        diagnostics.append("missing_referenced_paths")
    if not policy["ok"]:
        diagnostics.append("missing_local_only_no_copy_policy")
    if policy["manifest_declares_media_assets_copied_into_repo"] is not False:
        diagnostics.append("media_assets_copied_into_repo=false")
    if policy["manifest_declares_copy_media_into_repo"] is True:
        diagnostics.append("copy_media_into_repo_requested")

    field_rows: list[dict[str, Any]] = [
        {
            "section": "manifest",
            "entry_id": "",
            "field": "schema",
            "required": True,
            "status": "present" if is_nonempty(manifest.get("schema")) else "missing",
            "diagnostic": "" if is_nonempty(manifest.get("schema")) else "missing_schema",
            "value": manifest.get("schema", ""),
        },
        {
            "section": "manifest",
            "entry_id": "",
            "field": "media_assets_copied_into_repo=false",
            "required": True,
            "status": "present" if policy["manifest_declares_media_assets_copied_into_repo"] is False else "missing",
            "diagnostic": ""
            if policy["manifest_declares_media_assets_copied_into_repo"] is False
            else "media_assets_copied_into_repo=false",
            "value": str(policy["manifest_declares_media_assets_copied_into_repo"]),
        },
        {
            "section": "manifest",
            "entry_id": "",
            "field": "local_only_no_copy_policy",
            "required": True,
            "status": "present" if policy["local_only_no_copy_policy_present"] else "missing",
            "diagnostic": "" if policy["local_only_no_copy_policy_present"] else "missing_local_only_no_copy_policy",
            "value": str(policy["local_only_no_copy_policy_present"]).lower(),
        },
        {
            "section": "manifest",
            "entry_id": "",
            "field": "provenance",
            "required": True,
            "status": "present" if inherited_provenance else "missing",
            "diagnostic": "" if inherited_provenance else "missing_provenance",
            "value": str(inherited_provenance).lower(),
        },
        {
            "section": "manifest",
            "entry_id": "",
            "field": "review",
            "required": True,
            "status": "present" if inherited_review else "missing",
            "diagnostic": "" if inherited_review else "missing_review",
            "value": str(inherited_review).lower(),
        },
    ]
    for capture in depth_captures + pick_place_captures:
        field_rows.extend(field_rows_for_capture(capture))
    if not depth_captures:
        field_rows.append(
            {
                "section": "depth_reference_captures[]",
                "entry_id": "",
                "field": "entry",
                "required": True,
                "status": "missing",
                "diagnostic": "missing_depth_reference",
                "value": "",
            }
        )
    if not pick_place_captures:
        field_rows.append(
            {
                "section": "pick_place_video_captures[]",
                "entry_id": "",
                "field": "entry",
                "required": True,
                "status": "missing",
                "diagnostic": "missing_pick_place_video",
                "value": "",
            }
        )

    status = "reference_capture_manifest_ready" if ready else "reference_capture_manifest_needs_follow_up"
    return {
        **base_summary,
        "status": status,
        "manifest_path": str(manifest_path),
        "manifest_dir": str(manifest_dir),
        "manifest_schema": manifest.get("schema"),
        "expected_manifest_schema": MANIFEST_SCHEMA,
        "ready_for_calibration_grade_simcamera_tuning": ready,
        "local_only_no_copy_policy": policy,
        "provenance_present": inherited_provenance,
        "review_present": inherited_review,
        "depth_reference_capture_count": len(depth_captures),
        "pick_place_video_capture_count": len(pick_place_captures),
        "depth_reference_captures": depth_captures,
        "pick_place_video_captures": pick_place_captures,
        "path_checks": sorted(
            all_path_checks,
            key=lambda row: (str(row.get("source")), str(row.get("declared_path")), str(row.get("category"))),
        ),
        "missing_path_checks": sorted(
            missing_paths,
            key=lambda row: (str(row.get("source")), str(row.get("declared_path")), str(row.get("category"))),
        ),
        "diagnostics": sorted(set(diagnostics)),
        "field_rows": field_rows,
        "notes": [
            "This checker validates a local manifest contract only; it does not open cameras, move hardware, or copy media.",
            "Readiness means the required real depth-reference and pick/place-video inputs exist with provenance/review and sidecar fields populated.",
            "Readiness is still an operator input gate, not proof of physical calibration accuracy.",
        ],
    }


def write_csv(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = summary.get("field_rows")
    rows = rows if isinstance(rows, list) else []
    fieldnames = ["section", "entry_id", "field", "required", "status", "diagnostic", "value"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if not isinstance(row, dict):
                continue
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(markdown_escape(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_escape(value) for value in row) + " |" for row in rows)
    return lines


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics = summary.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    path_rows = summary.get("path_checks")
    path_rows = path_rows if isinstance(path_rows, list) else []
    field_rows = summary.get("field_rows")
    field_rows = field_rows if isinstance(field_rows, list) else []
    lines = [
        "# Reference Capture Manifest Check",
        "",
        "## Status",
    ]
    lines.extend(
        markdown_table(
            ["Field", "Value"],
            [
                ["status", summary.get("status")],
                ["ready_for_calibration_grade_simcamera_tuning", summary.get("ready_for_calibration_grade_simcamera_tuning")],
                ["manifest_path", summary.get("manifest_path")],
                ["depth_reference_capture_count", summary.get("depth_reference_capture_count", 0)],
                ["pick_place_video_capture_count", summary.get("pick_place_video_capture_count", 0)],
                ["media_assets_copied_into_repo", summary.get("media_assets_copied_into_repo")],
                ["diagnostics", diagnostics],
            ],
        )
    )
    lines.extend(["", "## Required Fields"])
    required = summary.get("required_capture_sidecar_fields")
    required = required if isinstance(required, list) else []
    lines.extend(
        markdown_table(
            ["Section", "Field", "Description"],
            [
                [row.get("section"), row.get("field"), row.get("description")]
                for row in required
                if isinstance(row, dict)
            ],
        )
    )
    lines.extend(["", "## Field Checklist"])
    lines.extend(
        markdown_table(
            ["Section", "Entry", "Field", "Status", "Diagnostic"],
            [
                [row.get("section"), row.get("entry_id"), row.get("field"), row.get("status"), row.get("diagnostic")]
                for row in field_rows
                if isinstance(row, dict)
            ],
        )
    )
    lines.extend(["", "## Referenced Path Checks"])
    if path_rows:
        lines.extend(
            markdown_table(
                ["Source", "Category", "Declared Path", "Exists", "Resolved Path"],
                [
                    [
                        row.get("source"),
                        row.get("category"),
                        row.get("declared_path"),
                        row.get("exists"),
                        row.get("resolved_path"),
                    ]
                    for row in path_rows
                    if isinstance(row, dict)
                ],
            )
        )
    else:
        lines.append("_No media or sidecar paths were available to check._")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This script never copies media into the repository or output directory.",
            "- Missing media and sidecar paths are diagnostics, not process failures.",
            "- A ready manifest is still an operator-supplied input gate; it is not physical calibration truth by itself.",
            "- Real depth references and pick/place videos are required before future SimCamera tuning evidence should be described as calibration-grade.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    summary = build_summary(args)
    output_dir = args.output_dir.expanduser().resolve()
    summary_path = output_dir / OUTPUT_JSON_NAME
    csv_path = output_dir / OUTPUT_CSV_NAME
    readme_path = output_dir / OUTPUT_README_NAME
    summary["summary_path"] = str(summary_path)
    summary["csv_path"] = str(csv_path)
    summary["readme_path"] = str(readme_path)
    write_json(summary_path, summary)
    write_csv(csv_path, summary)
    write_readme(readme_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
