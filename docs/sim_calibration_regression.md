# Simulator Calibration Regression Gate

Run this hardware-free gate before changing simulator rendering, camera profiles, board/perception calibration, or anything that could affect the SO-101 chess camera path. It exercises the merged simulator calibration regression suite without connecting to the robot or opening GUI display flows.

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check
```

The suite passes when `/private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json` has `"ok": true` and `"status": "ok"`. It also writes a root `/private/tmp/lerobot_sim/calibration_regression_suite/README.md`, `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index_report.md`, and `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index.json`. For quick review, open `artifact_index_report.md` first; it is a deterministic Markdown view of the compact artifact index and links the highest-signal generated evidence. The root `README.md` repeats that entrypoint, the core JSON summaries, the hardware/gui skipped markers, and the current real-media gap.

For a narrower camera/board pose check without running the full suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_camera_pose_fixture.py --output-dir /private/tmp/lerobot_sim/sim_camera_pose_fixture
```

That writes `/private/tmp/lerobot_sim/sim_camera_pose_fixture/sim_camera_pose_fixture_summary.json` plus one raw frame, annotated frame, and `camera_metadata.json` per deterministic case.

Each per-case `camera_metadata.json` contains `camera_metadata.image_size_px`, `camera_metadata.camera_matrix_px`, `camera_metadata.intrinsics`, `camera_metadata.distortion_coefficients`, `camera_metadata.extrinsics.board_to_camera`, and `camera_metadata.coordinate_frame_convention` alongside projected board corners. The same file records target and piece square centers under `projection`. These intrinsics/extrinsics are simulator reference metadata for camera-first tooling compatibility, not physical calibration truth.

## GitHub Actions Signal

The focused `Simulator Calibration Regression` workflow runs the same hardware-free suite for pull requests targeting `feat/telemetry-recording` when simulator, camera, chess perception, smoke-script, report-renderer, reference-image, or gate documentation paths change. It uses Python 3.12, installs only the Python modules needed by this suite, verifies the generated summary fields, writes a job summary naming the uploaded artifact, and uploads the suite output directory as a workflow artifact. After downloading the artifact, open `artifact_index_report.md` first, then follow its links to images, JSON summaries, and child logs.

The workflow also treats `sim_camera_pose_fixture`, `pick_place_scenario_matrix.piece_visibility`, and `artifact_index.json` as part of the artifact contract. The pose fixture must report deterministic nominal and perturbed case IDs, raw frames, annotated frames, per-case metadata JSON, projected board corners, and target/piece centers. All four pick/place scenarios must report available visibility evidence, each target release frame path must exist, and each `target_release_open` row must include visible fraction, occlusion fraction, and gripper-clearance fields. The generated artifact index must exist, report `status: "ok"`, have a nonzero artifact count, have no missing artifacts, and include populated categories for real-reference comparisons, ranked candidates, perception fixture evidence, SimCamera pose fixture evidence, pick/place scenario release frames, the negative check, and child logs. These are structural availability checks rather than exact metric-value thresholds.

This CI signal is still a simulator/perception regression gate only. It does not connect to SO-101 hardware, open GUI calibration flows, or replace later physical robot validation.

## What This Proves

The suite orchestrates these existing smoke scripts as subprocesses and records each child command, return code, stdout path, stderr path, and expected JSON path under `child_commands`:

- `smoke_sim_reference_media_inventory.py` finds real reference media that can calibrate the simulator.
- `smoke_sim_reference_media_comparison_set.py` runs real-reference comparison artifacts for selected images.
- `smoke_sim_calibration_session_report.py` ranks baseline and perturbed local SimCamera candidates.
- `smoke_sim_perception_regression_fixture.py` packages the selected ranked candidate into perception fixture evidence.
- `smoke_sim_camera_pose_fixture.py` renders deterministic nominal, perturbed, overview, and gripper-state SimCamera pose review frames plus per-case metadata.
- `smoke_sim_pick_place_scenario_matrix.py` runs center, edge-file, back-rank, and near-gripper pick/place scenarios.
- With `--include-negative-check`, an empty-inventory comparison-set run must fail clearly while the aggregate suite still passes.

A passing summary should show:

- `hardware_skipped: true`
- `gui_skipped: true`
- `child_commands.*.ok: true`
- `comparison_set.status: "ok"`
- `calibration_session.selected_candidate` populated with the rank-1 candidate
- `perception_fixture.status: "ok"` and fixture artifact paths populated
- `sim_camera_pose_fixture.status: "ok"` with deterministic nominal and perturbed case IDs, frame paths, annotated-frame paths, and metadata paths populated
- `pick_place_scenario_matrix.aggregate_status.ok: true` with four scenario IDs and release-frame paths populated
- `pick_place_scenario_matrix.piece_visibility.all_scenarios_available: true` with per-scenario visible fraction, occlusion fraction, and gripper clearance values
- `negative_check.status: "no_reference_media_selected"` when `--include-negative-check` is used
- `artifact_index.status: "ok"` with `artifact_count > 0`, `missing_artifact_count: 0`, an existing `path`, and categories covering real-reference comparison, ranked candidate, perception fixture, SimCamera pose fixture, pick/place scenario, negative check, and logs

The `sim_camera_pose_fixture` signal is a simulator-only pose artifact. It freezes the synthetic camera marker clock inside the smoke process, renders a small deterministic set of SimCamera frames, and writes one `camera_metadata.json` per case with view/profile data, image size, camera matrix/intrinsics, zero distortion coefficients, named board-to-camera extrinsics, coordinate-frame convention notes, board corners, target square center, piece square center, gripper state, and image hashes. It compares perturbed and alternate views against the nominal gripper-open case for review, but does not use pixel deltas as thresholds.

The `piece_visibility` signal is a simulator-only geometry metric. Each pick/place capture reconstructs the active piece disc and visible gripper finger polygons from synthetic capture metadata, then reports:

- `occlusion.visible_fraction` and `occlusion.occlusion_fraction`
- `gripper_clearance.min_clearance_px`
- `gripper_clearance.clear_of_gripper`
- `status`, usually `clear` or `gripper_overlap`

These values are evidence-only in this first pass. The suite reports them but does not fail on a visibility threshold until local and GitHub Actions runs prove the measured values are stable. They do not model physical chess-piece contact or real-camera segmentation.

## Outputs

The top-level summary is:

```text
/private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json
```

Common artifact paths under the output directory:

- `inventory/reference_media_inventory.json`
- `comparison_set/comparison_set_summary.json`
- `comparison_set/references/*/side_by_side.jpg`
- `comparison_set/references/*/overlay.jpg`
- `comparison_set/references/*/absolute_difference_heatmap.jpg`
- `session/session_summary.json`
- `session/candidates/*/comparison/side_by_side.jpg`
- `session/candidates/*/comparison/absolute_difference_heatmap.jpg`
- `session/candidates/*/board_pose/frame_annotated.jpg`
- `session/candidates/*/pick_place/06_target_release_open.jpg`
- `fixture/fixture_summary.json`
- `sim_camera_pose_fixture/sim_camera_pose_fixture_summary.json`
- `sim_camera_pose_fixture/cases/*/frame.png`
- `sim_camera_pose_fixture/cases/*/frame_annotated.png`
- `sim_camera_pose_fixture/cases/*/camera_metadata.json`
- `pick_place_scenario_matrix/scenario_matrix_summary.json`
- `pick_place_scenario_matrix/scenarios/*/summary.json`
- `pick_place_scenario_matrix/scenarios/*/06_target_release_open.jpg`
- `negative_empty_inventory/comparison_set_summary.json`
- `README.md`
- `artifact_index_report.md`
- `artifact_index.json`

Each child also writes captured stdout/stderr text files in its own output directory.

The artifact index can be regenerated from an existing suite summary without rerunning smokes:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_artifact_index.py /private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json --output-json /private/tmp/lerobot_sim/calibration_regression_suite/artifact_index.json
```

The human-readable report can also be regenerated from either the artifact index or the suite summary:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/render_sim_calibration_artifact_index_report.py /private/tmp/lerobot_sim/calibration_regression_suite/artifact_index.json
```

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/render_sim_calibration_artifact_index_report.py /private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json --output-md /private/tmp/lerobot_sim/calibration_regression_suite/artifact_index_report.md
```

The report includes the category summary table, artifact and missing counts, hardware/gui skipped markers, the current real-media visibility gap, real-reference comparison images, ranked candidate captures, perception fixture evidence, all pick/place release frames, negative-check status, and child stdout/stderr links.

## Skipped Paths

This is intentionally local and hardware-free:

- No SO-101 motors, serial ports, Feetech buses, or real robot execution paths are invoked.
- No camera capture device is opened.
- No OpenCV click/display calibration UI is requested; the suite passes explicit non-interactive inputs.
- No simulator rendering, camera profiles, perception algorithms, dependencies, canonical calibration constants, UI behavior, LLM/tool flow, or motor behavior are changed.

The generated summary records these as `hardware_skipped`, `gui_skipped`, and `skipped_markers`.

## Current Reference Media State

The current inventory selects one wired real image:

```text
archive/chess_test_images/current_view.jpg
```

That image currently covers camera POV, board corners, piece scale, gripper visibility, workspace geometry, and lighting heuristics. Known gaps remain:

- No real-world videos are present for motion, recovery, or timing references.
- No reference media currently documents failure modes.
- The inventory tags and coverage are heuristic, based on path/name and simulator wiring.

Do not treat this suite as a substitute for later hardware validation. Treat it as the default local regression gate before touching the physical SO-101.

## Quick Summary Check

After the command finishes, this one-liner confirms the fields developers usually need:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 - <<'PY'
import json
from pathlib import Path
summary = json.loads(Path("/private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json").read_text())
print({
    "ok": summary["ok"],
    "status": summary["status"],
    "hardware_skipped": summary["hardware_skipped"],
    "gui_skipped": summary["gui_skipped"],
    "selected_candidate": summary["selected_candidate"]["candidate_id"],
    "pose_fixture_cases": summary["sim_camera_pose_fixture"]["case_ids"],
    "pose_fixture_frames": summary["sim_camera_pose_fixture"]["frame_paths"],
    "matrix_scenarios": summary["pick_place_scenario_matrix"]["scenario_ids"],
    "matrix_release_frames": summary["pick_place_scenario_matrix"]["release_frame_paths"],
    "matrix_piece_visibility": summary["pick_place_scenario_matrix"]["piece_visibility"],
    "negative_check": summary["negative_check"]["status"],
    "artifact_index": summary["artifact_index"],
})
PY
```
