#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from smoke_sim_real_calibration_sidecars import validate_sidecar_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "real_calibration_capture"
SCHEMA = "lerobot.sim.real_calibration_capture_workflow.v1"
SIDECAR_SCHEMA_PREFIX = "lerobot.sim.real_calibration_sidecar"
BOARD_CORNER_ORDER = ("a1", "h1", "h8", "a8")
SUPPORTED_REQUIREMENTS = ("intrinsics", "extrinsics", "board_pose", "depth")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare hardware-free SO-101 real-calibration sidecar JSON from file/manual inputs. "
            "The default path never opens a camera, moves motors, or claims real calibration."
        )
    )
    parser.add_argument("--capture-spec", type=Path, default=None, help="JSON object with capture inputs.")
    parser.add_argument("--image-path", type=Path, default=None, help="Repo-local or absolute captured image path.")
    parser.add_argument("--capture-id", default=None)
    parser.add_argument("--camera-id", default=None)
    parser.add_argument("--image-size", default=None, help="Image size as WIDTHxHEIGHT when it cannot be read.")
    parser.add_argument("--camera-matrix-json", default=None, help="3x3 camera matrix JSON array.")
    parser.add_argument("--distortion-json", default=None, help="Distortion coefficients JSON array.")
    parser.add_argument(
        "--corner",
        action="append",
        default=[],
        help="Board corner as label:x,y. Repeat for a1,h1,h8,a8.",
    )
    parser.add_argument(
        "--distance",
        action="append",
        default=[],
        help="Metric reference as id:distance_m or id:distance_m:x,y. Repeat as needed.",
    )
    parser.add_argument("--board-size-m", type=float, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--require",
        action="append",
        choices=SUPPORTED_REQUIREMENTS,
        default=[],
        help="Fail if this sidecar kind cannot be written from supplied inputs.",
    )
    truth_group = parser.add_mutually_exclusive_group()
    truth_group.add_argument(
        "--example-only",
        action="store_true",
        help="Mark generated sidecars as example/test-only. This is the default.",
    )
    truth_group.add_argument(
        "--real-capture",
        action="store_true",
        help="Mark generated sidecars as user-supplied real capture data.",
    )
    return parser.parse_args()


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def repo_relative(path: Path, repo_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def resolve_path(value: str | Path | None, *, repo_root: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def parse_json_arg(value: str | None, *, label: str) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc}") from exc


def parse_image_size(value: str | None) -> list[int] | None:
    if value is None:
        return None
    pieces = value.lower().split("x")
    if len(pieces) != 2:
        raise ValueError("--image-size must use WIDTHxHEIGHT, for example 640x480.")
    try:
        width, height = int(pieces[0]), int(pieces[1])
    except ValueError as exc:
        raise ValueError("--image-size must contain integer width and height.") from exc
    if width <= 0 or height <= 0:
        raise ValueError("--image-size values must be positive.")
    return [width, height]


def detect_image_size(path: Path | None) -> list[int] | None:
    if path is None or not path.is_file():
        return None
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return None
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    return [int(image.shape[1]), int(image.shape[0])]


def parse_corner(value: str) -> dict[str, Any]:
    try:
        label, xy_text = value.split(":", 1)
        x_text, y_text = xy_text.split(",", 1)
        x, y = float(x_text), float(y_text)
    except ValueError as exc:
        raise ValueError("--corner must use label:x,y, for example a1:82.0,356.0.") from exc
    if label not in BOARD_CORNER_ORDER:
        raise ValueError(f"--corner label must be one of {','.join(BOARD_CORNER_ORDER)}.")
    return {"label": label, "pixel_xy": [x, y], "confidence": 1.0}


def parse_distance(value: str) -> dict[str, Any]:
    pieces = value.split(":")
    if len(pieces) not in {2, 3}:
        raise ValueError("--distance must use id:distance_m or id:distance_m:x,y.")
    reference_id = pieces[0].strip()
    if not reference_id:
        raise ValueError("--distance id must be non-empty.")
    try:
        distance_m = float(pieces[1])
    except ValueError as exc:
        raise ValueError("--distance distance_m must be numeric.") from exc
    if distance_m <= 0.0 or not math.isfinite(distance_m):
        raise ValueError("--distance distance_m must be positive and finite.")
    reference: dict[str, Any] = {
        "id": reference_id,
        "target": reference_id,
        "distance_m": distance_m,
        "distance_type": "camera_range",
    }
    if len(pieces) == 3:
        try:
            x_text, y_text = pieces[2].split(",", 1)
            reference["pixel_xy"] = [float(x_text), float(y_text)]
        except ValueError as exc:
            raise ValueError("--distance pixel point must use x,y.") from exc
    return reference


def merge_capture_inputs(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    if args.capture_spec is not None:
        spec_path = resolve_path(args.capture_spec, repo_root=repo_root)
        if spec_path is None:
            raise ValueError("--capture-spec did not resolve to a path.")
        spec = read_json_object(spec_path, label="capture spec")

    if args.image_path is not None:
        spec["image_path"] = str(args.image_path)
    if args.capture_id is not None:
        spec["capture_id"] = args.capture_id
    if args.camera_id is not None:
        spec["camera_id"] = args.camera_id

    image_size = parse_image_size(args.image_size)
    if image_size is not None:
        spec["image_size_px"] = image_size

    camera_matrix = parse_json_arg(args.camera_matrix_json, label="--camera-matrix-json")
    distortion = parse_json_arg(args.distortion_json, label="--distortion-json")
    if camera_matrix is not None or distortion is not None:
        intrinsics = spec.get("intrinsics")
        intrinsics = intrinsics if isinstance(intrinsics, dict) else {}
        if camera_matrix is not None:
            intrinsics["camera_matrix_px"] = camera_matrix
        if distortion is not None:
            intrinsics["distortion_coefficients"] = distortion
        spec["intrinsics"] = intrinsics

    if args.corner:
        board = spec.get("board")
        board = board if isinstance(board, dict) else {}
        board["corners"] = [parse_corner(value) for value in args.corner]
        spec["board"] = board
    if args.board_size_m is not None:
        board = spec.get("board")
        board = board if isinstance(board, dict) else {}
        board["board_size_m"] = args.board_size_m
        spec["board"] = board

    if args.distance:
        depth = spec.get("depth")
        depth = depth if isinstance(depth, dict) else {}
        depth["metric_references"] = [parse_distance(value) for value in args.distance]
        spec["depth"] = depth

    return spec


def ordered_corners(corners: Any) -> list[dict[str, Any]] | None:
    if isinstance(corners, dict):
        ordered: list[dict[str, Any]] = []
        for label in BOARD_CORNER_ORDER:
            xy = corners.get(label)
            if not isinstance(xy, list) or len(xy) != 2 or not all(is_number(item) for item in xy):
                return None
            ordered.append({"label": label, "pixel_xy": [float(xy[0]), float(xy[1])], "confidence": 1.0})
        return ordered
    if isinstance(corners, list):
        by_label = {corner.get("label"): corner for corner in corners if isinstance(corner, dict)}
        if set(by_label) >= set(BOARD_CORNER_ORDER):
            return [by_label[label] for label in BOARD_CORNER_ORDER]
    return None


def sidecar_truth_flags(args: argparse.Namespace) -> dict[str, bool]:
    real_capture = bool(args.real_capture)
    return {"example_only": not real_capture, "real_capture": real_capture}


def build_intrinsics(spec: dict[str, Any], *, image_size_px: list[int] | None, flags: dict[str, bool]) -> dict[str, Any] | None:
    intrinsics = spec.get("intrinsics")
    if not isinstance(intrinsics, dict) or image_size_px is None:
        return None
    camera_id = spec.get("camera_id") or intrinsics.get("camera_id")
    payload = {
        "schema": f"{SIDECAR_SCHEMA_PREFIX}.intrinsics.v1",
        "sidecar_type": "intrinsics",
        **flags,
        "camera_id": camera_id,
        "calibration_source": intrinsics.get("calibration_source")
        or ("user-supplied real capture inputs" if flags["real_capture"] else "example/test-only capture workflow input"),
        "image_size_px": image_size_px,
        "camera_matrix_px": intrinsics.get("camera_matrix_px"),
        "distortion_model": intrinsics.get("distortion_model", "opencv_plumb_bob"),
        "distortion_coefficients": intrinsics.get("distortion_coefficients"),
        "units": "pixels",
        "notes": intrinsics.get("notes", []),
    }
    if payload["camera_id"] is None:
        return None
    return payload


def build_extrinsics(spec: dict[str, Any], *, flags: dict[str, bool]) -> dict[str, Any] | None:
    extrinsics = spec.get("extrinsics")
    if not isinstance(extrinsics, dict):
        return None
    camera_id = spec.get("camera_id") or extrinsics.get("camera_id")
    transform = extrinsics.get("transform")
    has_transform = isinstance(transform, dict) or (
        "matrix_4x4" in extrinsics or ("translation_m" in extrinsics and "rotation_matrix" in extrinsics)
    )
    if camera_id is None or not has_transform:
        return None
    payload = {
        "schema": f"{SIDECAR_SCHEMA_PREFIX}.extrinsics.v1",
        "sidecar_type": "extrinsics",
        **flags,
        "camera_id": camera_id,
        "transform_convention": extrinsics.get("transform_convention", "board_to_camera"),
        "coordinate_frame_convention": extrinsics.get(
            "coordinate_frame_convention",
            "OpenCV camera frame: +x right, +y down, +z forward; board frame origin at a1.",
        ),
        "notes": extrinsics.get("notes", []),
    }
    if isinstance(transform, dict):
        payload["transform"] = transform
    elif "matrix_4x4" in extrinsics:
        payload["transform"] = {"matrix_4x4": extrinsics.get("matrix_4x4")}
    else:
        payload["transform"] = {
            "translation_m": extrinsics.get("translation_m"),
            "rotation_matrix": extrinsics.get("rotation_matrix"),
        }
    return payload


def build_board_pose(spec: dict[str, Any], *, image_size_px: list[int] | None, flags: dict[str, bool]) -> dict[str, Any] | None:
    board = spec.get("board")
    if not isinstance(board, dict) or image_size_px is None:
        return None
    corners = ordered_corners(board.get("corners"))
    if corners is None:
        return None
    payload: dict[str, Any] = {
        "schema": f"{SIDECAR_SCHEMA_PREFIX}.board_pose.v1",
        "sidecar_type": "board_pose",
        **flags,
        "image_size_px": image_size_px,
        "corner_order": list(BOARD_CORNER_ORDER),
        "corners": corners,
        "detection_source": board.get("detection_source")
        or ("manual user-supplied corner detections" if flags["real_capture"] else "example/test-only manual corner detections"),
        "notes": board.get("notes", []),
    }
    if board.get("board_size_m") is not None:
        payload["board_size_m"] = board.get("board_size_m")
    for key in ("transform_convention", "transform", "matrix_4x4", "translation_m", "rotation_matrix"):
        if key in board:
            payload[key] = board[key]
    return payload


def build_depth(spec: dict[str, Any], *, flags: dict[str, bool]) -> dict[str, Any] | None:
    depth = spec.get("depth")
    if not isinstance(depth, dict):
        return None
    metric_references = depth.get("metric_references")
    depth_map = depth.get("depth_map")
    if metric_references is None and depth_map is None:
        return None
    payload: dict[str, Any] = {
        "schema": f"{SIDECAR_SCHEMA_PREFIX}.depth.v1",
        "sidecar_type": "depth",
        **flags,
        "depth_units": depth.get("depth_units", "m"),
        "depth_scale_to_m": depth.get("depth_scale_to_m", 1.0),
        "reference_frame": depth.get(
            "reference_frame",
            "OpenCV camera frame; metric_references are measured camera range unless noted per row.",
        ),
        "notes": depth.get("notes", []),
    }
    if metric_references is not None:
        payload["metric_references"] = metric_references
    if depth_map is not None:
        payload["depth_map"] = depth_map
    return payload


def capture_steps(missing_requirements: list[str], *, real_capture: bool) -> list[str]:
    base_steps = [
        "Keep SO-101 motors disabled or stationary; this helper does not move hardware.",
        "Capture a sharp, repo-local chessboard image with all four board corners visible.",
        "Record the camera id/source, image resolution, and capture provenance.",
        "Measure or solve camera intrinsics with a real calibration target; do not reuse synthetic fixtures.",
        "Mark board corners in a1,h1,h8,a8 order or provide a solved board pose using the documented frame convention.",
        "Measure camera-to-board or camera-to-piece distances, or attach depth-map metadata with units and scale.",
        "Run the generated sidecars through scripts/smoke_sim_real_calibration_sidecars.py before wiring them into a manifest.",
    ]
    if not real_capture:
        base_steps.append("Generated sidecars are marked example_only=true unless --real-capture is passed.")
    if missing_requirements:
        base_steps.append(f"Missing required inputs for this run: {', '.join(missing_requirements)}.")
    return base_steps


def build_plan_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Real Calibration Capture Plan",
        "",
        "This artifact is hardware-aware scaffolding only. The helper did not open a camera, move motors, or execute robot actions.",
        "",
        f"- Capture id: `{summary['capture_id']}`",
        f"- Image path: `{summary.get('image_path')}`",
        f"- Camera id: `{summary.get('camera_id')}`",
        f"- Real capture flag: `{summary['real_capture']}`",
        f"- Example-only flag: `{summary['example_only']}`",
        "",
        "## Written Sidecars",
    ]
    for sidecar in summary["sidecars"]:
        lines.append(f"- `{sidecar['kind']}`: `{sidecar['path']}` ({sidecar['validation_status']})")
    if not summary["sidecars"]:
        lines.append("- None; supply capture inputs before expecting sidecar JSON.")
    lines.extend(["", "## Next Physical Capture Steps"])
    lines.extend(f"- {step}" for step in summary["next_capture_steps"])
    lines.append("")
    return "\n".join(lines)


def build_manifest(summary: dict[str, Any], *, output_dir: Path, repo_root: Path) -> dict[str, Any]:
    sidecars_by_kind = {item["kind"]: item["path"] for item in summary["sidecars"]}
    media_entry: dict[str, Any] = {
        "relative_path": repo_relative(Path(summary["image_path"]), repo_root) or summary["image_path"],
        "capture_id": summary["capture_id"],
        "camera_view": "User-supplied capture workflow image. Confirm physical camera mounting before real calibration use.",
        "board_visibility": "All four board corners should be visible and manually/detector confirmed.",
        "piece_layout": "User supplied; document piece layout in notes before residual comparison.",
        "gripper_visibility": "User supplied; document wrist/gripper visibility before residual comparison.",
        "calibration_targets": ["board_corners", "workspace_geometry", "piece_scale"],
        "failure_mode": "none_documented",
        "sim_profiles": ["current_gripper_reference"],
        "declared_tags": ["capture_workflow_generated"],
        "notes": [
            "Generated by prepare_real_calibration_capture_sidecars.py.",
            "Do not treat example_only sidecars as physical SO-101 calibration.",
        ],
        "limitations": [
            "Hardware was not accessed by the helper.",
            "Residual comparability still depends on user-supplied real capture provenance.",
        ],
    }
    key_by_kind = {
        "intrinsics": "real_intrinsics_path",
        "extrinsics": "real_extrinsics_path",
        "board_pose": "board_corner_detections_path",
        "depth": "depth_reference_path",
    }
    for kind, key in key_by_kind.items():
        path_text = sidecars_by_kind.get(kind)
        if path_text is not None:
            media_entry[key] = repo_relative(Path(path_text), repo_root) or path_text
    manifest = {
        "schema": "lerobot.sim.reference_media_manifest.v1",
        "notes": [
            "Generated capture-workflow manifest for validator/intake smoke tests.",
            "Sidecar truth is controlled by each sidecar's example_only/real_capture flags.",
        ],
        "media": [media_entry],
    }
    write_json(output_dir / "reference_media_manifest.generated_sidecars.json", manifest)
    return manifest


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = merge_capture_inputs(args, repo_root)
    image_path = resolve_path(spec.get("image_path"), repo_root=repo_root)
    image_size_px = spec.get("image_size_px")
    if not isinstance(image_size_px, list) or len(image_size_px) != 2:
        image_size_px = detect_image_size(image_path)
    capture_id = str(spec.get("capture_id") or (image_path.stem if image_path else "capture_workflow"))
    flags = sidecar_truth_flags(args)

    builders = {
        "intrinsics": build_intrinsics(spec, image_size_px=image_size_px, flags=flags),
        "extrinsics": build_extrinsics(spec, flags=flags),
        "board_pose": build_board_pose(spec, image_size_px=image_size_px, flags=flags),
        "depth": build_depth(spec, flags=flags),
    }
    sidecars: list[dict[str, Any]] = []
    missing_requirements: list[str] = []
    for kind in SUPPORTED_REQUIREMENTS:
        payload = builders[kind]
        if payload is None:
            if kind in args.require:
                missing_requirements.append(kind)
            continue
        kind_from_payload, issues = validate_sidecar_payload(payload, path=Path(f"{kind}.json"))
        path = output_dir / f"{capture_id}_{kind}.json"
        write_json(path, payload)
        sidecars.append(
            {
                "kind": kind_from_payload,
                "path": str(path),
                "repo_relative_path": repo_relative(path, repo_root),
                "ok": not issues,
                "validation_status": "valid" if not issues else "invalid",
                "issues": issues,
                "example_only": payload.get("example_only"),
                "real_capture": payload.get("real_capture"),
            }
        )
        if issues and kind in args.require:
            missing_requirements.append(kind)

    ok = not missing_requirements and all(item["ok"] for item in sidecars)
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "missing_required_capture_inputs",
        "output_dir": str(output_dir),
        "repo_root": str(repo_root),
        "capture_id": capture_id,
        "image_path": str(image_path) if image_path is not None else None,
        "image_exists": bool(image_path and image_path.is_file()),
        "image_size_px": image_size_px,
        "camera_id": spec.get("camera_id"),
        "hardware_skipped": True,
        "gui_skipped": True,
        "real_camera_capture_skipped": True,
        "robot_motion_skipped": True,
        "openai_skipped": True,
        "example_only": flags["example_only"],
        "real_capture": flags["real_capture"],
        "required_sidecars": list(args.require),
        "missing_required_sidecars": missing_requirements,
        "sidecars": sidecars,
        "next_capture_steps": capture_steps(missing_requirements, real_capture=flags["real_capture"]),
    }
    manifest = build_manifest(summary, output_dir=output_dir, repo_root=repo_root) if image_path is not None else None
    summary["generated_manifest_path"] = (
        str(output_dir / "reference_media_manifest.generated_sidecars.json") if manifest is not None else None
    )
    write_json(output_dir / "capture_workflow_summary.json", summary)
    write_text(output_dir / "capture_plan.md", build_plan_markdown(summary))
    return summary


def main() -> int:
    args = parse_args()
    try:
        summary = build_summary(args)
    except ValueError as exc:
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "status": "invalid_capture_inputs",
            "output_dir": str(output_dir),
            "error": str(exc),
            "hardware_skipped": True,
            "gui_skipped": True,
            "real_camera_capture_skipped": True,
            "robot_motion_skipped": True,
            "openai_skipped": True,
        }
        write_json(output_dir / "capture_workflow_summary.json", summary)
    print(json.dumps(summary, indent=2))
    if not summary["ok"]:
        print(f"ERROR: capture workflow status={summary['status']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
