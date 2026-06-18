#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smoke_sim_calibration_regression_suite import (  # noqa: E402
    REVIEWED_SO101_MODEL_AUTHORITY,
    so101_training_readiness_gate_section,
)

DEFAULT_OUTPUT_DIR = (
    Path("/private/tmp") / "lerobot_sim" / "so101_training_readiness_gate_matrix"
)
SCHEMA = "lerobot.sim.so101_training_readiness_gate_matrix.v1"
DEV_AUTHORITY = "development_scaffold_not_reviewed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a hardware-free contract matrix over the SO-101 serious-training "
            "readiness gate. Inputs are injected state dictionaries and are not "
            "policy-training authority."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing output directory before running.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "case_id",
        "ok",
        "gate_status",
        "gate_ready",
        "reviewed_model_authority_ready",
        "reviewed_model_backed_board_source_pick_place",
        "board_pick_reviewed_model_authority_ready",
        "rollout_ready_for_policy_training",
        "rollout_policy_training_authority_ready",
        "development_fixture_evidence_not_policy_training_truth",
        "blockers",
        "expected_gate_ready",
        "errors",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})


def reviewed_authority_ready(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_model_authority_ready",
        "ready": True,
        "blockers": [],
        "summary_path": str(summary_path),
    }


def reviewed_authority_blocked(summary_path: Path) -> dict[str, Any]:
    return {
        "status": "reviewed_model_authority_blocked",
        "ready": False,
        "blockers": [
            "supply_reviewed_so101_model_bundle_manifest",
            "prove_physical_reviewed_model_motion",
        ],
        "summary_path": str(summary_path),
    }


def board_pick_state(
    summary_path: Path,
    *,
    model_authority: str | None,
    ready_for_model_backed_ik: bool,
    seeded_source_pose: bool,
    manual_piece_pose_after_reset: bool = False,
    verified: bool = True,
) -> dict[str, Any]:
    return {
        "status": (
            "reviewed_model_backed_board_source_pick_place_verified"
            if model_authority == REVIEWED_SO101_MODEL_AUTHORITY
            and ready_for_model_backed_ik
            and not seeded_source_pose
            and not manual_piece_pose_after_reset
            and verified
            else "development_board_source_pick_place_verified"
            if verified
            else "board_source_pick_place_not_verified"
        ),
        "board_source_pick_place_verified": verified,
        "ready_for_model_backed_ik": ready_for_model_backed_ik,
        "model_authority": model_authority,
        "robot_pose_seeded_for_source_fixture": seeded_source_pose,
        "manual_piece_pose_used_after_reset": manual_piece_pose_after_reset,
        "summary_path": str(summary_path),
    }


def rollout_state(
    summary_path: Path,
    *,
    ready_for_policy_training: bool,
    model_authority: str | None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok" if ready_for_policy_training else "not_policy_ready",
        "ready_for_policy_training": ready_for_policy_training,
        "training_authority_status": (
            "reviewed_policy_training_rollouts_ready"
            if ready_for_policy_training
            and model_authority == REVIEWED_SO101_MODEL_AUTHORITY
            else "development_rollouts_prerequisites_verified_not_policy_ready"
            if model_authority == DEV_AUTHORITY
            else "reviewed_rollouts_not_ready"
        ),
        "model_authority": model_authority,
        "rollout_use": (
            "policy_training"
            if ready_for_policy_training
            and model_authority == REVIEWED_SO101_MODEL_AUTHORITY
            else "debug_imitation_curriculum_only"
        ),
        "serious_policy_training_blockers": blockers
        if blockers is not None
        else ([] if ready_for_policy_training else ["reviewed_model_backed_training_rollouts"]),
        "summary_path": str(summary_path),
    }


def case_specs(output_dir: Path) -> list[dict[str, Any]]:
    summaries = output_dir / "input_summaries"
    authority_ready = reviewed_authority_ready(summaries / "authority_ready.json")
    authority_blocked = reviewed_authority_blocked(summaries / "authority_blocked.json")
    board_dev = board_pick_state(
        summaries / "board_dev.json",
        model_authority=DEV_AUTHORITY,
        ready_for_model_backed_ik=False,
        seeded_source_pose=True,
    )
    board_reviewed = board_pick_state(
        summaries / "board_reviewed.json",
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
        ready_for_model_backed_ik=True,
        seeded_source_pose=False,
    )
    rollout_dev_blocked = rollout_state(
        summaries / "rollout_dev_blocked.json",
        ready_for_policy_training=False,
        model_authority=DEV_AUTHORITY,
        blockers=[
            "reviewed_so101_model_bundle",
            "reviewed_tcp_and_base_to_board_alignment",
            "reviewed_model_backed_board_source_pick_place",
        ],
    )
    rollout_reviewed_ready = rollout_state(
        summaries / "rollout_reviewed_ready.json",
        ready_for_policy_training=True,
        model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
    )
    return [
        {
            "case_id": "all_development_evidence_blocked",
            "authority": authority_blocked,
            "board": board_dev,
            "rollouts": rollout_dev_blocked,
            "expect": {
                "ready": False,
                "reviewed_authority": False,
                "board_pick": False,
                "board_authority": False,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": [
                    "supply_reviewed_so101_model_bundle_manifest",
                    "reviewed_model_backed_board_source_pick_place",
                ],
            },
        },
        {
            "case_id": "reviewed_authority_but_board_still_development",
            "authority": authority_ready,
            "board": board_dev,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
            },
        },
        {
            "case_id": "board_draft_authority_rejected",
            "authority": authority_ready,
            "board": board_pick_state(
                summaries / "board_draft.json",
                model_authority="draft_candidate_not_reviewed",
                ready_for_model_backed_ik=True,
                seeded_source_pose=False,
            ),
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": False,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
            },
        },
        {
            "case_id": "board_seeded_reviewed_authority_rejected",
            "authority": authority_ready,
            "board": board_pick_state(
                summaries / "board_seeded_reviewed.json",
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                ready_for_model_backed_ik=True,
                seeded_source_pose=True,
            ),
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
            },
        },
        {
            "case_id": "board_manual_reset_pose_reviewed_authority_rejected",
            "authority": authority_ready,
            "board": board_pick_state(
                summaries / "board_manual_reset_pose_reviewed.json",
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                ready_for_model_backed_ik=True,
                seeded_source_pose=False,
                manual_piece_pose_after_reset=True,
            ),
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": False,
                "board_authority": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_board_source_pick_place"],
            },
        },
        {
            "case_id": "rollout_raw_ready_development_authority_rejected",
            "authority": authority_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_raw_dev.json",
                ready_for_policy_training=True,
                model_authority=DEV_AUTHORITY,
                blockers=["reviewed_model_backed_training_rollouts"],
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "rollout_raw": True,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
            },
        },
        {
            "case_id": "rollout_reviewed_authority_not_ready",
            "authority": authority_ready,
            "board": board_reviewed,
            "rollouts": rollout_state(
                summaries / "rollout_reviewed_not_ready.json",
                ready_for_policy_training=False,
                model_authority=REVIEWED_SO101_MODEL_AUTHORITY,
                blockers=["reviewed_model_backed_training_rollouts"],
            ),
            "expect": {
                "ready": False,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "rollout_raw": False,
                "rollout_authority": False,
                "development_caveat": True,
                "blockers_contain": ["reviewed_model_backed_training_rollouts"],
            },
        },
        {
            "case_id": "all_ready_reviewed_contract_state",
            "authority": authority_ready,
            "board": board_reviewed,
            "rollouts": rollout_reviewed_ready,
            "expect": {
                "ready": True,
                "reviewed_authority": True,
                "board_pick": True,
                "board_authority": True,
                "rollout_raw": True,
                "rollout_authority": True,
                "development_caveat": False,
                "blockers_exact": [],
            },
        },
    ]


def add_error(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def expect_contains(errors: list[str], label: str, values: Any, expected_values: list[str]) -> None:
    values = values if isinstance(values, list) else []
    for expected in expected_values:
        if expected not in values:
            errors.append(f"{label}: expected {expected!r} in {values!r}")


def summarize_case(spec: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    gate = so101_training_readiness_gate_section(
        spec["authority"],
        spec["board"],
        spec["rollouts"],
    )
    expect = spec["expect"]
    errors: list[str] = []
    add_error(errors, "ready", gate.get("ready"), expect["ready"])
    add_error(
        errors,
        "status",
        gate.get("status"),
        "serious_training_ready" if expect["ready"] else "serious_training_blocked",
    )
    add_error(
        errors,
        "reviewed_model_authority_ready",
        gate.get("reviewed_model_authority_ready"),
        expect["reviewed_authority"],
    )
    add_error(
        errors,
        "reviewed_model_backed_board_source_pick_place",
        gate.get("reviewed_model_backed_board_source_pick_place"),
        expect["board_pick"],
    )
    add_error(
        errors,
        "board_pick_reviewed_model_authority_ready",
        gate.get("board_pick_reviewed_model_authority_ready"),
        expect["board_authority"],
    )
    if "rollout_raw" in expect:
        add_error(
            errors,
            "rollout_ready_for_policy_training",
            gate.get("rollout_ready_for_policy_training"),
            expect["rollout_raw"],
        )
    add_error(
        errors,
        "rollout_policy_training_authority_ready",
        gate.get("rollout_policy_training_authority_ready"),
        expect["rollout_authority"],
    )
    add_error(
        errors,
        "development_fixture_evidence_not_policy_training_truth",
        gate.get("development_fixture_evidence_not_policy_training_truth"),
        expect["development_caveat"],
    )
    add_error(errors, "blocker_count", gate.get("blocker_count"), len(gate.get("blockers") or []))
    if "blockers_exact" in expect:
        add_error(errors, "blockers", gate.get("blockers"), expect["blockers_exact"])
    expect_contains(
        errors,
        "blockers",
        gate.get("blockers"),
        expect.get("blockers_contain", []),
    )

    summary_path = case_dir / "so101_training_readiness_gate.json"
    case_dir.mkdir(parents=True, exist_ok=True)
    write_json(summary_path, gate)
    return {
        "case_id": spec["case_id"],
        "ok": not errors,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "expected": expect,
        "summary_path": str(summary_path),
        "gate": gate,
    }


def flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    gate = case["gate"]
    return {
        "case_id": case["case_id"],
        "ok": case["ok"],
        "gate_status": gate.get("status"),
        "gate_ready": gate.get("ready"),
        "reviewed_model_authority_ready": gate.get("reviewed_model_authority_ready"),
        "reviewed_model_backed_board_source_pick_place": gate.get(
            "reviewed_model_backed_board_source_pick_place"
        ),
        "board_pick_reviewed_model_authority_ready": gate.get(
            "board_pick_reviewed_model_authority_ready"
        ),
        "rollout_ready_for_policy_training": gate.get("rollout_ready_for_policy_training"),
        "rollout_policy_training_authority_ready": gate.get(
            "rollout_policy_training_authority_ready"
        ),
        "development_fixture_evidence_not_policy_training_truth": gate.get(
            "development_fixture_evidence_not_policy_training_truth"
        ),
        "blockers": gate.get("blockers"),
        "expected_gate_ready": case["expected"].get("ready"),
        "errors": case["errors"],
    }


def write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SO-101 Training Readiness Gate Matrix",
        "",
        f"- `status`: `{summary['status']}`",
        f"- `case_count`: `{summary['case_count']}`",
        f"- `failed_cases`: `{', '.join(summary['failed_case_ids']) if summary['failed_case_ids'] else 'none'}`",
        f"- `summary_json`: `{summary['artifacts']['summary_json']}`",
        f"- `cases_csv`: `{summary['artifacts']['cases_csv']}`",
        "",
        "Caveat: this is a contract-state smoke. It injects reviewed-authority, board-pick, and rollout dictionaries to exercise serious-training gate transitions; it is not policy-training authority.",
        "",
        "## Cases",
        "",
        "| Case | Status | Ready | Board Pick | Rollout Authority | Fixture Caveat | Blockers |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        gate = case["gate"]
        lines.append(
            "| `{case_id}` | `{status}` | `{ready}` | `{board}` | `{rollout}` | `{fixture}` | `{blockers}` |".format(
                case_id=case["case_id"],
                status=case["status"],
                ready=gate.get("ready"),
                board=gate.get("reviewed_model_backed_board_source_pick_place"),
                rollout=gate.get("rollout_policy_training_authority_ready"),
                fixture=gate.get("development_fixture_evidence_not_policy_training_truth"),
                blockers=", ".join(gate.get("blockers") or []),
            )
        )
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- `all_ready_reviewed_contract_state` exercises the ready branch only; its injected dictionaries are not reviewed robot evidence.",
            "- Draft, development, and fixture-only model-authority labels are rejected even when raw readiness booleans are true.",
            "- Use this smoke to protect training-readiness gate logic. Use reviewed SO-101 model-backed pick/place and rollout evidence before serious training.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve(strict=False)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        summarize_case(spec, output_dir / "cases" / spec["case_id"])
        for spec in case_specs(output_dir)
    ]
    ok = all(case["ok"] for case in cases)
    summary_path = output_dir / "so101_training_readiness_gate_matrix_summary.json"
    csv_path = output_dir / "so101_training_readiness_gate_matrix_cases.csv"
    readme_path = output_dir / "README.md"
    summary = {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ok" if ok else "validation_failed",
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "model_authority": "training_readiness_contract_matrix_not_authority",
        "observed_evidence_is_policy_training_authority": False,
        "ready_for_policy_training": False,
        "hardware_skipped": True,
        "gui_skipped": True,
        "openai_skipped": True,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "failed_case_ids": [case["case_id"] for case in cases if not case["ok"]],
        "cases": cases,
        "artifacts": {
            "summary_json": str(summary_path),
            "cases_csv": str(csv_path),
            "readme_md": str(readme_path),
        },
        "limitations": [
            "This matrix injects state dictionaries and does not load a reviewed SO-101 model or train a policy.",
            "The all-ready case exercises the gate's ready branch and must not be cited as serious policy-training evidence.",
            "Development or draft model-authority strings remain blocked even when raw readiness booleans are true.",
        ],
    }
    write_json(summary_path, summary)
    write_csv(csv_path, [flatten_case(case) for case in cases])
    write_readme(readme_path, summary)

    print(
        json.dumps(
            {
                "ok": ok,
                "status": summary["status"],
                "summary_json": str(summary_path),
                "cases_csv": str(csv_path),
                "readme_md": str(readme_path),
                "case_ids": summary["case_ids"],
                "failed_cases": summary["failed_case_ids"],
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
