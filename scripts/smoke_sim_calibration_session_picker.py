#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lerobot.sim import load_ranked_sim_calibration_session  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test ranked simulator calibration session listing and selection."
    )
    parser.add_argument("summary_path", type=Path)
    parser.add_argument("--select-rank", type=int, default=1)
    parser.add_argument("--select-candidate-id", default=None)
    parser.add_argument("--expect-count", type=int, default=None)
    parser.add_argument("--expect-ranks", default=None, help="Comma-separated rank list, for example 1,2.")
    parser.add_argument(
        "--expect-fields",
        action="store_true",
        help="Assert candidate id, score/penalty, paths, corners, profile, and reference image metadata are present.",
    )
    return parser.parse_args()


def required_fields_ok(candidate: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in (
        "candidate_id",
        "rank_score",
        "total_penalty",
        "candidate_path",
        "candidate_artifact_dir",
        "artifact_paths",
        "board_corners_xy",
        "base_profile",
        "reference_image_path",
    ):
        value = candidate.get(key)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(key)
    corners = candidate.get("board_corners_xy")
    if not isinstance(corners, list) or len(corners) != 4:
        missing.append("board_corners_xy[4]")
    return missing


def main() -> int:
    args = parse_args()
    try:
        session = load_ranked_sim_calibration_session(args.summary_path)
        selected = session.select(
            rank=int(args.select_rank),
            candidate_id=str(args.select_candidate_id) if args.select_candidate_id else None,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = session.to_jsonable()
    payload["selected"] = selected.to_jsonable()

    if args.expect_count is not None and payload["candidate_count"] != int(args.expect_count):
        print(
            f"ERROR: expected {args.expect_count} ranked candidates, got {payload['candidate_count']}",
            file=sys.stderr,
        )
        return 1

    if args.expect_ranks:
        expected_ranks = [int(item.strip()) for item in args.expect_ranks.split(",") if item.strip()]
        actual_ranks = [int(candidate["rank"]) for candidate in payload["candidates"]]
        if actual_ranks != expected_ranks:
            print(f"ERROR: expected ranks {expected_ranks}, got {actual_ranks}", file=sys.stderr)
            return 1

    if args.expect_fields:
        for candidate in payload["candidates"]:
            missing = required_fields_ok(candidate)
            if missing:
                print(
                    f"ERROR: candidate {candidate.get('candidate_id')} missing required fields: {missing}",
                    file=sys.stderr,
                )
                return 1

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
