#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "reference_capture_checklist"
SCHEMA = "lerobot.sim.reference_capture_checklist.v1"
SUITE_SCHEMA = "lerobot.sim.calibration_regression_suite.v1"
INVENTORY_SCHEMA = "lerobot.sim.reference_media_inventory.v1"
COMPARISON_SCHEMA = "lerobot.sim.reference_media_comparison_set.v1"
CURRENT_REFERENCE_PATH = "archive/chess_test_images/current_view.jpg"
OUTPUT_JSON_NAME = "reference_capture_checklist.json"
OUTPUT_MD_NAME = "reference_capture_checklist.md"
ACTIONABLE_STATUSES = {"missing", "partial"}
REPRESENTED_STATUSES = {"represented", "partial"}
NONE_FAILURE_MODES = {"", "none", "none_documented", "not_applicable"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a hardware-free SO-101 chess reference capture checklist from an "
            "existing suite summary, inventory JSON, or comparison-set summary."
        )
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        type=Path,
        default=None,
        help=(
            "Existing calibration_regression_summary.json, reference_media_inventory.json, "
            "or comparison_set_summary.json."
        ),
    )
    parser.add_argument("--suite-summary", type=Path, default=None)
    parser.add_argument("--inventory-json", type=Path, default=None)
    parser.add_argument("--comparison-summary", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object.")
    return payload


def resolve_path(value: Any, *, base_dir: Path, repo_root: Path | None = None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    base_candidate = (base_dir / path).resolve()
    if base_candidate.exists():
        return base_candidate
    if repo_root is not None:
        repo_candidate = (repo_root / path).resolve()
        if repo_candidate.exists():
            return repo_candidate
    return base_candidate


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if isinstance(item, str) and item.strip():
            rows.append(item.strip())
    return rows


def status_from_action_count(action_count: int) -> str:
    return "action_required" if action_count else "complete"


def detect_payload(path: Path) -> tuple[str, dict[str, Any]]:
    payload = read_json_object(path, label="input")
    schema = payload.get("schema")
    if schema == SUITE_SCHEMA or "calibration_session" in payload or "artifact_index" in payload:
        return "suite", payload
    if schema == INVENTORY_SCHEMA or "media" in payload and "visibility_gaps" in payload:
        return "inventory", payload
    if schema == COMPARISON_SCHEMA or "selected_media" in payload and "inventory_json_path" in payload:
        return "comparison", payload
    raise ValueError(
        f"{path} is not a supported suite, inventory, or comparison-set JSON artifact."
    )


def load_context(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.suite_summary or args.inventory_json or args.comparison_summary or args.input_json
    if input_path is None:
        raise ValueError("Provide an input JSON path or one of --suite-summary, --inventory-json, or --comparison-summary.")
    input_path = input_path.expanduser().resolve()
    kind, payload = detect_payload(input_path)

    suite: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    repo_root = REPO_ROOT
    input_base_dir = input_path.parent

    if kind == "suite":
        suite = payload
        repo_root_value = suite.get("repo_root")
        if isinstance(repo_root_value, str) and repo_root_value:
            repo_root = Path(repo_root_value).expanduser().resolve()
        inventory_section = suite.get("inventory")
        inventory_section = inventory_section if isinstance(inventory_section, dict) else {}
        inventory_path = resolve_path(
            inventory_section.get("summary_path"),
            base_dir=input_base_dir,
            repo_root=repo_root,
        )
        if inventory_path is not None and inventory_path.is_file():
            inventory = read_json_object(inventory_path, label="inventory")
        comparison_section = suite.get("comparison_set")
        comparison_section = comparison_section if isinstance(comparison_section, dict) else {}
        comparison_path = resolve_path(
            comparison_section.get("summary_path"),
            base_dir=input_base_dir,
            repo_root=repo_root,
        )
        if comparison_path is not None and comparison_path.is_file():
            comparison = read_json_object(comparison_path, label="comparison summary")
    elif kind == "inventory":
        inventory = payload
        repo_root_value = inventory.get("repo_root")
        if isinstance(repo_root_value, str) and repo_root_value:
            repo_root = Path(repo_root_value).expanduser().resolve()
    else:
        comparison = payload
        inventory_path = resolve_path(comparison.get("inventory_json_path"), base_dir=input_base_dir)
        if inventory_path is not None and inventory_path.is_file():
            inventory = read_json_object(inventory_path, label="inventory")
            repo_root_value = inventory.get("repo_root")
            if isinstance(repo_root_value, str) and repo_root_value:
                repo_root = Path(repo_root_value).expanduser().resolve()

    if args.inventory_json is not None and inventory is None:
        inventory = read_json_object(args.inventory_json.expanduser().resolve(), label="inventory")
    if args.comparison_summary is not None and comparison is None:
        comparison = read_json_object(args.comparison_summary.expanduser().resolve(), label="comparison summary")

    if inventory is None:
        raise ValueError("Could not load a reference-media inventory JSON from the supplied input.")

    return {
        "input_kind": kind,
        "input_path": str(input_path),
        "repo_root": str(repo_root),
        "suite": suite,
        "inventory": inventory,
        "comparison": comparison,
    }


def record_text(record: dict[str, Any]) -> str:
    declared = record.get("declared_metadata")
    declared = declared if isinstance(declared, dict) else {}
    parts: list[str] = []
    for key in (
        "relative_path",
        "media_type",
        "capture_id",
        "camera_view",
        "board_visibility",
        "piece_layout",
        "gripper_visibility",
        "failure_mode",
    ):
        value = declared.get(key, record.get(key))
        if isinstance(value, str):
            parts.append(value)
    for key in ("declared_tags", "reference_tags", "inferred_tags", "declared_target_categories"):
        value = declared.get(key, record.get(key))
        if isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, str))
    return " ".join(parts).lower()


def useful_for(record: dict[str, Any], category: str) -> bool:
    utility = record.get("calibration_utility")
    utility = utility if isinstance(utility, dict) else {}
    return utility.get(category) in {"useful", "candidate", "declared"}


def media_for_category(records: list[dict[str, Any]], category: str) -> list[str]:
    return sorted(
        str(record.get("relative_path"))
        for record in records
        if isinstance(record.get("relative_path"), str) and useful_for(record, category)
    )


def media_matching(records: list[dict[str, Any]], *tokens: str) -> list[str]:
    token_set = [token.lower() for token in tokens]
    matches = []
    for record in records:
        relative_path = record.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        text = record_text(record)
        if any(token in text for token in token_set):
            matches.append(relative_path)
    return sorted(set(matches))


def failure_mode_records(records: list[dict[str, Any]]) -> list[str]:
    matches = []
    for record in records:
        relative_path = record.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        declared = record.get("declared_metadata")
        declared = declared if isinstance(declared, dict) else {}
        failure_mode = str(declared.get("failure_mode") or "").strip().lower()
        if failure_mode and failure_mode not in NONE_FAILURE_MODES:
            matches.append(relative_path)
            continue
        if useful_for(record, "failure_mode"):
            matches.append(relative_path)
    return sorted(set(matches))


def simulator_profile_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        relative_path = record.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        profiles: set[str] = set()
        for ref in record.get("simulator_references") or []:
            if isinstance(ref, dict) and isinstance(ref.get("profile"), str):
                profiles.add(ref["profile"])
        declared = record.get("declared_metadata")
        declared = declared if isinstance(declared, dict) else {}
        for profile in normalize_string_list(declared.get("sim_profiles")):
            profiles.add(profile)
        if profiles:
            rows.append({"relative_path": relative_path, "profiles": sorted(profiles)})
    return rows


def manifest_fields(
    *,
    relative_path: str,
    capture_id: str,
    camera_view: str,
    board_visibility: str,
    piece_layout: str,
    gripper_visibility: str,
    calibration_targets: list[str],
    failure_mode: str = "none_documented",
    sim_profiles: list[str] | None = None,
    declared_tags: list[str] | None = None,
    notes: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "capture_id": capture_id,
        "camera_view": camera_view,
        "board_visibility": board_visibility,
        "piece_layout": piece_layout,
        "gripper_visibility": gripper_visibility,
        "calibration_targets": calibration_targets,
        "failure_mode": failure_mode,
        "sim_profiles": sim_profiles or [],
        "declared_tags": declared_tags or [],
        "notes": notes or [],
        "limitations": limitations or [],
    }


def requirement(
    *,
    requirement_id: str,
    title: str,
    status: str,
    media_type: str,
    capture_goal: str,
    represented_by: list[str] | None = None,
    partial_represented_by: list[str] | None = None,
    missing_evidence: list[str] | None = None,
    suggested_filenames: list[str] | None = None,
    manifest_template: dict[str, Any] | None = None,
    review_against: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    represented = sorted(set(represented_by or []))
    partial = sorted(set(partial_represented_by or []))
    if status not in {"represented", "partial", "missing"}:
        raise ValueError(f"Invalid requirement status {status!r} for {requirement_id}.")
    return {
        "id": requirement_id,
        "title": title,
        "status": status,
        "media_type": media_type,
        "capture_goal": capture_goal,
        "represented_by": represented,
        "partial_represented_by": partial,
        "missing_evidence": missing_evidence or [],
        "suggested_filenames": suggested_filenames or [],
        "manifest_template": manifest_template or {},
        "review_against_synthetic_outputs": review_against or [],
        "notes": notes or [],
    }


def visual_review_links(suite: dict[str, Any] | None) -> list[str]:
    if suite is None:
        return []
    visual_review = suite.get("visual_review")
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    links: list[str] = []
    contact_paths = visual_review.get("contact_sheet_paths")
    if isinstance(contact_paths, dict):
        links.extend(str(value) for value in contact_paths.values() if isinstance(value, str))
    app_frame = visual_review.get("app_entrypoint_frame")
    app_frame = app_frame if isinstance(app_frame, dict) else {}
    review_copy = app_frame.get("review_copy_path")
    if isinstance(review_copy, str):
        links.append(review_copy)
    return sorted(set(links))


def build_requirements(
    *,
    records: list[dict[str, Any]],
    suite: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    current_record = next(
        (record for record in records if record.get("relative_path") == CURRENT_REFERENCE_PATH),
        None,
    )
    current = [CURRENT_REFERENCE_PATH] if current_record is not None else []
    board_piece_gripper = sorted(
        set(media_for_category(records, "board_corners"))
        | set(media_for_category(records, "piece_scale"))
        | set(media_for_category(records, "gripper_visibility"))
    )
    board_corner_media = media_for_category(records, "board_corners")
    lighting_media = media_for_category(records, "lighting")
    videos = sorted(
        str(record.get("relative_path"))
        for record in records
        if record.get("media_type") == "video" and isinstance(record.get("relative_path"), str)
    )
    failure_media = failure_mode_records(records)
    profile_rows = simulator_profile_records(records)
    profile_media = sorted({row["relative_path"] for row in profile_rows})
    overhead_media = media_matching(records, "overhead", "bird's eye", "birds_eye", "birdseye", "top-down", "topdown")
    approach_media = sorted(set(videos) & set(media_matching(records, "approach", "pick", "grasp", "motion")))
    release_media = sorted(set(videos) & set(media_matching(records, "release", "place", "drop", "retreat")))
    post_pick_media = media_matching(records, "post_pick", "post-pick", "verification", "after_pick", "after-release")
    target_media = media_matching(records, "calibration_target", "checkerboard", "chessboard_corners", "aruco", "charuco")
    review_links = visual_review_links(suite)

    requirements = [
        requirement(
            requirement_id="static_current_gripper_reference_photo",
            title="Static gripper-reference frame",
            status="represented" if current else "missing",
            media_type="image",
            capture_goal=(
                "A repo-local still frame representing the current camera POV, board/piece scale, "
                "gripper visibility, workspace geometry, and lighting baseline."
            ),
            represented_by=current,
            missing_evidence=[] if current else [CURRENT_REFERENCE_PATH],
            suggested_filenames=["archive/reference_media/so101/static/current_gripper_reference.jpg"],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/static/current_gripper_reference.jpg",
                capture_id="so101_static_current_gripper_reference",
                camera_view="Static current camera or gripper-reference POV.",
                board_visibility="Full board area and usable corners visible.",
                piece_layout="Representative chess piece layout for scale review.",
                gripper_visibility="Gripper and pickup zone visible enough for overlay review.",
                calibration_targets=[
                    "camera_pov",
                    "board_corners",
                    "piece_scale",
                    "gripper_visibility",
                    "workspace_geometry",
                    "lighting",
                ],
                sim_profiles=["current_gripper_reference"],
                declared_tags=["real_reference", "static_photo", "current_single_image_baseline"],
            ),
            review_against=review_links,
            notes=[
                f"Today this role is covered only by {CURRENT_REFERENCE_PATH}.",
                "This is a reference-media placeholder, not physical calibration truth.",
            ],
        ),
        requirement(
            requirement_id="overhead_board_reference_photo",
            title="Overhead board POV frame",
            status="represented" if overhead_media else "missing",
            media_type="image",
            capture_goal="A top-down or bird's-eye board photo for board-square alignment and crop sanity checks.",
            represented_by=overhead_media,
            partial_represented_by=board_corner_media if not overhead_media else [],
            missing_evidence=[] if overhead_media else ["overhead or bird's-eye camera POV"],
            suggested_filenames=["archive/reference_media/so101/static/overhead_board_reference.jpg"],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/static/overhead_board_reference.jpg",
                capture_id="so101_overhead_board_reference",
                camera_view="Overhead or bird's-eye board POV.",
                board_visibility="All board edges/corners and file/rank orientation visible.",
                piece_layout="Representative pieces visible for square occupancy scale.",
                gripper_visibility="No gripper required unless it naturally appears near the board.",
                calibration_targets=["camera_pov", "board_corners", "piece_scale", "workspace_geometry"],
                declared_tags=["real_reference", "static_photo", "overhead_board"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="board_piece_gripper_closeup_photo",
            title="Board, piece, and gripper close-range frame",
            status="partial" if board_piece_gripper else "missing",
            media_type="image",
            capture_goal="A closer still frame where piece geometry and gripper fingers are easy to inspect near a pickup square.",
            represented_by=[],
            partial_represented_by=board_piece_gripper,
            missing_evidence=[
                "close-range gripper fingers around a real chess piece",
                "pickup-square crop that is more detailed than the current workspace-wide image",
            ],
            suggested_filenames=["archive/reference_media/so101/static/gripper_piece_pickup_closeup.jpg"],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/static/gripper_piece_pickup_closeup.jpg",
                capture_id="so101_gripper_piece_pickup_closeup",
                camera_view="Close gripper/pickup-zone POV.",
                board_visibility="Target square and neighboring squares visible.",
                piece_layout="Single target piece centered in pickup zone.",
                gripper_visibility="Both fingers and wrist geometry visible.",
                calibration_targets=["piece_scale", "gripper_visibility", "workspace_geometry"],
                declared_tags=["real_reference", "static_photo", "gripper_closeup"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="dedicated_calibration_target_photo_set",
            title="Dedicated calibration target or chessboard-corner shots",
            status="represented" if target_media else "missing",
            media_type="image",
            capture_goal=(
                "Photos of a dedicated calibration target, or explicit chessboard-corner/corner-order shots, "
                "with enough metadata to compare against simulator board-corner projections."
            ),
            represented_by=target_media,
            partial_represented_by=board_corner_media if not target_media else [],
            missing_evidence=[] if target_media else ["dedicated calibration target or explicit chessboard-corner capture"],
            suggested_filenames=[
                "archive/reference_media/so101/calibration/chessboard_corners_nominal.jpg",
                "archive/reference_media/so101/calibration/chessboard_corners_offset.jpg",
            ],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/calibration/chessboard_corners_nominal.jpg",
                capture_id="so101_chessboard_corners_nominal",
                camera_view="Calibration target or explicit chessboard-corner view.",
                board_visibility="All intended corners/target points visible and ordered.",
                piece_layout="No pieces required unless using board corners with normal setup.",
                gripper_visibility="No gripper required.",
                calibration_targets=["board_corners", "camera_pov", "workspace_geometry"],
                declared_tags=["real_reference", "static_photo", "calibration_target"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="gripper_approach_clip",
            title="Gripper approach clip",
            status="represented" if approach_media else "missing",
            media_type="video",
            capture_goal="A short real clip of the gripper approaching a target chess piece before grasp.",
            represented_by=approach_media,
            missing_evidence=[] if approach_media else ["real-world video of approach motion"],
            suggested_filenames=["archive/reference_media/so101/video/gripper_approach_e4.mp4"],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/video/gripper_approach_e4.mp4",
                capture_id="so101_gripper_approach_e4",
                camera_view="Camera POV used during approach.",
                board_visibility="Target square and neighboring pieces visible throughout approach.",
                piece_layout="Target piece starts on source square.",
                gripper_visibility="Fingers visible before contact.",
                calibration_targets=["camera_pov", "gripper_visibility", "piece_scale", "workspace_geometry"],
                declared_tags=["real_reference", "video", "approach_motion"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="gripper_release_clip",
            title="Gripper release clip",
            status="represented" if release_media else "missing",
            media_type="video",
            capture_goal="A short real clip of place/release and retreat after a move.",
            represented_by=release_media,
            missing_evidence=[] if release_media else ["real-world video of release and retreat motion"],
            suggested_filenames=["archive/reference_media/so101/video/gripper_release_e5.mp4"],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/video/gripper_release_e5.mp4",
                capture_id="so101_gripper_release_e5",
                camera_view="Camera POV used during release.",
                board_visibility="Target square and release area visible.",
                piece_layout="Target piece visible before and after release.",
                gripper_visibility="Fingers visible while opening and retreating.",
                calibration_targets=["camera_pov", "gripper_visibility", "piece_scale", "workspace_geometry"],
                declared_tags=["real_reference", "video", "release_motion"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="occlusion_failure_mode_clip_set",
            title="Occlusion and failure-mode clips",
            status="represented" if failure_media else "missing",
            media_type="image_or_video",
            capture_goal=(
                "Real examples of occluded pieces, missed grasps, bad lighting, recovery motion, "
                "or other failure modes that should be visible in the intake manifest."
            ),
            represented_by=failure_media,
            missing_evidence=[] if failure_media else ["failure_mode media", "occlusion examples", "recovery/missed-grasp clips"],
            suggested_filenames=[
                "archive/reference_media/so101/failure/occluded_piece_e4.mp4",
                "archive/reference_media/so101/failure/missed_grasp_e4.mp4",
                "archive/reference_media/so101/failure/bad_lighting_board.jpg",
            ],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/failure/occluded_piece_e4.mp4",
                capture_id="so101_failure_occluded_piece_e4",
                camera_view="Camera POV where failure is visible.",
                board_visibility="Board and occluding object/piece visible.",
                piece_layout="Failure case piece layout documented.",
                gripper_visibility="Gripper visible if it contributes to the failure mode.",
                calibration_targets=["failure_mode", "camera_pov", "gripper_visibility"],
                failure_mode="occluded_piece",
                declared_tags=["real_reference", "video", "failure_mode", "occlusion"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="lighting_exposure_variant_photos",
            title="Lighting and exposure variants",
            status="represented" if len(lighting_media) >= 2 else ("partial" if lighting_media else "missing"),
            media_type="image",
            capture_goal="Two or more still frames that document realistic lighting/exposure variation around the board.",
            represented_by=lighting_media if len(lighting_media) >= 2 else [],
            partial_represented_by=lighting_media if len(lighting_media) == 1 else [],
            missing_evidence=[] if len(lighting_media) >= 2 else ["second lighting/exposure variant"],
            suggested_filenames=[
                "archive/reference_media/so101/static/lighting_nominal.jpg",
                "archive/reference_media/so101/static/lighting_dim.jpg",
                "archive/reference_media/so101/static/lighting_glare.jpg",
            ],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/static/lighting_dim.jpg",
                capture_id="so101_lighting_dim",
                camera_view="Same camera POV as primary reference under changed lighting.",
                board_visibility="Board and pieces visible despite lighting change.",
                piece_layout="Representative pieces visible for scale/color review.",
                gripper_visibility="Gripper optional unless it affects exposure.",
                calibration_targets=["lighting", "camera_pov", "piece_scale"],
                declared_tags=["real_reference", "static_photo", "lighting_variant"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="post_pick_verification_photo",
            title="Post-pick or post-release verification frame",
            status="represented" if post_pick_media else "missing",
            media_type="image",
            capture_goal="A real still frame after pick or release for comparing final piece state against synthetic release frames.",
            represented_by=post_pick_media,
            missing_evidence=[] if post_pick_media else ["real post-pick or post-release verification frame"],
            suggested_filenames=["archive/reference_media/so101/static/post_release_e5_verification.jpg"],
            manifest_template=manifest_fields(
                relative_path="archive/reference_media/so101/static/post_release_e5_verification.jpg",
                capture_id="so101_post_release_e5_verification",
                camera_view="Camera POV used to verify final piece placement.",
                board_visibility="Destination square and adjacent squares visible.",
                piece_layout="Moved piece visible after release.",
                gripper_visibility="Gripper visible or clearly out of the way.",
                calibration_targets=["piece_scale", "workspace_geometry", "gripper_visibility"],
                declared_tags=["real_reference", "static_photo", "post_release_verification"],
            ),
            review_against=review_links,
        ),
        requirement(
            requirement_id="simulator_profile_manifest_link",
            title="Simulator profile link in media metadata",
            status="represented" if profile_media else "missing",
            media_type="manifest_metadata",
            capture_goal=(
                "Each useful reference item should declare the simulator profile it informs, "
                "so future captures can be routed into comparison sets without changing renderer code."
            ),
            represented_by=profile_media,
            missing_evidence=[] if profile_media else ["sim_profiles manifest field or simulator_reference_paths link"],
            suggested_filenames=["archive/reference_media_manifest.example.json"],
            manifest_template=manifest_fields(
                relative_path=CURRENT_REFERENCE_PATH,
                capture_id="current_view_static_gripper_reference",
                camera_view="Static current camera view used by current gripper-reference simulator profile.",
                board_visibility="Board area and visible corners are usable for simulator review.",
                piece_layout="Scale/layout reference.",
                gripper_visibility="Gripper visible enough to review overlay placement.",
                calibration_targets=[
                    "camera_pov",
                    "board_corners",
                    "piece_scale",
                    "gripper_visibility",
                    "workspace_geometry",
                    "lighting",
                ],
                sim_profiles=["current_gripper_reference"],
                declared_tags=["real_reference", "static_photo", "current_single_image_baseline"],
            ),
            review_against=review_links,
            notes=[f"Detected profile links: {profile_rows}" if profile_rows else "No profile links detected."],
        ),
    ]
    return requirements


def build_checklist(context: dict[str, Any], output_json: Path, output_md: Path) -> dict[str, Any]:
    suite = context.get("suite")
    suite = suite if isinstance(suite, dict) else None
    inventory = context["inventory"]
    comparison = context.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else None
    records = inventory.get("media")
    records = [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []
    inventory_summary = inventory.get("summary")
    inventory_summary = inventory_summary if isinstance(inventory_summary, dict) else {}
    manifest_summary = inventory.get("manifest_summary")
    manifest_summary = manifest_summary if isinstance(manifest_summary, dict) else {}
    reference_manifest = suite.get("reference_media_manifest") if suite is not None else None
    reference_manifest = reference_manifest if isinstance(reference_manifest, dict) else manifest_summary
    comparison_selected = comparison.get("selected_media") if isinstance(comparison, dict) else []
    selected_rows = [row for row in comparison_selected if isinstance(row, dict)] if isinstance(comparison_selected, list) else []
    requirements = build_requirements(records=records, suite=suite)
    action_items = [
        {
            "id": row["id"],
            "status": row["status"],
            "missing_evidence": row["missing_evidence"],
            "suggested_filenames": row["suggested_filenames"],
            "manifest_template": row["manifest_template"],
        }
        for row in requirements
        if row["status"] in ACTIONABLE_STATUSES
    ]
    represented_media = sorted(
        {
            path
            for row in requirements
            if row["status"] in REPRESENTED_STATUSES
            for path in (row["represented_by"] + row["partial_represented_by"])
        }
    )
    current_record = next((record for record in records if record.get("relative_path") == CURRENT_REFERENCE_PATH), None)
    current_targets = []
    if current_record is not None:
        current_targets = [
            category
            for category in (
                "camera_pov",
                "board_corners",
                "piece_scale",
                "gripper_visibility",
                "workspace_geometry",
                "lighting",
                "failure_mode",
            )
            if useful_for(current_record, category)
        ]
    skipped_markers = suite.get("skipped_markers") if suite is not None else {}
    skipped_markers = skipped_markers if isinstance(skipped_markers, dict) else {}
    hardware_skipped = bool(suite.get("hardware_skipped", inventory.get("hardware_skipped", True))) if suite else True
    gui_skipped = bool(suite.get("gui_skipped", inventory.get("gui_skipped", True))) if suite else True
    openai_skipped = bool(suite.get("openai_skipped", True)) if suite else True

    summary = {
        "schema": SCHEMA,
        "ok": True,
        "status": status_from_action_count(len(action_items)),
        "checklist_path": str(output_json),
        "markdown_path": str(output_md),
        "input": {
            "kind": context["input_kind"],
            "path": context["input_path"],
            "repo_root": context["repo_root"],
        },
        "hardware_skipped": hardware_skipped,
        "gui_skipped": gui_skipped,
        "real_camera_skipped": True,
        "openai_skipped": openai_skipped,
        "skipped_markers": {
            "hardware": skipped_markers.get(
                "hardware",
                "Checklist reads existing inventory/suite JSON only; no robot hardware paths are invoked.",
            ),
            "gui": skipped_markers.get(
                "gui",
                "Checklist generation does not request OpenCV display or click calibration flows.",
            ),
            "real_camera": "Checklist generation does not open a camera device or capture new media.",
            "openai": skipped_markers.get(
                "openai",
                "Checklist generation uses local JSON artifacts only; no OpenAI credentials or network calls are required.",
            ),
        },
        "media_summary": {
            "media_count": inventory_summary.get("media_count", len(records)),
            "image_count": inventory_summary.get("image_count"),
            "video_count": inventory_summary.get("video_count"),
            "currently_wired_media_count": inventory_summary.get("currently_wired_media_count"),
            "manifest_declared_media_count": inventory_summary.get("manifest_declared_media_count"),
            "manifest_validation_status": inventory_summary.get("manifest_validation_status"),
            "selected_media_count": len(selected_rows),
            "represented_media_count": len(represented_media),
            "represented_media": represented_media,
        },
        "reference_media_manifest": {
            "supplied": reference_manifest.get("supplied"),
            "status": reference_manifest.get("status"),
            "path": reference_manifest.get("path"),
            "declared_media_count": reference_manifest.get("declared_media_count"),
            "matched_media_count": reference_manifest.get("matched_media_count"),
        },
        "current_view_representation": {
            "relative_path": CURRENT_REFERENCE_PATH,
            "detected": current_record is not None,
            "represented_target_categories": current_targets,
            "represented_roles": [
                row["id"]
                for row in requirements
                if CURRENT_REFERENCE_PATH in row["represented_by"]
            ],
            "partial_context_roles": [
                row["id"]
                for row in requirements
                if CURRENT_REFERENCE_PATH in row["partial_represented_by"]
            ],
            "not_represented_roles": [
                row["id"]
                for row in requirements
                if CURRENT_REFERENCE_PATH not in row["represented_by"]
                and CURRENT_REFERENCE_PATH not in row["partial_represented_by"]
            ],
        },
        "synthetic_visual_review_outputs": visual_review_links(suite),
        "capture_requirements": requirements,
        "action_items": action_items,
        "counts": {
            "requirement_count": len(requirements),
            "represented_requirement_count": sum(1 for row in requirements if row["status"] == "represented"),
            "partial_requirement_count": sum(1 for row in requirements if row["status"] == "partial"),
            "missing_requirement_count": sum(1 for row in requirements if row["status"] == "missing"),
            "action_item_count": len(action_items),
        },
        "notes": [
            "This checklist is a hardware-free intake artifact only.",
            "It makes the current real-media gap actionable without requiring new media in the default suite.",
            "Future captures should be added as repo-local files plus manifest entries before comparison against synthetic visual-review outputs.",
            "No physical SO-101 calibration truth, camera capture, image/video comparison algorithm, or simulator renderer change is claimed here.",
        ],
    }
    return summary


def markdown_code(value: Any) -> str:
    text = "" if value is None else str(value)
    escaped = text.replace("`", "\\`")
    return f"`{escaped}`"


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


def write_markdown(path: Path, checklist: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    media_summary = checklist.get("media_summary")
    media_summary = media_summary if isinstance(media_summary, dict) else {}
    current = checklist.get("current_view_representation")
    current = current if isinstance(current, dict) else {}
    manifest = checklist.get("reference_media_manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    skipped = checklist.get("skipped_markers")
    skipped = skipped if isinstance(skipped, dict) else {}
    counts = checklist.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    lines = [
        "# SO-101 Chess Reference Capture Checklist",
        "",
        "## Status",
    ]
    lines.extend(
        markdown_table(
            ["Field", "Value"],
            [
                ["status", checklist.get("status")],
                ["represented_media_count", media_summary.get("represented_media_count")],
                ["missing_requirement_count", counts.get("missing_requirement_count")],
                ["partial_requirement_count", counts.get("partial_requirement_count")],
                ["action_item_count", counts.get("action_item_count")],
                ["current_reference_detected", current.get("detected")],
                ["current_reference_path", current.get("relative_path")],
                ["manifest_supplied", manifest.get("supplied")],
                ["manifest_status", manifest.get("status")],
                ["manifest_path", manifest.get("path")],
            ],
        )
    )
    lines.extend(["", "## Skipped Paths"])
    lines.extend(
        markdown_table(
            ["Path", "Skipped", "Marker"],
            [
                ["hardware", checklist.get("hardware_skipped"), skipped.get("hardware")],
                ["gui", checklist.get("gui_skipped"), skipped.get("gui")],
                ["real_camera", checklist.get("real_camera_skipped"), skipped.get("real_camera")],
                ["openai", checklist.get("openai_skipped"), skipped.get("openai")],
            ],
        )
    )
    lines.extend(["", "## Current Represented Media"])
    lines.extend(
        markdown_table(
            ["Field", "Value"],
            [
                ["media_count", media_summary.get("media_count")],
                ["image_count", media_summary.get("image_count")],
                ["video_count", media_summary.get("video_count")],
                ["currently_wired_media_count", media_summary.get("currently_wired_media_count")],
                ["represented_media", media_summary.get("represented_media")],
                ["current_view_targets", current.get("represented_target_categories")],
                ["current_view_roles", current.get("represented_roles")],
                ["current_view_partial_context_roles", current.get("partial_context_roles")],
            ],
        )
    )
    requirements = checklist.get("capture_requirements")
    requirement_rows = []
    if isinstance(requirements, list):
        for row in requirements:
            if not isinstance(row, dict):
                continue
            template = row.get("manifest_template")
            template = template if isinstance(template, dict) else {}
            targets = template.get("calibration_targets")
            requirement_rows.append(
                [
                    row.get("id"),
                    row.get("status"),
                    row.get("media_type"),
                    row.get("represented_by") or row.get("partial_represented_by"),
                    row.get("missing_evidence"),
                    row.get("suggested_filenames"),
                    targets,
                    template.get("failure_mode"),
                    template.get("sim_profiles"),
                ]
            )
    lines.extend(["", "## Capture Requirements"])
    lines.extend(
        markdown_table(
            [
                "Requirement",
                "Status",
                "Media Type",
                "Represented/Partial By",
                "Missing Evidence",
                "Suggested Filename",
                "Manifest Targets",
                "Failure Mode",
                "Sim Profiles",
            ],
            requirement_rows,
        )
    )
    action_items = checklist.get("action_items")
    action_items = action_items if isinstance(action_items, list) else []
    lines.extend(["", "## Action Items"])
    if action_items:
        for item in action_items:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {markdown_code(item.get('id'))}: {markdown_code(item.get('status'))}; capture {item.get('suggested_filenames')}.")
    else:
        lines.append("_No missing or partial capture requirements._")

    review_outputs = checklist.get("synthetic_visual_review_outputs")
    review_outputs = review_outputs if isinstance(review_outputs, list) else []
    lines.extend(["", "## Synthetic Visual Review Anchors"])
    if review_outputs:
        for output in review_outputs:
            lines.append(f"- `{output}`")
    else:
        lines.append("_No suite visual-review outputs were available from the input JSON._")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Add future media as repo-local files and wire them through `archive/reference_media_manifest.example.json` or a follow-up manifest.",
            "- Keep default suite behavior hardware-free; real media remains optional until capture work lands.",
            "- This artifact is a checklist and failure-mode placeholder, not physical calibration truth.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def failure_summary(output_json: Path, output_md: Path, error: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "validation_failed",
        "checklist_path": str(output_json),
        "markdown_path": str(output_md),
        "error": error,
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_skipped": True,
        "openai_skipped": True,
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_json = (args.output_json or output_dir / OUTPUT_JSON_NAME).expanduser().resolve()
    output_md = (args.output_md or output_dir / OUTPUT_MD_NAME).expanduser().resolve()
    try:
        context = load_context(args)
        checklist = build_checklist(context, output_json, output_md)
        write_markdown(output_md, checklist)
    except Exception as exc:
        checklist = failure_summary(output_json, output_md, str(exc))

    write_json(output_json, checklist)
    print(json.dumps(checklist, indent=2))
    if not checklist["ok"]:
        print(f"ERROR: reference capture checklist status={checklist['status']}; wrote {output_json}", file=sys.stderr)
    return 0 if checklist["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
