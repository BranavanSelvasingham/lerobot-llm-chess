#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import csv
import json
import mimetypes
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp") / "lerobot_sim" / "reference_media_inventory"
SCHEMA = "lerobot.sim.reference_media_inventory.v1"
MANIFEST_SCHEMA = "lerobot.sim.reference_media_manifest.v1"

IMAGE_EXTENSIONS = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"})
VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"})
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
CALIBRATION_DATA_EXTENSIONS = frozenset({".json", ".yaml", ".yml"})
CANDIDATE_EXTENSIONS = MEDIA_EXTENSIONS | CALIBRATION_DATA_EXTENSIONS
DEFAULT_SCAN_ROOTS = ("archive", "artifacts", "docs", "scripts", "src")
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".cache",
        ".git",
        ".hg",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site-packages",
        "tmp",
        "temp",
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
DECLARED_METADATA_FIELDS = (
    "capture_id",
    "camera_view",
    "board_visibility",
    "piece_layout",
    "gripper_visibility",
    "calibration_targets",
    "failure_mode",
    "sim_profiles",
    "real_intrinsics_path",
    "real_extrinsics_path",
    "real_board_pose_path",
    "board_corner_detections_path",
    "real_depth_path",
    "depth_reference_path",
    "declared_tags",
    "notes",
    "limitations",
)
TARGET_CATEGORY_ALIASES = {
    "board_corners": "board_corners",
    "board_corner_alignment": "board_corners",
    "camera_pov": "camera_pov",
    "camera_pose": "camera_pov",
    "failure_mode": "failure_mode",
    "gripper_overlay": "gripper_visibility",
    "gripper_visibility": "gripper_visibility",
    "lighting": "lighting",
    "piece_scale": "piece_scale",
    "workspace_geometry": "workspace_geometry",
}
REFERENCE_CLASS_LABELS = {
    "camera_pov": "camera POV",
    "chessboard_board": "chessboard/board",
    "gripper_arm": "gripper/arm",
    "calibration_target": "calibration target",
    "depth_distance": "depth/distance",
    "ui_demo_screenshot": "UI/demo/screenshot",
    "unknown": "unknown",
}
REFERENCE_CLASS_KEYWORDS = {
    "camera_pov": (
        "camera",
        "cam",
        "pov",
        "view",
        "current_view",
        "overhead",
        "side_view",
        "bird",
        "projection",
    ),
    "chessboard_board": (
        "board",
        "chess",
        "chessboard",
        "square",
        "corner",
        "rank",
        "file",
        "piece",
        "a1",
        "h8",
    ),
    "gripper_arm": (
        "gripper",
        "arm",
        "wrist",
        "so101",
        "so-101",
        "robot",
        "end_effector",
        "eef",
        "pickup",
        "pick_place",
    ),
    "calibration_target": (
        "calibration",
        "calibrate",
        "checkerboard",
        "charuco",
        "aruco",
        "fiducial",
        "target",
        "intrinsics",
        "extrinsics",
        "distortion",
    ),
    "depth_distance": (
        "depth",
        "distance",
        "range",
        "metric",
        "z_depth",
        "plane",
        "pose",
    ),
    "ui_demo_screenshot": (
        "ui",
        "screenshot",
        "screen",
        "demo",
        "viz",
        "visual",
        "contact_sheet",
        "overlay",
    ),
}
REFERENCE_GAP_DEFINITIONS = (
    (
        "missing_gripper_pov",
        "No found candidate combines camera POV and gripper/arm evidence.",
    ),
    (
        "missing_board_closeup",
        "No found candidate is classified as chessboard/board evidence.",
    ),
    (
        "missing_depth_reference",
        "No found candidate is classified as depth/distance evidence.",
    ),
    (
        "missing_calibration_target",
        "No found candidate is classified as calibration-target evidence.",
    ),
    (
        "missing_pick_place_video",
        "No found video appears to document pick/place, grasp, release, or recovery motion.",
    ),
)
CALIBRATION_DATA_KEYWORDS = frozenset(
    {
        "aruco",
        "board",
        "camera",
        "calibration",
        "charuco",
        "chess",
        "chessboard",
        "corner",
        "depth",
        "distortion",
        "extrinsic",
        "extrinsics",
        "intrinsic",
        "intrinsics",
        "pose",
        "projection",
    }
)
EXCLUDED_CALIBRATION_DATA_PARTS = frozenset({".github"})
EXCLUDED_CALIBRATION_DATA_FILENAMES = frozenset({".pre-commit-config.yaml"})
TEXT_SCAN_BYTES = 64 * 1024


@dataclass(frozen=True)
class SimulatorReference:
    profile: str
    key: str
    relative_path: str


@dataclass(frozen=True)
class CandidateFile:
    path: Path
    scan_root: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory real-world reference media that can guide simulator calibration "
            "without touching hardware or GUI display paths."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help=(
            "File or directory root to scan. Can be repeated. When omitted, only "
            "--repo-root is scanned. Supplying --root replaces the default scan root, "
            "so use --root . --root /path/to/sibling to include both."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--include",
        action="append",
        type=Path,
        default=None,
        help=(
            "Legacy repo-relative file or directory filter. Can be repeated. When omitted, "
            "each --root is scanned recursively. When supplied, filters scan paths inside "
            "repo_root for compatibility with older calls."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=(
            "Optional repo-relative JSON manifest describing reference-media intent and "
            "coverage metadata for found media."
        ),
    )
    parser.add_argument("--output-name", default="reference_media_inventory.json")
    return parser.parse_args()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def root_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def record_relative_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def is_repo_local(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def relative_or_self(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON in {label} {path}: {exc}"
    except OSError as exc:
        return None, f"Could not read {label} {path}: {exc}"
    if not isinstance(payload, dict):
        return None, f"{label} {path} must contain a JSON object."
    return payload, None


def repo_local_manifest_path(raw_path: Path | None, repo_root: Path) -> tuple[Path | None, dict[str, str] | None]:
    if raw_path is None:
        return None, None
    manifest_path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = manifest_path.expanduser().resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return (
            resolved,
            {
                "path": str(resolved),
                "status": "outside_repo",
                "note": "Manifest path must resolve inside repo_root.",
            },
        )
    return resolved, None


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def declared_target_categories(metadata: dict[str, Any]) -> list[str]:
    categories: set[str] = set()
    for target in normalize_string_list(metadata.get("calibration_targets")):
        key = target.strip().lower().replace("-", "_").replace(" ", "_")
        category = TARGET_CATEGORY_ALIASES.get(key)
        if category:
            categories.add(category)
    failure_mode = metadata.get("failure_mode")
    if isinstance(failure_mode, str) and failure_mode.strip().lower() not in {"", "none", "none_documented", "not_applicable"}:
        categories.add("failure_mode")
    return sorted(categories)


def manifest_path_issue(relative_path: Any, repo_root: Path) -> tuple[str | None, dict[str, str] | None]:
    if not isinstance(relative_path, str) or not relative_path:
        return None, {"path": str(relative_path), "status": "invalid_path", "note": "Media entry path must be a string."}
    media_path = (repo_root / relative_path).resolve()
    try:
        media_path.relative_to(repo_root.resolve())
    except ValueError:
        return relative_path, {
            "path": relative_path,
            "status": "outside_repo",
            "note": "Manifest media paths must resolve inside repo_root.",
        }
    if not media_path.exists():
        return relative_path, {"path": relative_path, "status": "missing", "note": "Manifest media path does not exist."}
    if not media_path.is_file():
        return relative_path, {"path": relative_path, "status": "not_file", "note": "Manifest media path is not a file."}
    if media_path.suffix.lower() not in MEDIA_EXTENSIONS:
        return relative_path, {
            "path": relative_path,
            "status": "unsupported_media_type",
            "note": "Manifest media path exists but is not a supported image/video extension.",
        }
    return repo_relative(media_path, repo_root), None


def manifest_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in DECLARED_METADATA_FIELDS:
        if field in entry:
            metadata[field] = entry[field]
    metadata["declared_target_categories"] = declared_target_categories(metadata)
    return metadata


def load_reference_media_manifest(
    manifest_arg: Path | None,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_path, path_issue = repo_local_manifest_path(manifest_arg, repo_root)
    if manifest_arg is None:
        return (
            {
                "schema": MANIFEST_SCHEMA,
                "supplied": False,
                "ok": True,
                "status": "not_supplied",
                "path": None,
                "declared_media_count": 0,
                "valid_media_count": 0,
                "matched_media_count": 0,
                "issue_count": 0,
                "issues": [],
                "notes": [
                    "No manifest was supplied; inventory metadata is heuristic path/name metadata only.",
                ],
            },
            {},
        )
    if path_issue is not None:
        return (
            {
                "schema": MANIFEST_SCHEMA,
                "supplied": True,
                "ok": False,
                "status": "validation_failed",
                "path": str(manifest_path),
                "declared_media_count": 0,
                "valid_media_count": 0,
                "matched_media_count": 0,
                "issue_count": 1,
                "issues": [path_issue],
            },
            {},
        )
    assert manifest_path is not None
    payload, error = read_json_object(manifest_path, label="reference media manifest")
    if error is not None or payload is None:
        return (
            {
                "schema": MANIFEST_SCHEMA,
                "supplied": True,
                "ok": False,
                "status": "validation_failed",
                "path": repo_relative(manifest_path, repo_root),
                "declared_media_count": 0,
                "valid_media_count": 0,
                "matched_media_count": 0,
                "issue_count": 1,
                "issues": [{"path": repo_relative(manifest_path, repo_root), "status": "invalid_json", "note": error or ""}],
            },
            {},
        )

    entries = payload.get("media")
    if not isinstance(entries, list):
        return (
            {
                "schema": MANIFEST_SCHEMA,
                "supplied": True,
                "ok": False,
                "status": "validation_failed",
                "path": repo_relative(manifest_path, repo_root),
                "declared_media_count": 0,
                "valid_media_count": 0,
                "matched_media_count": 0,
                "issue_count": 1,
                "issues": [
                    {
                        "path": repo_relative(manifest_path, repo_root),
                        "status": "invalid_media_list",
                        "note": "Manifest must contain a media array.",
                    }
                ],
            },
            {},
        )

    manifest_schema = str(payload.get("schema") or MANIFEST_SCHEMA)
    by_path: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    if manifest_schema != MANIFEST_SCHEMA:
        issues.append(
            {
                "path": repo_relative(manifest_path, repo_root),
                "status": "unexpected_schema",
                "note": f"Expected {MANIFEST_SCHEMA}, got {manifest_schema}.",
            }
        )
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append({"path": f"media[{index}]", "status": "invalid_entry", "note": "Media entry must be an object."})
            continue
        relative_path, issue = manifest_path_issue(entry.get("relative_path"), repo_root)
        if issue is not None:
            issues.append(issue)
            continue
        assert relative_path is not None
        if relative_path in by_path:
            issues.append({"path": relative_path, "status": "duplicate_entry", "note": "Duplicate manifest media path."})
            continue
        by_path[relative_path] = manifest_metadata(entry)

    return (
        {
            "schema": manifest_schema,
            "supplied": True,
            "ok": not issues,
            "status": "ok" if not issues else "validation_failed",
            "path": repo_relative(manifest_path, repo_root),
            "declared_media_count": len(entries),
            "valid_media_count": len(by_path),
            "matched_media_count": 0,
            "issue_count": len(issues),
            "issues": issues,
            "manifest_notes": payload.get("notes") if isinstance(payload.get("notes"), list) else [],
        },
        by_path,
    )


def text_candidate_keywords(path: Path) -> list[str]:
    text = path.as_posix().lower()
    path_hits = {keyword for keyword in CALIBRATION_DATA_KEYWORDS if keyword in text}
    content_hits: set[str] = set()
    try:
        with path.open("rb") as handle:
            chunk = handle.read(TEXT_SCAN_BYTES)
    except OSError:
        return sorted(path_hits)
    try:
        decoded = chunk.decode("utf-8", errors="ignore").lower()
    except Exception:
        decoded = ""
    content_hits.update(keyword for keyword in CALIBRATION_DATA_KEYWORDS if keyword in decoded)
    return sorted(path_hits | content_hits)


def is_candidate_path(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in MEDIA_EXTENSIONS:
        return True
    if suffix in CALIBRATION_DATA_EXTENSIONS:
        if path.name in EXCLUDED_CALIBRATION_DATA_FILENAMES:
            return False
        if any(part in EXCLUDED_CALIBRATION_DATA_PARTS for part in path.parts):
            return False
        return bool(text_candidate_keywords(path))
    return False


def iter_root_files(root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    resolved_root = root.expanduser().resolve()
    if not resolved_root.exists():
        return [], [{"path": str(resolved_root), "status": "missing", "note": "Scan root does not exist."}]
    if resolved_root.is_file():
        return ([resolved_root] if is_candidate_path(resolved_root) else []), issues
    if not os.access(resolved_root, os.R_OK):
        return [], [{"path": str(resolved_root), "status": "unreadable", "note": "Scan root is not readable."}]

    files: list[Path] = []

    def on_error(error: OSError) -> None:
        issues.append({"path": error.filename or str(resolved_root), "status": "walk_error", "note": str(error)})

    for directory, dir_names, file_names in os.walk(resolved_root, topdown=True, onerror=on_error, followlinks=False):
        directory_path = Path(directory)
        dir_names[:] = sorted(name for name in dir_names if name not in EXCLUDED_DIR_NAMES)
        for name in sorted(file_names):
            path = directory_path / name
            if is_excluded(relative_or_self(path, resolved_root)) or not path.is_file():
                continue
            if is_candidate_path(path):
                files.append(path.resolve())
    return files, issues


def iter_candidate_media(
    repo_root: Path,
    scan_roots: list[Path],
    includes: list[Path] | None,
) -> tuple[list[CandidateFile], list[dict[str, str]]]:
    candidates: list[CandidateFile] = []
    scan_issues: list[dict[str, str]] = []

    for raw_root in scan_roots:
        expanded_root = raw_root.expanduser()
        root = expanded_root.resolve() if expanded_root.is_absolute() else (repo_root / expanded_root).resolve()
        include_paths = includes
        if include_paths:
            expanded_roots = [
                include if include.is_absolute() else (repo_root / include).resolve()
                for include in include_paths
            ]
        else:
            expanded_roots = [root]

        for scan_root in expanded_roots:
            files, issues = iter_root_files(scan_root)
            scan_issues.extend(issues)
            for path in files:
                candidates.append(CandidateFile(path=path, scan_root=scan_root.resolve()))

    by_path: dict[Path, CandidateFile] = {}
    for candidate in candidates:
        by_path.setdefault(candidate.path.resolve(), candidate)
    unique = sorted(
        by_path.values(),
        key=lambda candidate: (
            root_relative(candidate.path, candidate.scan_root),
            str(candidate.scan_root),
            str(candidate.path),
        ),
    )
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


def png_dimensions(data: bytes) -> dict[str, Any] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = struct.unpack(">II", data[16:24])
        return {
            "width": int(width),
            "height": int(height),
            "metadata_source": "stdlib_png_header",
        }
    return None


def bmp_dimensions(data: bytes) -> dict[str, Any] | None:
    if len(data) >= 26 and data.startswith(b"BM"):
        width = struct.unpack("<I", data[18:22])[0]
        height = abs(struct.unpack("<i", data[22:26])[0])
        return {
            "width": int(width),
            "height": int(height),
            "metadata_source": "stdlib_bmp_header",
        }
    return None


def jpeg_dimensions(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"\xff\xd8":
                return None
            while True:
                marker_start = handle.read(1)
                if not marker_start:
                    return None
                if marker_start != b"\xff":
                    continue
                marker = handle.read(1)
                while marker == b"\xff":
                    marker = handle.read(1)
                if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"}:
                    segment_length = struct.unpack(">H", handle.read(2))[0]
                    if segment_length < 7:
                        return None
                    _precision = handle.read(1)
                    height, width = struct.unpack(">HH", handle.read(4))
                    channels = handle.read(1)[0]
                    return {
                        "width": int(width),
                        "height": int(height),
                        "channels": int(channels),
                        "metadata_source": "stdlib_jpeg_header",
                    }
                if marker in {b"\xd9", b"\xda"}:
                    return None
                length_bytes = handle.read(2)
                if len(length_bytes) != 2:
                    return None
                segment_length = struct.unpack(">H", length_bytes)[0]
                if segment_length < 2:
                    return None
                handle.seek(segment_length - 2, os.SEEK_CUR)
    except OSError:
        return None


def stdlib_image_metadata(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        metadata = jpeg_dimensions(path)
        if metadata is not None:
            return metadata
    try:
        data = path.read_bytes()[:64]
    except OSError as exc:
        return {"metadata_error": f"Could not read image header: {exc}"}
    for parser in (png_dimensions, bmp_dimensions):
        metadata = parser(data)
        if metadata is not None:
            return {
                "channels": None,
                **metadata,
            }
    return {"metadata_error": "Pillow unavailable and stdlib header parser does not support this image format."}


def image_metadata(path: Path) -> dict[str, Any]:
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
    return stdlib_image_metadata(path)


def parse_frame_rate(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            denominator_float = float(denominator)
            return float(numerator) / denominator_float if denominator_float else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def ffprobe_video_metadata(path: Path) -> dict[str, Any] | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,nb_frames,duration",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=10)
    except Exception as exc:
        return {"metadata_error": f"ffprobe failed to run: {exc}"}
    if result.returncode != 0:
        return {"metadata_error": f"ffprobe failed: {result.stderr.strip()}"}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"metadata_error": f"ffprobe returned invalid JSON: {exc}"}
    streams = payload.get("streams") if isinstance(payload, dict) else None
    stream = streams[0] if isinstance(streams, list) and streams and isinstance(streams[0], dict) else {}
    format_payload = payload.get("format") if isinstance(payload, dict) and isinstance(payload.get("format"), dict) else {}
    duration_raw = stream.get("duration") or format_payload.get("duration")
    try:
        duration = float(duration_raw) if duration_raw not in {None, "N/A", ""} else None
    except (TypeError, ValueError):
        duration = None
    try:
        frame_count = int(stream["nb_frames"]) if stream.get("nb_frames") not in {None, "N/A", ""} else None
    except (TypeError, ValueError):
        frame_count = None
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": parse_frame_rate(stream.get("avg_frame_rate")),
        "frame_count": frame_count,
        "duration_seconds": duration,
        "metadata_source": "ffprobe",
    }


def video_metadata(path: Path) -> dict[str, Any]:
    ffprobe_metadata = ffprobe_video_metadata(path)
    if ffprobe_metadata is not None:
        return ffprobe_metadata

    cv2 = cv2_module()
    if cv2 is None:
        return {"metadata_error": "ffprobe/OpenCV unavailable; video dimensions/duration not read."}

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
    if suffix in CALIBRATION_DATA_EXTENSIONS:
        return "calibration_data"
    return "unknown"


def calibration_data_metadata(path: Path) -> dict[str, Any]:
    keywords = text_candidate_keywords(path)
    return {
        "metadata_source": "limited_text_keyword_scan",
        "keyword_hits": keywords,
        "bytes_scanned": TEXT_SCAN_BYTES,
        "note": "Only a small text prefix is scanned; no binary or broad schema parsing is performed.",
    }


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
    if media_type == "calibration_data":
        tags.add("calibration_data")
    return sorted(tags)


def reference_classifications(relative_path: str, media_type: str, metadata: dict[str, Any]) -> tuple[list[str], list[str]]:
    haystack_parts = [relative_path.lower(), media_type.lower()]
    keyword_hits = metadata.get("keyword_hits")
    if isinstance(keyword_hits, list):
        haystack_parts.extend(str(hit).lower() for hit in keyword_hits)
    haystack = " ".join(haystack_parts)
    classes: set[str] = set()
    reasons: list[str] = []
    for class_name, keywords in REFERENCE_CLASS_KEYWORDS.items():
        hits = sorted({keyword for keyword in keywords if keyword in haystack})
        if hits:
            classes.add(class_name)
            reasons.append(f"{class_name}: matched {', '.join(hits[:5])}")
    if media_type == "video":
        classes.add("camera_pov")
        reasons.append("camera_pov: video candidate can provide temporal POV evidence")
    if "current_view" in haystack:
        classes.update({"camera_pov", "chessboard_board", "gripper_arm"})
        reasons.append("current_view: treated as active gripper-camera board reference")
    if not classes:
        classes.add("unknown")
        reasons.append("unknown: no calibration-relevant path/name/content keywords matched")
    return sorted(classes), reasons


def utility_categories(tags: list[str], media_type: str, reference_classes: list[str]) -> dict[str, str]:
    tag_set = set(tags)
    class_set = set(reference_classes)
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
        if "camera_pov" in tag_set or "camera_pov" in class_set:
            categories["camera_pov"] = "candidate"
        if "board" in tag_set or "chessboard_board" in class_set:
            categories["board_corners"] = "candidate"
            categories["piece_scale"] = "candidate"
            categories["workspace_geometry"] = "candidate"
        if "gripper" in tag_set or "gripper_arm" in class_set:
            categories["gripper_visibility"] = "candidate"
        if media_type == "image":
            categories["lighting"] = "candidate"
        if "calibration_target" in class_set:
            categories["camera_pov"] = "candidate"
            categories["board_corners"] = "candidate"
            categories["workspace_geometry"] = "candidate"
        if "depth_distance" in class_set:
            categories["workspace_geometry"] = "candidate"
        if "failure_mode" in tag_set:
            categories["failure_mode"] = "candidate"
    return categories


def calibration_notes(
    relative_path: str,
    tags: list[str],
    utilities: dict[str, str],
    wired_refs: list[SimulatorReference],
    declared_metadata: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    if any(ref.relative_path == relative_path for ref in wired_refs):
        profiles = sorted({ref.profile for ref in wired_refs if ref.relative_path == relative_path})
        notes.append(f"Wired into simulator profile(s): {', '.join(profiles)}.")
    if declared_metadata:
        notes.append("Manifest metadata declares intended calibration coverage for this media.")
    if "active_current_gripper_reference" in tags:
        notes.append(
            "Active current gripper reference: useful for camera POV, board-corner placement, piece scale, "
            "gripper overlay placement, workspace geometry, and lighting calibration."
        )
    if utilities["failure_mode"] in {"gap", "not_indicated"}:
        notes.append("Does not appear to document a failure mode from path/name heuristics.")
    return notes


def apply_declared_utility(
    utilities: dict[str, str],
    declared_metadata: dict[str, Any] | None,
) -> dict[str, str]:
    if not declared_metadata:
        return utilities
    updated = dict(utilities)
    for category in declared_metadata.get("declared_target_categories", []):
        if category in updated:
            updated[category] = "declared"
    return updated


def build_media_record(
    candidate: CandidateFile,
    repo_root: Path,
    wired_refs: list[SimulatorReference],
    manifest_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    path = candidate.path
    relative_path = record_relative_path(path, repo_root)
    root_relative_label = root_relative(path, candidate.scan_root)
    media_type = infer_media_type(path)
    if media_type == "image":
        metadata = image_metadata(path)
    elif media_type == "video":
        metadata = video_metadata(path)
    elif media_type == "calibration_data":
        metadata = calibration_data_metadata(path)
    else:
        metadata = {"metadata_error": "Unsupported candidate type."}
    heuristic_tags = inferred_tags(relative_path, media_type)
    declared_metadata = manifest_records.get(relative_path)
    declared_tags = normalize_string_list(declared_metadata.get("declared_tags")) if declared_metadata else []
    declared_category_tags = declared_metadata.get("declared_target_categories", []) if declared_metadata else []
    tags = sorted(set(heuristic_tags) | set(declared_tags) | set(declared_category_tags))
    classes, class_reasons = reference_classifications(relative_path, media_type, metadata)
    utilities = apply_declared_utility(utility_categories(tags, media_type, classes), declared_metadata)
    matching_refs = [ref for ref in wired_refs if ref.relative_path == relative_path]
    dimensions = {
        "width": metadata.get("width") if media_type in {"image", "video"} else None,
        "height": metadata.get("height") if media_type in {"image", "video"} else None,
        "channels": metadata.get("channels") if media_type == "image" else None,
    }

    return {
        "relative_path": relative_path,
        "path": str(path.resolve()),
        "root": str(candidate.scan_root.resolve()),
        "root_relative_path": root_relative_label,
        "path_scope": "repo_local" if is_repo_local(path, repo_root) else "external",
        "media_type": media_type,
        "mime_type": mimetypes.guess_type(path.name)[0],
        "extension": path.suffix.lower(),
        "file_size_bytes": int(path.stat().st_size),
        "dimensions": dimensions,
        "duration_seconds": metadata.get("duration_seconds"),
        "metadata": metadata,
        "reference_classes": classes,
        "reference_class_labels": [REFERENCE_CLASS_LABELS[class_name] for class_name in classes],
        "classification_reasons": class_reasons,
        "inferred_tags": heuristic_tags,
        "declared_tags": declared_tags,
        "reference_tags": tags,
        "tagging_basis": (
            "heuristic_path_and_filename_plus_manifest"
            if declared_metadata
            else "heuristic_path_and_filename"
        ),
        "declared_metadata": declared_metadata,
        "manifest_validation": {
            "declared": declared_metadata is not None,
            "status": "matched" if declared_metadata is not None else "not_declared",
        },
        "calibration_utility": utilities,
        "calibration_utility_notes": calibration_notes(
            relative_path,
            tags,
            utilities,
            wired_refs,
            declared_metadata,
        ),
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
            if utilities.get(category) in {"useful", "candidate", "declared"}:
                coverage[category].append(record["relative_path"])
    return {key: sorted(value) for key, value in coverage.items()}


def records_with_class(records: list[dict[str, Any]], class_name: str) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if class_name in set(record.get("reference_classes") if isinstance(record.get("reference_classes"), list) else [])
    ]


def is_pick_place_video(record: dict[str, Any]) -> bool:
    if record.get("media_type") != "video":
        return False
    text = " ".join(
        str(value).lower()
        for value in (
            record.get("relative_path"),
            record.get("root_relative_path"),
            record.get("path"),
            " ".join(record.get("reference_tags") or []),
            " ".join(record.get("reference_classes") or []),
        )
    )
    return any(token in text for token in ("pick", "place", "grasp", "release", "move", "motion", "recovery"))


def is_example_or_synthetic_record(record: dict[str, Any]) -> bool:
    text = " ".join(
        str(value).lower()
        for value in (
            record.get("relative_path"),
            record.get("root_relative_path"),
            record.get("path"),
        )
    )
    return any(token in text for token in ("synthetic", ".example", "example_", "/test_data/", "test_data/"))


def gap_eligible_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if not is_example_or_synthetic_record(record)]


def reference_gap_ids(records: list[dict[str, Any]]) -> list[str]:
    eligible_records = gap_eligible_records(records)
    classes_by_record = [
        set(record.get("reference_classes") if isinstance(record.get("reference_classes"), list) else [])
        for record in eligible_records
    ]
    missing: list[str] = []
    has_gripper_pov = any({"camera_pov", "gripper_arm"} <= classes for classes in classes_by_record)
    has_board = any("chessboard_board" in classes for classes in classes_by_record)
    has_depth = any("depth_distance" in classes for classes in classes_by_record)
    has_calibration_target = any("calibration_target" in classes for classes in classes_by_record)
    has_pick_place = any(is_pick_place_video(record) for record in eligible_records)
    if not has_gripper_pov:
        missing.append("missing_gripper_pov")
    if not has_board:
        missing.append("missing_board_closeup")
    if not has_depth:
        missing.append("missing_depth_reference")
    if not has_calibration_target:
        missing.append("missing_calibration_target")
    if not has_pick_place:
        missing.append("missing_pick_place_video")
    return missing


def visibility_gaps(records: list[dict[str, Any]], wired_refs: list[SimulatorReference]) -> list[dict[str, str]]:
    coverage = category_coverage(records)
    gaps: list[dict[str, str]] = []
    explicit_missing = set(reference_gap_ids(records))
    for gap_id, note in REFERENCE_GAP_DEFINITIONS:
        if gap_id in explicit_missing:
            gaps.append(
                {
                    "category": gap_id,
                    "status": "missing",
                    "note": note,
                }
            )
    for category, paths in coverage.items():
        if not paths:
            gaps.append(
                {
                    "category": category,
                    "status": "missing",
                    "note": "No found media was heuristically or manifest-declared useful for this reference category.",
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
    scan_roots = args.root if args.root else [repo_root]
    includes = args.include
    wired_refs, simulator_reference_issues = simulator_reference_paths(repo_root)
    manifest_summary, manifest_records = load_reference_media_manifest(args.manifest, repo_root)
    candidates, scan_issues = iter_candidate_media(repo_root, scan_roots, includes)
    if manifest_records:
        manifest_candidates = [
            CandidateFile(path=(repo_root / relative_path).resolve(), scan_root=repo_root)
            for relative_path in manifest_records
        ]
        by_path = {candidate.path.resolve(): candidate for candidate in candidates}
        for candidate in manifest_candidates:
            by_path.setdefault(candidate.path.resolve(), candidate)
        candidates = sorted(
            by_path.values(),
            key=lambda candidate: (
                record_relative_path(candidate.path, repo_root),
                root_relative(candidate.path, candidate.scan_root),
            ),
        )
    records = [build_media_record(candidate, repo_root, wired_refs, manifest_records) for candidate in candidates]
    matched_manifest_paths = {
        record["relative_path"] for record in records if record["manifest_validation"]["declared"]
    }
    manifest_summary = {
        **manifest_summary,
        "matched_media_count": len(matched_manifest_paths),
        "unmatched_declared_media": sorted(set(manifest_records) - matched_manifest_paths),
    }
    coverage = category_coverage(records)
    active_path = "archive/chess_test_images/current_view.jpg"
    active_records = [record for record in records if record["relative_path"] == active_path]
    videos = [record for record in records if record["media_type"] == "video"]
    reference_gaps = reference_gap_ids(records)
    classification_counts = {
        class_name: len(records_with_class(records, class_name))
        for class_name in REFERENCE_CLASS_LABELS
    }
    status = "media_inventory_complete" if records else "media_inventory_empty"

    return {
        "schema": SCHEMA,
        "ok": bool(manifest_summary.get("ok", True)),
        "status": status,
        "repo_root": str(repo_root),
        "output_path": str(args.output_dir.expanduser().resolve() / args.output_name),
        "hardware_skipped": True,
        "gui_skipped": True,
        "scan": {
            "roots": [
                str((root.expanduser().resolve() if root.expanduser().is_absolute() else (repo_root / root.expanduser()).resolve()))
                for root in scan_roots
            ],
            "include_paths": [path.as_posix() for path in includes] if includes else [],
            "default_scan_scope": "repo_root_only" if args.root is None else "explicit_roots",
            "media_extensions": sorted(MEDIA_EXTENSIONS),
            "calibration_data_extensions": sorted(CALIBRATION_DATA_EXTENSIONS),
            "candidate_extensions": sorted(CANDIDATE_EXTENSIONS),
            "excluded_dir_names": sorted(EXCLUDED_DIR_NAMES),
            "scan_issues": scan_issues,
        },
        "manifest_summary": manifest_summary,
        "simulator_reference_paths": [
            {"profile": ref.profile, "key": ref.key, "relative_path": ref.relative_path} for ref in wired_refs
        ],
        "simulator_reference_issues": simulator_reference_issues,
        "summary": {
            "status": status,
            "candidate_count": len(records),
            "media_count": len(records),
            "image_count": sum(1 for record in records if record["media_type"] == "image"),
            "video_count": len(videos),
            "calibration_data_count": sum(1 for record in records if record["media_type"] == "calibration_data"),
            "currently_wired_media_count": sum(
                1 for record in records if record["currently_wired_into_simulator_tooling"]
            ),
            "manifest_declared_media_count": sum(
                1 for record in records if record["manifest_validation"]["declared"]
            ),
            "manifest_validation_status": manifest_summary["status"],
            "active_current_gripper_reference_detected": bool(active_records),
            "active_current_gripper_reference_path": active_path,
            "coverage": coverage,
            "reference_classification_counts": classification_counts,
            "reference_gaps": reference_gaps,
            "videos_present": bool(videos),
            "has_enough_real_pov_evidence": not any(
                gap in set(reference_gaps)
                for gap in (
                    "missing_gripper_pov",
                    "missing_board_closeup",
                    "missing_depth_reference",
                    "missing_calibration_target",
                    "missing_pick_place_video",
                )
            ),
        },
        "media": records,
        "visibility_gaps": visibility_gaps(records, wired_refs),
        "reference_gaps": reference_gaps,
        "next_recommended_reference_fixture_inputs": [
            record["relative_path"]
            for record in records
            if record["currently_wired_into_simulator_tooling"]
            or "active_current_gripper_reference" in record["inferred_tags"]
        ],
        "notes": [
            "Default tags and calibration utility are heuristic, based on path/name and simulator wiring.",
            "When a manifest is supplied, declared metadata is merged into reference_tags and calibration_utility.",
            "The root/path fields may point at optional local sibling evidence; this script does not copy or modify media assets.",
            "This inventory reports found candidates only; it does not create thumbnails or calibration datasets.",
        ],
    }


def write_inventory_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "path",
        "root",
        "root_relative_path",
        "relative_path",
        "path_scope",
        "media_type",
        "extension",
        "file_size_bytes",
        "width",
        "height",
        "channels",
        "duration_seconds",
        "metadata_source",
        "reference_classes",
        "classification_reasons",
        "currently_wired_into_simulator_tooling",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in sorted(records, key=lambda item: (str(item.get("root") or ""), str(item.get("root_relative_path") or ""))):
            dimensions = record.get("dimensions") if isinstance(record.get("dimensions"), dict) else {}
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            writer.writerow(
                {
                    "path": record.get("path"),
                    "root": record.get("root"),
                    "root_relative_path": record.get("root_relative_path"),
                    "relative_path": record.get("relative_path"),
                    "path_scope": record.get("path_scope"),
                    "media_type": record.get("media_type"),
                    "extension": record.get("extension"),
                    "file_size_bytes": record.get("file_size_bytes"),
                    "width": dimensions.get("width"),
                    "height": dimensions.get("height"),
                    "channels": dimensions.get("channels"),
                    "duration_seconds": record.get("duration_seconds"),
                    "metadata_source": metadata.get("metadata_source"),
                    "reference_classes": ";".join(record.get("reference_classes") or []),
                    "classification_reasons": " | ".join(record.get("classification_reasons") or []),
                    "currently_wired_into_simulator_tooling": record.get("currently_wired_into_simulator_tooling"),
                }
            )


def markdown_list(items: list[str]) -> list[str]:
    if not items:
        return ["- None."]
    return [f"- `{item}`" for item in items]


def write_inventory_readme(path: Path, inventory: dict[str, Any], csv_path: Path) -> None:
    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    scan = inventory.get("scan") if isinstance(inventory.get("scan"), dict) else {}
    roots = scan.get("roots") if isinstance(scan.get("roots"), list) else []
    gaps = inventory.get("reference_gaps") if isinstance(inventory.get("reference_gaps"), list) else []
    media = inventory.get("media") if isinstance(inventory.get("media"), list) else []
    wired = [
        str(record.get("relative_path"))
        for record in media
        if isinstance(record, dict) and record.get("currently_wired_into_simulator_tooling")
    ]
    lines = [
        "# Simulator Reference Media Inventory",
        "",
        f"- Status: `{inventory.get('status')}`",
        f"- Candidate count: `{summary.get('candidate_count', 0)}`",
        f"- Image count: `{summary.get('image_count', 0)}`",
        f"- Video count: `{summary.get('video_count', 0)}`",
        f"- Calibration-data count: `{summary.get('calibration_data_count', 0)}`",
        f"- JSON: `{Path(str(inventory.get('output_path'))).name}`",
        f"- CSV: `{csv_path.name}`",
        "",
        "## Roots Scanned",
        "",
        *markdown_list([str(root) for root in roots]),
        "",
        "## Reference Gaps",
        "",
        *markdown_list([str(gap) for gap in gaps]),
        "",
        "## Simulator Wiring",
        "",
        *markdown_list(sorted(wired)),
        "",
        "## Renderer Guidance",
        "",
        "Use repo-local or sibling media paths as review references for synthetic camera frames, board appearance, gripper occlusion, and workspace geometry. Keep large source photos/videos outside this PR unless they are intentionally small fixtures; future renderer work should point to reviewed local evidence, record provenance in a manifest, and preserve explicit gaps instead of inventing calibration truth.",
        "",
        "This inventory is hardware-free and deterministic. Missing dimensions, durations, or calibration sidecars are reported as metadata gaps and do not fail the scan.",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory(args)
    output_path = output_dir / args.output_name
    csv_path = output_dir / "reference_media_inventory.csv"
    readme_path = output_dir / "README.md"
    inventory["output_path"] = str(output_path)
    inventory["csv_path"] = str(csv_path)
    inventory["readme_path"] = str(readme_path)
    output_path.write_text(json.dumps(inventory, indent=2) + "\n")
    write_inventory_csv(csv_path, inventory["media"])
    write_inventory_readme(readme_path, inventory, csv_path)
    print(json.dumps(inventory, indent=2))
    return 0 if inventory["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
