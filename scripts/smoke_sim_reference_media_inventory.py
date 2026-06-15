#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "reference_media_inventory"
SCHEMA = "lerobot.sim.reference_media_inventory.v1"

IMAGE_EXTENSIONS = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"})
VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"})
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
DEFAULT_SCAN_ROOTS = ("archive", "artifacts", "docs", "scripts", "src")
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
    }
)
EXPECTED_REFERENCE_CATEGORIES = (
    "camera_pov",
    "board_corners",
    "piece_scale",
    "gripper_visibility",
    "workspace_geometry",
    "lighting",
    "failure_mode",
)


@dataclass(frozen=True)
class SimulatorReference:
    profile: str
    key: str
    relative_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory real-world reference media that can guide simulator calibration "
            "without touching hardware or GUI display paths."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--include",
        action="append",
        type=Path,
        default=None,
        help=(
            "Repo-relative file or directory to scan. Can be repeated. Defaults to likely "
            "repo media roots: archive, artifacts, docs, scripts, src."
        ),
    )
    parser.add_argument("--output-name", default="reference_media_inventory.json")
    return parser.parse_args()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def relative_or_self(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def iter_candidate_media(repo_root: Path, includes: list[Path]) -> tuple[list[Path], list[dict[str, str]]]:
    media: list[Path] = []
    scan_issues: list[dict[str, str]] = []

    for raw_include in includes:
        include_path = raw_include if raw_include.is_absolute() else repo_root / raw_include
        if not include_path.exists():
            scan_issues.append(
                {
                    "path": repo_relative(include_path, repo_root),
                    "status": "missing",
                    "note": "Include path does not exist; no media scanned there.",
                }
            )
            continue
        if is_excluded(relative_or_self(include_path, repo_root)):
            scan_issues.append(
                {
                    "path": repo_relative(include_path, repo_root),
                    "status": "excluded",
                    "note": "Include path is inside an excluded cache/VCS directory.",
                }
            )
            continue
        if include_path.is_file():
            if include_path.suffix.lower() in MEDIA_EXTENSIONS:
                media.append(include_path)
            continue
        for path in include_path.rglob("*"):
            if not path.is_file() or is_excluded(relative_or_self(path, repo_root)):
                continue
            if path.suffix.lower() in MEDIA_EXTENSIONS:
                media.append(path)

    unique = sorted({path.resolve() for path in media}, key=lambda path: repo_relative(path, repo_root))
    return unique, scan_issues


def ast_value(node: ast.AST, constants: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, f"<{node.id}>")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path" and len(node.args) == 1:
        return ast_value(node.args[0], constants)
    if isinstance(node, ast.Attribute):
        owner = ast_value(node.value, constants)
        return f"{owner}.{node.attr}" if isinstance(owner, str) else node.attr
    if isinstance(node, (ast.Tuple, ast.List)):
        return [ast_value(item, constants) for item in node.elts]
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            key = ast_value(key_node, constants) if key_node is not None else None
            if key is not None:
                result[str(key)] = ast_value(value_node, constants)
        return result
    return ast.unparse(node) if hasattr(ast, "unparse") else "<unsupported>"


def simulator_reference_paths(repo_root: Path) -> tuple[list[SimulatorReference], list[dict[str, str]]]:
    config_path = repo_root / "src" / "lerobot" / "sim" / "config.py"
    if not config_path.exists():
        return [], [{"path": repo_relative(config_path, repo_root), "status": "missing"}]

    try:
        tree = ast.parse(config_path.read_text(), filename=str(config_path))
    except SyntaxError as exc:
        return [], [{"path": repo_relative(config_path, repo_root), "status": "parse_error", "note": str(exc)}]

    constants: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name = node.target.id
            value_node = node.value
        else:
            continue
        if name.startswith("CURRENT_"):
            constants[name] = ast_value(value_node, constants)
        elif name == "SIM_CAMERA_CALIBRATION_PROFILES":
            profiles = ast_value(value_node, constants)

    refs: list[SimulatorReference] = []
    for profile, payload in sorted(profiles.items()):
        if not isinstance(payload, dict):
            continue
        for key, value in sorted(payload.items()):
            if key.endswith("_path") and isinstance(value, str) and value:
                refs.append(SimulatorReference(profile=profile, key=key, relative_path=Path(value).as_posix()))
    return refs, []


def cv2_module() -> Any | None:
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    return cv2


def pil_image_module() -> Any | None:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    return Image


def image_metadata(path: Path) -> dict[str, Any]:
    cv2 = cv2_module()
    if cv2 is not None:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is not None:
            height, width = image.shape[:2]
            channels = int(image.shape[2]) if len(image.shape) == 3 else 1
            return {
                "width": int(width),
                "height": int(height),
                "channels": channels,
                "metadata_source": "opencv",
            }

    Image = pil_image_module()
    if Image is not None:
        try:
            with Image.open(path) as image:
                return {
                    "width": int(image.width),
                    "height": int(image.height),
                    "channels": len(image.getbands()),
                    "metadata_source": "pillow",
                }
        except Exception as exc:
            return {"metadata_error": f"pillow failed to read image: {exc}"}

    return {"metadata_error": "OpenCV/Pillow unavailable or could not read image."}


def video_metadata(path: Path) -> dict[str, Any]:
    cv2 = cv2_module()
    if cv2 is None:
        return {"metadata_error": "OpenCV unavailable; video dimensions/duration not read."}

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return {"metadata_error": "OpenCV could not open video."}
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        duration = frame_count / fps if frame_count > 0.0 and fps > 0.0 else None
        return {
            "width": width or None,
            "height": height or None,
            "fps": fps or None,
            "frame_count": int(frame_count) if frame_count > 0.0 else None,
            "duration_seconds": duration,
            "metadata_source": "opencv",
        }
    finally:
        capture.release()


def infer_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def inferred_tags(relative_path: str, media_type: str) -> list[str]:
    text = relative_path.lower()
    tags: set[str] = {media_type}
    if "current_view" in text:
        tags.update({"current_view", "active_current_gripper_reference"})
    if "chess_test_images" in text:
        tags.update({"chess_test_images", "real_reference"})
    if "gripper" in text or "current_view" in text:
        tags.add("gripper")
    if "board" in text or "chess" in text:
        tags.add("board")
    if "camera" in text or "view" in text:
        tags.add("camera_pov")
    if "calibration" in text or "reference" in text:
        tags.add("calibration_reference")
    if any(token in text for token in ("fail", "failure", "bad", "miss", "error")):
        tags.add("failure_mode")
    if media_type == "video":
        tags.add("motion_reference")
    return sorted(tags)


def utility_categories(tags: list[str], media_type: str) -> dict[str, str]:
    tag_set = set(tags)
    categories = {category: "gap" for category in EXPECTED_REFERENCE_CATEGORIES}
    if "active_current_gripper_reference" in tag_set:
        for category in (
            "camera_pov",
            "board_corners",
            "piece_scale",
            "gripper_visibility",
            "workspace_geometry",
            "lighting",
        ):
            categories[category] = "useful"
        categories["failure_mode"] = "not_indicated"
    else:
        if "camera_pov" in tag_set:
            categories["camera_pov"] = "candidate"
        if "board" in tag_set:
            categories["board_corners"] = "candidate"
            categories["piece_scale"] = "candidate"
            categories["workspace_geometry"] = "candidate"
        if "gripper" in tag_set:
            categories["gripper_visibility"] = "candidate"
        if media_type == "image":
            categories["lighting"] = "candidate"
        if "failure_mode" in tag_set:
            categories["failure_mode"] = "candidate"
    return categories


def calibration_notes(relative_path: str, tags: list[str], utilities: dict[str, str], wired_refs: list[SimulatorReference]) -> list[str]:
    notes: list[str] = []
    if any(ref.relative_path == relative_path for ref in wired_refs):
        profiles = sorted({ref.profile for ref in wired_refs if ref.relative_path == relative_path})
        notes.append(f"Wired into simulator profile(s): {', '.join(profiles)}.")
    if "active_current_gripper_reference" in tags:
        notes.append(
            "Active current gripper reference: useful for camera POV, board-corner placement, piece scale, "
            "gripper overlay placement, workspace geometry, and lighting calibration."
        )
    if utilities["failure_mode"] in {"gap", "not_indicated"}:
        notes.append("Does not appear to document a failure mode from path/name heuristics.")
    return notes


def build_media_record(path: Path, repo_root: Path, wired_refs: list[SimulatorReference]) -> dict[str, Any]:
    relative_path = repo_relative(path, repo_root)
    media_type = infer_media_type(path)
    metadata = image_metadata(path) if media_type == "image" else video_metadata(path)
    tags = inferred_tags(relative_path, media_type)
    utilities = utility_categories(tags, media_type)
    matching_refs = [ref for ref in wired_refs if ref.relative_path == relative_path]

    return {
        "relative_path": relative_path,
        "media_type": media_type,
        "mime_type": mimetypes.guess_type(path.name)[0],
        "extension": path.suffix.lower(),
        "file_size_bytes": int(path.stat().st_size),
        "dimensions": {
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "channels": metadata.get("channels"),
        },
        "duration_seconds": metadata.get("duration_seconds"),
        "metadata": metadata,
        "inferred_tags": tags,
        "tagging_basis": "heuristic_path_and_filename",
        "calibration_utility": utilities,
        "calibration_utility_notes": calibration_notes(relative_path, tags, utilities, wired_refs),
        "currently_wired_into_simulator_tooling": bool(matching_refs),
        "simulator_references": [
            {"profile": ref.profile, "key": ref.key, "relative_path": ref.relative_path} for ref in matching_refs
        ],
    }


def category_coverage(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {category: [] for category in EXPECTED_REFERENCE_CATEGORIES}
    for record in records:
        utilities = record["calibration_utility"]
        for category in EXPECTED_REFERENCE_CATEGORIES:
            if utilities.get(category) in {"useful", "candidate"}:
                coverage[category].append(record["relative_path"])
    return {key: sorted(value) for key, value in coverage.items()}


def visibility_gaps(records: list[dict[str, Any]], wired_refs: list[SimulatorReference]) -> list[dict[str, str]]:
    coverage = category_coverage(records)
    gaps: list[dict[str, str]] = []
    for category, paths in coverage.items():
        if not paths:
            gaps.append(
                {
                    "category": category,
                    "status": "missing",
                    "note": "No found media was heuristically useful for this reference category.",
                }
            )
    if not any(record["media_type"] == "video" for record in records):
        gaps.append(
            {
                "category": "video",
                "status": "missing",
                "note": "No real-world videos were found for motion, recovery, or failure-mode timing references.",
            }
        )
    wired_paths = {ref.relative_path for ref in wired_refs}
    found_paths = {record["relative_path"] for record in records}
    for missing in sorted(wired_paths - found_paths):
        gaps.append(
            {
                "category": "simulator_reference",
                "status": "missing_file",
                "note": f"Simulator config references {missing}, but it was not found by this scan.",
            }
        )
    return gaps


def build_inventory(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.expanduser().resolve()
    includes = args.include if args.include else [Path(path) for path in DEFAULT_SCAN_ROOTS]
    wired_refs, simulator_reference_issues = simulator_reference_paths(repo_root)
    media_paths, scan_issues = iter_candidate_media(repo_root, includes)
    records = [build_media_record(path, repo_root, wired_refs) for path in media_paths]
    coverage = category_coverage(records)
    active_path = "archive/chess_test_images/current_view.jpg"
    active_records = [record for record in records if record["relative_path"] == active_path]
    videos = [record for record in records if record["media_type"] == "video"]

    return {
        "schema": SCHEMA,
        "ok": True,
        "repo_root": str(repo_root),
        "output_path": str(args.output_dir.expanduser().resolve() / args.output_name),
        "hardware_skipped": True,
        "gui_skipped": True,
        "scan": {
            "include_paths": [path.as_posix() for path in includes],
            "media_extensions": sorted(MEDIA_EXTENSIONS),
            "excluded_dir_names": sorted(EXCLUDED_DIR_NAMES),
            "scan_issues": scan_issues,
        },
        "simulator_reference_paths": [
            {"profile": ref.profile, "key": ref.key, "relative_path": ref.relative_path} for ref in wired_refs
        ],
        "simulator_reference_issues": simulator_reference_issues,
        "summary": {
            "media_count": len(records),
            "image_count": sum(1 for record in records if record["media_type"] == "image"),
            "video_count": len(videos),
            "currently_wired_media_count": sum(
                1 for record in records if record["currently_wired_into_simulator_tooling"]
            ),
            "active_current_gripper_reference_detected": bool(active_records),
            "active_current_gripper_reference_path": active_path,
            "coverage": coverage,
            "videos_present": bool(videos),
        },
        "media": records,
        "visibility_gaps": visibility_gaps(records, wired_refs),
        "next_recommended_reference_fixture_inputs": [
            record["relative_path"]
            for record in records
            if record["currently_wired_into_simulator_tooling"]
            or "active_current_gripper_reference" in record["inferred_tags"]
        ],
        "notes": [
            "Tags and calibration utility are heuristic, based on path/name and simulator wiring.",
            "This inventory reports found media only; it does not create thumbnails or calibration datasets.",
        ],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory(args)
    output_path = output_dir / args.output_name
    inventory["output_path"] = str(output_path)
    output_path.write_text(json.dumps(inventory, indent=2) + "\n")
    print(json.dumps(inventory, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
