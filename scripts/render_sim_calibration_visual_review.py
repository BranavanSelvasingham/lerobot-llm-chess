#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SCHEMA = "lerobot.sim.calibration_visual_review.v1"
DEFAULT_CONTACT_SHEET_CELL_WIDTH = 360
DEFAULT_VIDEO_FPS = 1.0
VIDEO_CODEC = "mp4v"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render durable PNG visual-review artifacts from an existing simulator "
            "calibration regression suite summary."
        )
    )
    parser.add_argument(
        "suite_summary",
        type=Path,
        help="Path to calibration_regression_summary.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to visual_review beside the suite summary.",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        default=DEFAULT_CONTACT_SHEET_CELL_WIDTH,
        help="Maximum image cell width for contact sheets.",
    )
    parser.add_argument(
        "--try-video",
        action="store_true",
        help="Best-effort MP4 from gripper POV annotated frames; skipped cleanly if unavailable.",
    )
    parser.add_argument(
        "--video-fps",
        type=float,
        default=DEFAULT_VIDEO_FPS,
        help="FPS for optional gripper POV review video.",
    )
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


def resolve_path(value: str, *, suite_summary_path: Path, output_dir: Path, repo_root: Path | None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    output_candidate = (output_dir / path).resolve()
    if output_candidate.exists():
        return output_candidate

    if repo_root is not None:
        repo_candidate = (repo_root / path).resolve()
        if repo_candidate.exists():
            return repo_candidate

    return (suite_summary_path.parent / path).resolve()


def output_relative(path: Path, output_dir: Path) -> str | None:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return None


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"OpenCV could not read image {path}.")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected BGR image with 3 channels at {path}, got shape {image.shape}.")
    return image


def write_image(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image_bgr)
    if not ok:
        raise ValueError(f"OpenCV could not write image {path}.")


def resize_to_max_width(image_bgr: np.ndarray, max_width: int) -> np.ndarray:
    if max_width <= 0:
        raise ValueError("--cell-width must be positive.")
    height, width = image_bgr.shape[:2]
    if width <= max_width:
        return image_bgr.copy()
    scale = float(max_width) / float(width)
    target = (max_width, max(1, int(round(height * scale))))
    return cv2.resize(image_bgr, target, interpolation=cv2.INTER_AREA)


def labeled_image(image_bgr: np.ndarray, *, label: str, detail: str = "") -> np.ndarray:
    label_height = 48 if detail else 30
    height, width = image_bgr.shape[:2]
    out = np.zeros((height + label_height, width, 3), dtype=np.uint8)
    out[:, :] = (18, 18, 18)
    out[label_height:, :] = image_bgr
    cv2.putText(out, label, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    if detail:
        cv2.putText(out, detail, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (205, 220, 255), 1, cv2.LINE_AA)
    return out


def ordered_path_rows(
    section: dict[str, Any],
    *,
    collection_key: str,
    ids_key: str,
    suite_summary_path: Path,
    suite_output_dir: Path,
    repo_root: Path | None,
) -> list[dict[str, Any]]:
    paths = section.get(collection_key)
    if not isinstance(paths, dict) or not paths:
        return []

    ordered_ids: list[str] = []
    ids = section.get(ids_key)
    if isinstance(ids, list):
        ordered_ids.extend(str(value) for value in ids if str(value) in paths)
    ordered_ids.extend(sorted(str(key) for key in paths if str(key) not in set(ordered_ids)))

    rows: list[dict[str, Any]] = []
    for item_id in ordered_ids:
        value = paths.get(item_id)
        if not isinstance(value, str) or not value:
            continue
        resolved = resolve_path(
            value,
            suite_summary_path=suite_summary_path,
            output_dir=suite_output_dir,
            repo_root=repo_root,
        )
        rows.append({"id": item_id, "path": resolved, "path_value": value})
    return rows


def make_contact_sheet(
    rows: list[dict[str, Any]],
    *,
    title: str,
    output_path: Path,
    suite_output_dir: Path,
    cell_width: int,
) -> dict[str, Any]:
    if not rows:
        raise ValueError(f"No source frames found for contact sheet {title!r}.")

    cells: list[np.ndarray] = []
    source_paths: list[str] = []
    labels: list[str] = []
    for row in rows:
        path = Path(row["path"])
        if not path.is_file():
            raise ValueError(f"Source frame for {title!r} does not exist: {path}")
        source = read_image(path)
        resized = resize_to_max_width(source, cell_width)
        detail = output_relative(path, suite_output_dir) or str(path)
        cell = labeled_image(resized, label=str(row["id"]), detail=detail)
        cells.append(cell)
        source_paths.append(str(path))
        labels.append(str(row["id"]))

    columns = min(len(cells), 6)
    row_count = int(math.ceil(len(cells) / float(columns)))
    cell_w = max(int(cell.shape[1]) for cell in cells)
    cell_h = max(int(cell.shape[0]) for cell in cells)
    gap = 8
    title_h = 42
    sheet_w = columns * cell_w + (columns + 1) * gap
    sheet_h = title_h + row_count * cell_h + (row_count + 1) * gap
    sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
    sheet[:, :] = (32, 32, 32)
    cv2.putText(sheet, title, (gap, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 1, cv2.LINE_AA)

    for index, cell in enumerate(cells):
        row_index = index // columns
        column_index = index % columns
        x = gap + column_index * (cell_w + gap)
        y = title_h + gap + row_index * (cell_h + gap)
        sheet[y : y + cell.shape[0], x : x + cell.shape[1]] = cell

    write_image(output_path, sheet)
    return {
        "path": str(output_path),
        "relative_path": output_relative(output_path, suite_output_dir),
        "label": title,
        "source_frame_count": len(rows),
        "source_frame_labels": labels,
        "source_frame_paths": source_paths,
        "output_dimensions": {
            "width_px": int(sheet.shape[1]),
            "height_px": int(sheet.shape[0]),
            "channels": int(sheet.shape[2]),
        },
    }


def copy_app_entrypoint_frame(
    app_entrypoint: dict[str, Any],
    *,
    output_path: Path,
    suite_summary_path: Path,
    suite_output_dir: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    frame_path_value = app_entrypoint.get("frame_path")
    if not isinstance(frame_path_value, str) or not frame_path_value:
        raise ValueError("app_entrypoint_metadata.frame_path is not populated.")
    source_path = resolve_path(
        frame_path_value,
        suite_summary_path=suite_summary_path,
        output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    if not source_path.is_file():
        raise ValueError(f"App-entrypoint frame does not exist: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)
    image = read_image(output_path)
    return {
        "status": "ok",
        "source_path": str(source_path),
        "review_copy_path": str(output_path),
        "relative_path": output_relative(output_path, suite_output_dir),
        "output_dimensions": {
            "width_px": int(image.shape[1]),
            "height_px": int(image.shape[0]),
            "channels": int(image.shape[2]),
        },
    }


def video_frame(row: dict[str, Any], *, target_width: int | None) -> np.ndarray:
    image = read_image(Path(row["path"]))
    if target_width is not None:
        image = resize_to_max_width(image, target_width)
    detail = Path(row["path"]).name
    return labeled_image(image, label=str(row["id"]), detail=detail)


def render_optional_video(
    rows: list[dict[str, Any]],
    *,
    output_path: Path,
    fps: float,
    cell_width: int,
    try_video: bool,
) -> dict[str, Any]:
    if not try_video:
        return {
            "attempted": False,
            "produced": False,
            "path": None,
            "codec": None,
            "fps": None,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "not requested; PNG contact sheets are the CI-stable visual-review artifact",
        }
    if not rows:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "no gripper POV annotated frames were available",
        }
    if fps <= 0:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "--video-fps must be positive",
        }

    try:
        prepared = [video_frame(row, target_width=cell_width) for row in rows]
        frame_h, frame_w = prepared[0].shape[:2]
        normalized = [
            frame if frame.shape[:2] == (frame_h, frame_w) else cv2.resize(frame, (frame_w, frame_h), interpolation=cv2.INTER_AREA)
            for frame in prepared
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*VIDEO_CODEC),
            float(fps),
            (int(frame_w), int(frame_h)),
        )
        if not writer.isOpened():
            return {
                "attempted": True,
                "produced": False,
                "path": None,
                "codec": VIDEO_CODEC,
                "fps": fps,
                "frame_count": 0,
                "duration_seconds": 0.0,
                "skipped_reason": "OpenCV VideoWriter could not open an MP4 writer",
            }
        try:
            for frame in normalized:
                writer.write(frame)
        finally:
            writer.release()
    except (cv2.error, OSError, ValueError) as exc:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": f"OpenCV MP4 render failed: {exc}",
        }

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        return {
            "attempted": True,
            "produced": False,
            "path": None,
            "codec": VIDEO_CODEC,
            "fps": fps,
            "frame_count": 0,
            "duration_seconds": 0.0,
            "skipped_reason": "OpenCV reported success but no non-empty MP4 was written",
        }

    capture = cv2.VideoCapture(str(output_path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or len(rows))
        actual_fps = float(capture.get(cv2.CAP_PROP_FPS) or fps)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or frame_w)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or frame_h)
    finally:
        capture.release()
    duration = float(frame_count) / actual_fps if actual_fps > 0 else 0.0
    return {
        "attempted": True,
        "produced": True,
        "path": str(output_path),
        "codec": VIDEO_CODEC,
        "fps": actual_fps,
        "frame_count": frame_count,
        "duration_seconds": duration,
        "dimensions": {"width_px": width, "height_px": height},
        "skipped_reason": None,
    }


def build_summary(
    *,
    suite_summary_path: Path,
    output_dir: Path,
    cell_width: int,
    try_video: bool,
    video_fps: float,
) -> dict[str, Any]:
    suite = read_json_object(suite_summary_path, label="suite summary")
    suite_output_dir = Path(str(suite.get("output_dir") or suite_summary_path.parent)).expanduser().resolve()
    repo_root_value = suite.get("repo_root")
    repo_root = Path(repo_root_value).expanduser().resolve() if isinstance(repo_root_value, str) else None

    pose_fixture = suite.get("sim_camera_pose_fixture")
    pose_fixture = pose_fixture if isinstance(pose_fixture, dict) else {}
    pov = suite.get("gripper_camera_pov_review")
    pov = pov if isinstance(pov, dict) else {}
    app_entrypoint = suite.get("app_entrypoint_metadata")
    app_entrypoint = app_entrypoint if isinstance(app_entrypoint, dict) else {}

    contact_specs = [
        {
            "id": "gripper_camera_pov_annotated",
            "label": "Gripper POV Annotated Contact Sheet",
            "section": pov,
            "collection_key": "annotated_frame_paths",
            "ids_key": "state_ids",
            "output_name": "gripper_camera_pov_annotated_contact_sheet.png",
            "source": "gripper_camera_pov_review.annotated_frame_paths",
        },
        {
            "id": "gripper_camera_pov_raw",
            "label": "Gripper POV Raw Contact Sheet",
            "section": pov,
            "collection_key": "frame_paths",
            "ids_key": "state_ids",
            "output_name": "gripper_camera_pov_raw_contact_sheet.png",
            "source": "gripper_camera_pov_review.frame_paths",
        },
        {
            "id": "sim_camera_pose_fixture_annotated",
            "label": "SimCamera Pose Fixture Annotated Contact Sheet",
            "section": pose_fixture,
            "collection_key": "annotated_frame_paths",
            "ids_key": "case_ids",
            "output_name": "sim_camera_pose_fixture_annotated_contact_sheet.png",
            "source": "sim_camera_pose_fixture.annotated_frame_paths",
        },
        {
            "id": "sim_camera_pose_fixture_raw",
            "label": "SimCamera Pose Fixture Raw Contact Sheet",
            "section": pose_fixture,
            "collection_key": "frame_paths",
            "ids_key": "case_ids",
            "output_name": "sim_camera_pose_fixture_raw_contact_sheet.png",
            "source": "sim_camera_pose_fixture.frame_paths",
        },
    ]

    contact_sheets: list[dict[str, Any]] = []
    gripper_annotated_rows: list[dict[str, Any]] = []
    for spec in contact_specs:
        rows = ordered_path_rows(
            spec["section"],
            collection_key=str(spec["collection_key"]),
            ids_key=str(spec["ids_key"]),
            suite_summary_path=suite_summary_path,
            suite_output_dir=suite_output_dir,
            repo_root=repo_root,
        )
        if spec["id"] == "gripper_camera_pov_annotated":
            gripper_annotated_rows = rows
        sheet = make_contact_sheet(
            rows,
            title=str(spec["label"]),
            output_path=output_dir / str(spec["output_name"]),
            suite_output_dir=suite_output_dir,
            cell_width=cell_width,
        )
        sheet.update(
            {
                "id": spec["id"],
                "source": spec["source"],
                "source_collection": spec["collection_key"],
            }
        )
        contact_sheets.append(sheet)

    app_frame = copy_app_entrypoint_frame(
        app_entrypoint,
        output_path=output_dir / "app_entrypoint_frame.jpg",
        suite_summary_path=suite_summary_path,
        suite_output_dir=suite_output_dir,
        repo_root=repo_root,
    )
    recording = render_optional_video(
        gripper_annotated_rows,
        output_path=output_dir / "gripper_camera_pov_annotated_sequence.mp4",
        fps=float(video_fps),
        cell_width=int(cell_width),
        try_video=bool(try_video),
    )

    return {
        "schema": SCHEMA,
        "ok": True,
        "status": "ok",
        "summary_path": str(output_dir / "visual_review_summary.json"),
        "suite_summary_path": str(suite_summary_path),
        "output_dir": str(output_dir),
        "repo_root": str(repo_root) if repo_root else None,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "skipped_markers": {
            "hardware": "Visual review consumes generated simulator frames only; no SO-101 motors, serial ports, or camera devices are opened.",
            "gui": "Visual review writes image files directly and does not open display windows.",
            "openai": "Visual review is local image composition only; no OpenAI credentials or network calls are required.",
        },
        "contact_sheets": contact_sheets,
        "contact_sheet_paths": {str(sheet["id"]): str(sheet["path"]) for sheet in contact_sheets},
        "app_entrypoint_frame": app_frame,
        "recording": recording,
        "notes": [
            "Contact sheets are the stable review artifact and are generated from existing smoke frames.",
            "The optional MP4 is best-effort only and is not required for the suite to pass.",
            "No simulator pixels, camera profiles, perception algorithms, UI behavior, or robot paths are changed by this helper.",
        ],
    }


def failure_summary(output_dir: Path, suite_summary_path: Path, error: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "validation_failed",
        "summary_path": str(output_dir / "visual_review_summary.json"),
        "suite_summary_path": str(suite_summary_path),
        "output_dir": str(output_dir),
        "error": error,
        "contact_sheets": [],
        "contact_sheet_paths": {},
        "app_entrypoint_frame": None,
        "recording": {
            "attempted": False,
            "produced": False,
            "path": None,
            "skipped_reason": "visual review failed before optional video handling",
        },
    }


def main() -> int:
    args = parse_args()
    suite_summary_path = args.suite_summary.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else suite_summary_path.parent / "visual_review"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary = build_summary(
            suite_summary_path=suite_summary_path,
            output_dir=output_dir,
            cell_width=int(args.cell_width),
            try_video=bool(args.try_video),
            video_fps=float(args.video_fps),
        )
    except ValueError as exc:
        summary = failure_summary(output_dir, suite_summary_path, str(exc))
    write_json(output_dir / "visual_review_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
