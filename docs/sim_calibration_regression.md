# Simulator Calibration Regression Gate

Run this hardware-free gate before changing simulator rendering, camera profiles, board/perception calibration, or anything that could affect the SO-101 chess camera path. It exercises the merged simulator calibration regression suite without connecting to the robot or opening GUI display flows.

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check
```

The suite passes when `/private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json` has `"ok": true` and `"status": "ok"`. It also writes a root `/private/tmp/lerobot_sim/calibration_regression_suite/README.md`, `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index_report.md`, and `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index.json`. For quick review, open `artifact_index_report.md` first; it is a deterministic Markdown view of the compact artifact index and links the highest-signal generated evidence, including the reference capture checklist, visual-review contact sheets, the gripper-camera POV review, the pose fixture, the pick/place gripper-camera sequence, the pick/place depth/distance JSON/CSV, the pick/place perceived-depth comparison JSON/CSV, and the app-entrypoint frame. For image-first inspection, open `visual_review/pick_place_sequence_distance_annotated_contact_sheet.png`, `visual_review/gripper_camera_pov_annotated_contact_sheet.png`, and `visual_review/sim_camera_pose_fixture_annotated_contact_sheet.png`; for metric review, inspect `visual_review/pick_place_depth_distance_metrics.json` or `.csv` plus `visual_review/pick_place_perceived_depth_comparison.json` or `.csv`. The root `README.md` repeats that entrypoint, the core JSON summaries, the hardware/gui/OpenAI skipped markers, and the current real-media gap.

To exercise the same suite with declared reference-media metadata, pass an optional manifest:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_manifest --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --reference-media-manifest archive/reference_media_manifest.example.json
```

That manifest-backed run remains hardware-free and is not the default CI path. It records `reference_media_manifest` in `calibration_regression_summary.json`, keeps `inventory.summary.manifest_validation_status`, carries selected media `declared_metadata`/`manifest_validation` through `comparison_set/comparison_set_summary.json`, and exposes the manifest status plus declared media fields in `artifact_index.json` and `artifact_index_report.md`.

For a narrower camera/board pose check without running the full suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_camera_pose_fixture.py --output-dir /private/tmp/lerobot_sim/sim_camera_pose_fixture
```

That writes `/private/tmp/lerobot_sim/sim_camera_pose_fixture/sim_camera_pose_fixture_summary.json` plus one raw frame, annotated frame, and `camera_metadata.json` per deterministic case.

Each per-case `camera_metadata.json` contains `camera_metadata.image_size_px`, `camera_metadata.camera_matrix_px`, `camera_metadata.intrinsics`, `camera_metadata.distortion_coefficients`, `camera_metadata.extrinsics.board_to_camera`, and `camera_metadata.coordinate_frame_convention` alongside projected board corners. The same file records target and piece square centers under `projection`. These intrinsics/extrinsics are simulator reference metadata for camera-first tooling compatibility, not physical calibration truth.

For reference-media intake metadata without running the full suite, use the manifest-aware inventory smoke:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_media_inventory.py --manifest archive/reference_media_manifest.example.json --output-dir /private/tmp/lerobot_sim/reference_media_inventory_manifest
```

See [docs/sim_reference_media_intake.md](sim_reference_media_intake.md) for the manifest fields used to describe camera POV, board/piece/gripper visibility, calibration target intent, failure-mode coverage, simulator profile wiring, and limitations for future repo-local SO-101 photos/videos.

## GitHub Actions Signal

The focused `Simulator Calibration Regression` workflow runs the same hardware-free suite for pull requests targeting `feat/telemetry-recording` when simulator, camera, chess perception, smoke-script, report-renderer, reference-image, or gate documentation paths change. It uses Python 3.12, installs only the Python modules needed by this suite, verifies the generated summary fields, writes a job summary naming the uploaded artifact, and uploads the suite output directory as a workflow artifact. After downloading the artifact, open `artifact_index_report.md` first, then follow its links to images, JSON summaries, and child logs.

The workflow also treats `sim_camera_pose_fixture`, `gripper_camera_pov_review`, `visual_review`, `app_entrypoint_metadata`, `pick_place_scenario_matrix.piece_visibility`, and `artifact_index.json` as part of the artifact contract. The pose fixture must report deterministic nominal and perturbed case IDs, raw frames, annotated frames, per-case metadata JSON, projected board corners, and target/piece centers. The gripper-camera POV review must report a small open/approach/grasp/release state sequence with raw frames, annotated frames, per-state metadata JSON, target square center and projected square polygon, gripper opening/state, SimCamera metadata contract checks, and piece visibility/occlusion/clearance rows. The visual review must report stable PNG contact sheets for gripper POV, pose fixture, and pick/place sequence frames, plus distance-annotated pick/place sequence frames, pick/place depth/distance JSON/CSV metrics, pick/place perceived-depth comparison JSON/CSV metrics, and a copied app-entrypoint frame for convenient bundle browsing. The depth/distance metrics must label simulator ground truth separately from perceived depth, include camera-to-board/piece distances, target/piece world coordinates, projected pixel coordinates, projection residuals, and a clearly sourced gripper-to-piece proxy when true end-effector depth is unavailable. The perceived-depth comparison must add a clearly labeled metadata-derived rendered-board-corner PnP baseline with estimated camera-to-piece/board distances, simulator ground-truth distances, signed/absolute residuals, estimator source/status, and an explicit note that it is not real-camera depth perception. The app-entrypoint smoke must report a synthetic frame, a metadata sidecar when requested, skipped hardware/gui/OpenAI markers, passing app-facing metadata contract checks, and the same compact `app_camera_status` readout shown by `chess_robot_ui_llm_v2.py --sim`. All four pick/place scenarios must report available visibility evidence, each target release frame path must exist, and each `target_release_open` row must include visible fraction, occlusion fraction, and gripper-clearance fields. The generated artifact index must exist, report `status: "ok"`, have a nonzero artifact count, have no missing artifacts, and include populated categories for visual-review contact sheets, sequence frames, depth/distance metrics, perceived-depth comparison metrics, real-reference comparisons, ranked candidates, perception fixture evidence, SimCamera pose fixture evidence, gripper-camera POV evidence, app-entrypoint evidence, pick/place scenario release frames, the negative check, and child logs. These are structural availability checks rather than exact metric-value thresholds.

This CI signal is still a simulator/perception regression gate only. It does not connect to SO-101 hardware, open GUI calibration flows, or replace later physical robot validation.

## What This Proves

The suite orchestrates these existing smoke scripts as subprocesses and records each child command, return code, stdout path, stderr path, and expected JSON path under `child_commands`:

- `smoke_sim_reference_media_inventory.py` finds real reference media that can calibrate the simulator.
- `smoke_sim_reference_media_comparison_set.py` runs real-reference comparison artifacts for selected images.
- `smoke_sim_calibration_session_report.py` ranks baseline and perturbed local SimCamera candidates.
- `smoke_sim_perception_regression_fixture.py` packages the selected ranked candidate into perception fixture evidence.
- `smoke_sim_camera_pose_fixture.py` renders deterministic nominal, perturbed, overview, and gripper-state SimCamera pose review frames plus per-case metadata.
- `smoke_sim_gripper_camera_pov_review.py` renders deterministic gripper-camera POV frames for open, approach, grasp-window, closed, and release-style gripper states using existing SimCamera/KinematicsTools metadata and piece-visibility geometry.
- `smoke_sim_pick_place_scenario_matrix.py` runs center, edge-file, back-rank, and near-gripper pick/place scenarios.
- `smoke_sim_app_entrypoints.py` verifies simulator app/tool entrypoints and the app-facing SimCamera metadata contract.
- `render_sim_calibration_visual_review.py` composes durable contact-sheet PNGs, distance-annotated pick/place sequence frames, and pick/place depth/distance JSON/CSV metrics from those generated frames without changing simulator rendering.
- `smoke_sim_reference_capture_checklist.py` turns the current real-media gap into JSON/Markdown capture requirements without opening cameras or making real media mandatory.
- With `--include-negative-check`, an empty-inventory comparison-set run must fail clearly while the aggregate suite still passes.

The calibration session report passes when at least one rankable candidate has every child smoke passing; lower-ranked candidate failures remain visible as comparative calibration evidence instead of blocking the suite.

A passing summary should show:

- `hardware_skipped: true`
- `gui_skipped: true`
- `openai_skipped: true`
- `reference_media_manifest.status: "ok"` and selected declared-media rows when `--reference-media-manifest` is supplied
- `child_commands.*.ok: true`
- `comparison_set.status: "ok"`
- `calibration_session.selected_candidate` populated with the rank-1 candidate
- `perception_fixture.status: "ok"` and fixture artifact paths populated
- `sim_camera_pose_fixture.status: "ok"` with deterministic nominal and perturbed case IDs, frame paths, annotated-frame paths, and metadata paths populated
- `gripper_camera_pov_review.status: "ok"` with open/approach/grasp/release state IDs, frame paths, annotated-frame paths, metadata paths, metadata contract checks, target center geometry, gripper state, and piece visibility rows populated
- `visual_review.status: "ok"` with gripper POV, pose fixture, and pick/place sequence contact-sheet PNG paths populated, distance-annotated pick/place sequence frames populated under `frame_sequences`, `distance_metrics.paths.json`/`.csv` populated with simulator-ground-truth depth/distance fields, `perceived_depth_comparison.paths.json`/`.csv` populated with estimate-vs-ground-truth residual fields, and `recordings.*` populated with either a best-effort MP4 path or a skipped reason
- `reference_capture_checklist.status: "action_required"` while only `archive/chess_test_images/current_view.jpg` is represented, with missing video, calibration-target, failure-mode, and post-pick capture requirements listed
- `app_entrypoint_metadata.status: "ok"` with `ok: true`, `frame_path`, `metadata_path`, skipped hardware/gui/OpenAI markers, passing metadata contract checks, and `app_camera_status.ok: true`
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

The `gripper_camera_pov_review` signal packages the same kind of synthetic metadata evidence for one camera-first review sequence. Each state writes a raw frame, an annotated frame, and `metadata.json` with the camera metadata contract, projected target square polygon, target/piece center, gripper opening, visible fraction, occlusion fraction, and minimum gripper clearance. The visual review also turns the center-board pick/place matrix child into a gripper-camera sequence showing approach, grasp/contact, lift/transfer, place/release, and retreat. These artifacts are meant to make pre-hardware pickup calibration review practical, not to claim physical contact or real-camera segmentation performance.

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
- `gripper_camera_pov_review/gripper_camera_pov_review_summary.json`
- `gripper_camera_pov_review/states/*/frame.png`
- `gripper_camera_pov_review/states/*/frame_annotated.png`
- `gripper_camera_pov_review/states/*/metadata.json`
- `visual_review/visual_review_summary.json`
- `visual_review/gripper_camera_pov_annotated_contact_sheet.png`
- `visual_review/gripper_camera_pov_raw_contact_sheet.png`
- `visual_review/sim_camera_pose_fixture_annotated_contact_sheet.png`
- `visual_review/sim_camera_pose_fixture_raw_contact_sheet.png`
- `visual_review/pick_place_sequence_distance_annotated_contact_sheet.png`
- `visual_review/pick_place_sequence_raw_contact_sheet.png`
- `visual_review/pick_place_sequence_frames/*.png`
- `visual_review/pick_place_depth_distance_metrics.json`
- `visual_review/pick_place_depth_distance_metrics.csv`
- `visual_review/pick_place_perceived_depth_comparison.json`
- `visual_review/pick_place_perceived_depth_comparison.csv`
- `visual_review/pick_place_sequence_distance_annotated_sequence.mp4` when OpenCV MP4 writing is available
- `visual_review/app_entrypoint_frame.jpg`
- `reference_capture_checklist/reference_capture_checklist.json`
- `reference_capture_checklist/reference_capture_checklist.md`
- `app_entrypoint/smoke_sim_app_entrypoints_summary.json`
- `app_entrypoint/smoke_sim_app_frame.jpg`
- `app_entrypoint/smoke_sim_app_metadata.json`
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

The visual review can be regenerated from an existing suite summary without rerunning smokes:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/render_sim_calibration_visual_review.py /private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json --output-dir /private/tmp/lerobot_sim/calibration_regression_suite/visual_review
```

By default, the standalone visual-review command writes deterministic PNG contact sheets, distance-annotated pick/place sequence frames, `pick_place_depth_distance_metrics.json`/`.csv`, and `pick_place_perceived_depth_comparison.json`/`.csv`, then records why no video was produced. The metric files use millimeters for the reviewer-facing fields and label camera-to-board/piece distances as simulator ground truth. The comparison files add `estimated_camera_to_piece_distance_mm`, `ground_truth_camera_to_piece_distance_mm`, `camera_to_piece_error_mm`, `estimated_camera_to_board_plane_distance_mm`, and `camera_to_board_error_mm` using a metadata-derived rendered-board-corner PnP baseline. The current gripper-to-piece value is a board-plane proxy from the rendered gripper overlay, and the comparison estimator is explicitly labeled `metadata_derived_baseline` until real camera/depth estimates are compared. A best-effort MP4 can be tried with `--try-video`, and the full regression suite now passes that flag so local/CI bundles include a recording when the OpenCV build supports MP4 writing. PNG contact sheets, frame sequences, and metric JSON/CSV remain the required review artifacts because codec availability varies.

The report includes the category summary table, artifact and missing counts, hardware/gui/OpenAI skipped markers, the current real-media visibility gap, the reference capture checklist, visual-review contact sheets, pick/place sequence frames, pick/place depth/distance metric JSON/CSV, a compact per-stage perceived-depth comparison table, real-reference comparison images, ranked candidate captures, perception fixture evidence, SimCamera pose fixture metadata, app-entrypoint metadata evidence, all pick/place release frames, negative-check status, and child stdout/stderr links.

## Skipped Paths

This is intentionally local and hardware-free:

- No SO-101 motors, serial ports, Feetech buses, or real robot execution paths are invoked.
- No camera capture device is opened.
- No OpenCV click/display calibration UI is requested; the suite passes explicit non-interactive inputs.
- No OpenAI credentials or network calls are required.
- No simulator rendering, camera profiles, perception algorithms, dependencies, canonical calibration constants, UI behavior, LLM/tool flow, or motor behavior are changed.

The generated summary records these as `hardware_skipped`, `gui_skipped`, `openai_skipped`, and `skipped_markers`.

## Current Reference Media State

The current inventory selects one wired real image:

```text
archive/chess_test_images/current_view.jpg
```

That image currently covers camera POV, board corners, piece scale, gripper visibility, workspace geometry, and lighting heuristics. Known gaps remain:

- No real-world videos are present for motion, recovery, or timing references.
- No reference media currently documents failure modes.
- The default inventory tags and coverage are heuristic, based on path/name and simulator wiring.
- `archive/reference_media_manifest.example.json` demonstrates the manifest intake contract against that same image only; no new real photos or videos were captured in this slice.
- When a manifest is supplied, the inventory validates repo-local media paths and records `manifest_summary`, per-record `declared_metadata`, per-record `manifest_validation`, merged `reference_tags`, and manifest-declared coverage/failure-mode gaps.

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
    "openai_skipped": summary["openai_skipped"],
    "selected_candidate": summary["selected_candidate"]["candidate_id"],
    "pose_fixture_cases": summary["sim_camera_pose_fixture"]["case_ids"],
    "pose_fixture_frames": summary["sim_camera_pose_fixture"]["frame_paths"],
    "visual_review": {
        "status": summary["visual_review"]["status"],
        "contact_sheet_paths": summary["visual_review"]["contact_sheet_paths"],
        "frame_sequences": [
            {key: seq[key] for key in ("id", "scenario_id", "frame_count")}
            for seq in summary["visual_review"]["frame_sequences"]
        ],
        "distance_metrics": {
            key: summary["visual_review"]["distance_metrics"].get(key)
            for key in ("status", "frame_count", "paths", "perceived_depth_status")
        },
        "perceived_depth_comparison": {
            key: summary["visual_review"]["perceived_depth_comparison"].get(key)
            for key in ("status", "frame_count", "paths", "aggregate")
        },
        "recordings": summary["visual_review"]["recordings"],
    },
    "app_entrypoint_metadata": {
        "ok": summary["app_entrypoint_metadata"]["ok"],
        "status": summary["app_entrypoint_metadata"]["status"],
        "frame_path": summary["app_entrypoint_metadata"]["frame_path"],
        "metadata_path": summary["app_entrypoint_metadata"]["metadata_path"],
        "metadata_contract_ok": summary["app_entrypoint_metadata"]["metadata_contract"]["ok"],
    },
    "matrix_scenarios": summary["pick_place_scenario_matrix"]["scenario_ids"],
    "matrix_release_frames": summary["pick_place_scenario_matrix"]["release_frame_paths"],
    "matrix_piece_visibility": summary["pick_place_scenario_matrix"]["piece_visibility"],
    "negative_check": summary["negative_check"]["status"],
    "artifact_index": summary["artifact_index"],
})
PY
```
