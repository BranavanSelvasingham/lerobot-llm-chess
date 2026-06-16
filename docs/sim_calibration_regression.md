# Simulator Calibration Regression Gate

Run this hardware-free gate before changing simulator rendering, camera profiles, board/perception calibration, or anything that could affect the SO-101 chess camera path. It exercises the merged simulator calibration regression suite without connecting to the robot or opening GUI display flows.

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check
```

The suite passes when `/private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json` has `"ok": true` and `"status": "ok"`. It also writes a root `/private/tmp/lerobot_sim/calibration_regression_suite/README.md`, `/private/tmp/lerobot_sim/calibration_regression_suite/evidence_bundle/sim_evidence_bundle.md`, `/private/tmp/lerobot_sim/calibration_regression_suite/evidence_bundle/sim_evidence_bundle.json`, `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index_report.md`, and `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index.json`. The suite now also runs the deterministic hardware-free IK reachability drill under `ik_reachability_drill/` and preserves `ik_reachability_drill_summary.json`, `ik_reachability_drill_rows.csv`, and `ik_reachability_drill_heatmap.png` as part of the contract. Missing repo-local SO-101 model inputs remain a non-failing explicit `model_unavailable_fallback_complete` diagnostic rather than a CI failure. For quick depth-calibration review, open `evidence_bundle/sim_evidence_bundle.md` first; it links the depth/distance scorecard, metadata-native depth view, MP4 recordings when available, real projection residual overlay when comparable real sidecars are supplied, and optional capture-plan entries without inventing capture evidence. For the full artifact inventory, open `artifact_index_report.md`; it is a deterministic Markdown view of the compact artifact index and links the highest-signal generated evidence, including the evidence bundle, reference capture checklist, visual-review contact sheets, the gripper-camera POV review, the pose fixture, the IK reachability summary/CSV/heatmap, the pick/place gripper-camera sequence, the pick/place depth/distance scorecard PNG/JSON, the pick/place depth/distance JSON/CSV, the pick/place perceived-depth comparison JSON/CSV, the pick/place PnP residual diagnostic JSON/CSV, the metadata-native SimCamera projection/depth PNG/JSON/CSV, the real projection intake JSON/CSV/contact sheet, and the app-entrypoint frame. For image-first inspection, open `visual_review/pick_place_depth_distance_scorecard.png`, `visual_review/pick_place_sequence_distance_annotated_contact_sheet.png`, `visual_review/gripper_camera_pov_annotated_contact_sheet.png`, `visual_review/sim_camera_pose_fixture_annotated_contact_sheet.png`, `visual_review/pick_place_metadata_native_depth_view.png`, `ik_reachability_drill/ik_reachability_drill_heatmap.png`, and `real_projection_intake/real_projection_intake_contact_sheet.png`; for metric review, inspect `evidence_bundle/sim_evidence_bundle.json`, `visual_review/pick_place_depth_distance_scorecard.json`, `visual_review/pick_place_depth_distance_metrics.json` or `.csv`, `visual_review/pick_place_perceived_depth_comparison.json` or `.csv`, `visual_review/pick_place_pnp_residual_diagnostics.json` or `.csv`, `visual_review/pick_place_metadata_native_depth_view.json` or `.csv`, `ik_reachability_drill/ik_reachability_drill_summary.json`, `ik_reachability_drill/ik_reachability_drill_rows.csv`, and `real_projection_intake/real_projection_intake.json` or `.csv`. The root `README.md` repeats those entrypoints, the core JSON summaries, the hardware/gui/OpenAI skipped markers, and the current real-media gap.

To ask the integrated suite to try model-backed IK, pass an optional model path:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_model --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --ik-model-path /absolute/path/to/so101.urdf
```

That still stays hardware-free. The suite forwards `--model-path` to
`scripts/smoke_sim_ik_reachability_drill.py`, preserves the child command under
`child_commands.ik_reachability_drill.command`, and exposes the requested path
under `ik_reachability_drill.configured_model_path`, with the richer request
probe mirrored under `ik_reachability_drill.configured_model_request`, plus
`ik_reachability_drill.model_diagnostic.selected_model_path` when the child can
use it. If the supplied path is missing or unusable, the suite still exits
successfully and records a `missing_model` or `model_unavailable` diagnostic
instead of turning the hardware-free gate red.

Before treating `--ik-model-path` results as meaningful model-backed IK
evidence, run the focused hardware-free contract checker:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_contract.py --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight
```

To inspect a candidate model explicitly:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

This checker writes `so101_model_contract_summary.json`,
`so101_model_contract_checklist.csv`, and `README.md`. It records whether the
supplied path exists, whether its suffix is one of `.urdf`, `.xml`, `.mjcf`, or
`.xacro`, whether it is directly usable by the current
`RobotKinematics`/placo path, the simulator-side body-joint and joint-limit
contract from `src/lerobot/sim/robot.py`, the expected target frame
`gripper_frame_link`, any visible TCP or gripper-tip field hits, and the
remaining model-to-sim alignment inputs still required before low IK residuals
should be treated as trustworthy. If no model is supplied, the checker exits
`0` with a structured `missing_model` / `model_not_supplied` diagnostic and a
checklist of next inputs. If a supplied path is missing, it exits `0` with
`model_unavailable`. If a URDF is supplied and `placo` is available, the
checker also attempts a non-destructive `RobotKinematics` initialization and
reports joint/frame visibility separately from runtime initialization success.

To exercise the same suite with declared reference-media metadata, pass an optional manifest:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_manifest --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --reference-media-manifest archive/reference_media_manifest.example.json
```

That manifest-backed run remains hardware-free and is not the default CI path. It records `reference_media_manifest` in `calibration_regression_summary.json`, keeps `inventory.summary.manifest_validation_status`, carries selected media `declared_metadata`/`manifest_validation` through `comparison_set/comparison_set_summary.json`, and exposes the manifest status plus declared media fields in `artifact_index.json` and `artifact_index_report.md`. Future manifests can also declare repo-local `real_intrinsics_path`, `real_extrinsics_path`, `real_board_pose_path`, `board_corner_detections_path`, `real_depth_path`, or `depth_reference_path` for the real projection intake. The intake validates declared sidecar schemas and reports `sidecar_validation`, `sidecar_valid_count`, `sidecar_invalid_count`, and `sidecar_missing_count`; `example_only` fixtures stay `valid_example` and do not unlock real comparability, so these signals are scaffolding, not proof that physical calibration exists. When sidecars pass the stricter `real_capture: true` gate, the intake also emits `real_projection_residuals.json`, `.csv`, and `real_projection_residual_overlay_contact_sheet.png` with projected-point pixel residuals, ordered board-corner detection residuals, camera z/range residuals, metric depth-reference residuals, and camera-to-board-plane residuals. The suite then refreshes the visual-review scorecard so `visual_review/pick_place_depth_distance_scorecard.json` reports either `real_depth_comparable` with those residual metrics or `missing_real_depth_reference` with the exact required sidecar inputs.

To prepare the real sidecar inputs without adding hardware requirements to CI, use the
capture workflow helper:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/prepare_real_calibration_capture_sidecars.py --capture-spec test_data/real_calibration_sidecars/capture_workflow_example_spec.synthetic.json --example-only --require intrinsics --require extrinsics --require board_pose --require depth --output-dir /private/tmp/lerobot_sim/capture_workflow_smoke
```

It writes validator-compatible sidecars from supplied files/manual measurements plus a
`capture_plan.md` that lists the physical capture steps still needed. It does not open a
camera, move motors, or claim real SO-101 calibration; generated sidecars are
`example_only` unless the operator explicitly passes `--real-capture` with user-supplied
physical camera/board/depth measurements.

For a narrower camera/board pose check without running the full suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_depth_distance_drill.py --output-dir /private/tmp/lerobot_sim/depth_distance_drill
```

That writes `/private/tmp/lerobot_sim/depth_distance_drill/depth_distance_drill_summary.json`,
`/private/tmp/lerobot_sim/depth_distance_drill/depth_distance_drill_rows.csv`,
and `/private/tmp/lerobot_sim/depth_distance_drill/depth_distance_drill_heatmap.png`.
The drill samples deterministic center, edge, back-rank, and near-gripper squares
under nominal plus small simulator-only `board_to_camera` translation/rotation
perturbations. Rows report camera-to-board and camera-to-piece-proxy distances,
camera-frame z-depth, projected pixel positions, image-edge margin, synthetic
gripper-clearance proxy, range/pixel deltas from nominal, and explicit
simulator-only limitations in `mm` and `px`. It does not update calibration
constants, run the full evidence bundle, open real cameras, move motors, or
exercise UI/OpenAI paths.

For a hardware-free inverse-kinematics and reachability feasibility drill around
SO-101 chess pick waypoints without running motors:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_ik_reachability_drill.py --output-dir /private/tmp/lerobot_sim/ik_reachability_drill
```

That writes `/private/tmp/lerobot_sim/ik_reachability_drill/ik_reachability_drill_summary.json`,
`/private/tmp/lerobot_sim/ik_reachability_drill/ik_reachability_drill_rows.csv`,
and `/private/tmp/lerobot_sim/ik_reachability_drill/ik_reachability_drill_heatmap.png`.
The drill samples deterministic absolute targets, `delta_xyz` moves, and radial
end-effector commands around synthetic board/chess-piece pick waypoints. Rows
report per-command feasibility, violated envelope or joint-limit checks,
`unknown_fields`, and either model-backed IK residuals or explicit
`model_unavailable`/`missing_model` diagnostics when no repo-local URDF-backed
SO-101 kinematic model is available.

When the repo has no usable SO-101 URDF or MuJoCo/MJCF source, the script still
passes with `status: "model_unavailable_fallback_complete"` and records a
structured `model_diagnostic` inventory plus `next_model_inputs_needed`. In
that state, `unknown_model_unavailable` rows mean the command stayed inside the
documented command envelope and joint-limit proxies, not that true physical IK,
collision safety, or Cartesian reachability were solved. `blocked` rows are the
ones that already fail the fallback envelope, z-range, step-size, or joint-limit
checks before any future hardware execution should be attempted.

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

The focused `Simulator Calibration Regression` workflow runs the same hardware-free suite for pull requests targeting `feat/telemetry-recording` when simulator, camera, chess perception, smoke-script, report-renderer, reference-image, or gate documentation paths change. It uses Python 3.12, installs only the Python modules needed by this suite, verifies the generated summary fields, now checks the integrated IK reachability summary/CSV/heatmap contract, writes a job summary naming the uploaded artifact, and uploads the suite output directory as a workflow artifact. By default it leaves `IK_MODEL_PATH` empty so CI keeps the existing fallback-only behavior; a caller can set `IK_MODEL_PATH` to forward `--ik-model-path` into the suite without changing the workflow structure. After downloading the artifact, open `artifact_index_report.md` first, then follow its links to images, JSON summaries, and child logs.

The workflow also treats `sim_camera_pose_fixture`, `ik_reachability_drill`, `gripper_camera_pov_review`, `visual_review`, `real_projection_intake`, `evidence_bundle`, `app_entrypoint_metadata`, `pick_place_scenario_matrix.piece_visibility`, and `artifact_index.json` as part of the artifact contract. The pose fixture must report deterministic nominal and perturbed case IDs, raw frames, annotated frames, per-case metadata JSON, projected board corners, and target/piece centers. The IK reachability drill must report a deterministic summary JSON, rows CSV, and heatmap PNG, expose row counts and counts-by-feasibility, and preserve model diagnostic status so `model_unavailable_fallback_complete` is explicit but non-failing when no repo-local SO-101 model is available. The gripper-camera POV review must report a small open/approach/grasp/release state sequence with raw frames, annotated frames, per-state metadata JSON, target square center and projected square polygon, gripper opening, SimCamera metadata contract checks, and piece visibility/occlusion/clearance rows. The visual review must report stable PNG contact sheets for gripper POV, pose fixture, and pick/place sequence frames, plus distance-annotated pick/place sequence frames, pick/place depth-distance scorecard PNG/JSON, pick/place depth/distance JSON/CSV metrics, pick/place perceived-depth comparison JSON/CSV metrics, pick/place PnP residual diagnostic JSON/CSV metrics, metadata-native SimCamera projection/depth PNG/JSON/CSV metrics, and a copied app-entrypoint frame for convenient bundle browsing. The evidence bundle must write `evidence_bundle/sim_evidence_bundle.md` and `.json` after real projection intake and the real-depth-aware visual-review refresh are complete; missing optional capture-plan artifacts and codec-dependent MP4s remain non-fatal. The depth/distance metrics must label simulator ground truth separately from perceived depth, include camera-to-board/piece distances, target/piece world coordinates, projected pixel coordinates, projection residuals, and a clearly sourced gripper-to-piece proxy when true end-effector depth is unavailable. The depth-distance scorecard must summarize SimCamera ground truth, the metadata-derived rendered-corner PnP baseline, mean/max simulator baseline residuals, corner residuals in pixels, and a `real_depth_reference` section whose status is either `real_depth_comparable` with real-vs-sim residual metrics or `missing_real_depth_reference` with required sidecar inputs. The perceived-depth comparison must add a clearly labeled metadata-derived rendered-board-corner PnP baseline with estimated camera-to-piece/board distances, simulator ground-truth distances, signed/absolute residuals, estimator source/status, and an explicit note that it is not real-camera depth perception. The PnP residual diagnostic must compare simulator ground-truth extrinsics, the rendered-board-corner PnP estimate, and metadata-projected 3D board corners for the same frames; it must report corner ordering assumptions, board size, reprojection residuals, camera-center/board distances, source comparability, and reason labels when sources are not geometrically comparable. The metadata-native projection/depth view must project board corners/center plus per-stage piece and target square centers directly through `camera_metadata.camera_matrix_px` and `camera_metadata.extrinsics.board_to_camera`, report `metadata_projected_pixel_xy`, `camera_frame_xyz_mm`, `camera_z_depth_mm`, `camera_range_mm`, `board_plane_distance_mm`, `source_model: simcamera_metadata`, and link back to the existing depth-distance and PnP diagnostic artifact paths. The real projection intake must link selected real reference media to that metadata-native depth view, report `real_reference_media_path`, `real_intrinsics_status`, `real_board_pose_status`, `real_depth_status`, `sim_metadata_native_depth_view_path`, `sim_expected_projected_points`, `comparable`, `depth_comparable`, `missing_inputs`, next capture requirements, and residual artifacts when real_capture sidecars are present. The app-entrypoint smoke must report a synthetic frame, a metadata sidecar when requested, skipped hardware/gui/OpenAI markers, passing app-facing metadata contract checks, and the same compact `app_camera_status` readout shown by `chess_robot_ui_llm_v2.py --sim`. All four pick/place scenarios must report available visibility evidence, each target release frame path must exist, and each `target_release_open` row must include visible fraction, occlusion fraction, and gripper-clearance fields. The generated artifact index must exist, report `status: "ok"`, have a nonzero artifact count, have no missing artifacts, and include populated categories for the evidence bundle, visual-review contact sheets, sequence frames, depth-distance scorecard, depth/distance metrics, perceived-depth comparison metrics, PnP residual diagnostic metrics, metadata-native projection/depth metrics, real-reference comparisons, real projection intake, ranked candidates, perception fixture evidence, SimCamera pose fixture evidence, IK reachability evidence, gripper-camera POV evidence, app-entrypoint evidence, pick/place scenario release frames, the negative check, and child logs. These are structural availability checks rather than exact metric-value thresholds.

This CI signal is still a simulator/perception regression gate only. It does not connect to SO-101 hardware, open GUI calibration flows, or replace later physical robot validation.

## What This Proves

The suite orchestrates these existing smoke scripts as subprocesses and records each child command, return code, stdout path, stderr path, and expected JSON path under `child_commands`:

- `smoke_sim_reference_media_inventory.py` finds real reference media that can calibrate the simulator.
- `smoke_sim_reference_media_comparison_set.py` runs real-reference comparison artifacts for selected images.
- `smoke_sim_real_projection_intake.py` links selected real media to the metadata-native SimCamera projection/depth view and reports missing real calibration inputs.
- `smoke_sim_real_calibration_sidecars.py` validates hardware-free JSON sidecar schemas for future real intrinsics, extrinsics or board pose, ordered board corners, and metric depth references.
- `smoke_sim_calibration_session_report.py` ranks baseline and perturbed local SimCamera candidates.
- `smoke_sim_perception_regression_fixture.py` packages the selected ranked candidate into perception fixture evidence.
- `smoke_sim_camera_pose_fixture.py` renders deterministic nominal, perturbed, overview, and gripper-state SimCamera pose review frames plus per-case metadata.
- `smoke_sim_ik_reachability_drill.py` records deterministic Cartesian, delta, and radial command feasibility evidence plus explicit missing-model fallback diagnostics.
- `smoke_sim_gripper_camera_pov_review.py` renders deterministic gripper-camera POV frames for open, approach, grasp-window, closed, and release-style gripper states using existing SimCamera/KinematicsTools metadata and piece-visibility geometry.
- `smoke_sim_pick_place_scenario_matrix.py` runs center, edge-file, back-rank, and near-gripper pick/place scenarios.
- `smoke_sim_app_entrypoints.py` verifies simulator app/tool entrypoints and the app-facing SimCamera metadata contract.
- `render_sim_calibration_visual_review.py` composes durable contact-sheet PNGs, distance-annotated pick/place sequence frames, pick/place depth-distance scorecard PNG/JSON, pick/place depth/distance JSON/CSV metrics, and the metadata-native SimCamera projection/depth PNG/JSON/CSV from those generated frames without changing simulator rendering.
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
- `ik_reachability_drill.status: "ok_model_backed"` or `"model_unavailable_fallback_complete"` with `row_count > 0`, populated `counts_by_feasibility`, and summary/CSV/heatmap artifact paths populated
- `ik_reachability_drill.configured_model_path` populated when `--ik-model-path` is supplied, otherwise `null`
- `ik_reachability_drill.configured_model_request` mirrored from the child diagnostic when `--ik-model-path` is supplied
- `gripper_camera_pov_review.status: "ok"` with open/approach/grasp/release state IDs, frame paths, annotated-frame paths, metadata paths, metadata contract checks, target center geometry, gripper state, and piece visibility rows populated
- `visual_review.status: "ok"` with gripper POV, pose fixture, and pick/place sequence contact-sheet PNG paths populated, distance-annotated pick/place sequence frames populated under `frame_sequences`, `depth_distance_scorecard.paths.png`/`.json` populated with the at-a-glance simulator-vs-baseline residual scorecard and missing-real-depth labels, `distance_metrics.paths.json`/`.csv` populated with simulator-ground-truth depth/distance fields, `perceived_depth_comparison.paths.json`/`.csv` populated with estimate-vs-ground-truth residual fields, `pnp_residual_diagnostics.paths.json`/`.csv` populated with source-comparability residual fields, `metadata_native_depth_view.paths.png`/`.json`/`.csv` populated with camera-model-aligned simulator projection/depth fields, and `recordings.*` populated with either a best-effort MP4 path or a skipped reason
- `real_projection_intake.status: "missing_real_depth_reference"` in the current default state, with JSON/CSV/PNG paths populated, `real_reference_media_path` pointing at the selected image, `sim_metadata_native_depth_view_path` populated, `comparable: false`, missing real intrinsics/board-pose/depth inputs listed, residual paths unset, and sidecar valid/invalid/missing counts populated when a manifest declares sidecar paths
- `reference_capture_checklist.status: "action_required"` while only `archive/chess_test_images/current_view.jpg` is represented, with missing video, calibration-target, failure-mode, and post-pick capture requirements listed
- `app_entrypoint_metadata.status: "ok"` with `ok: true`, `frame_path`, `metadata_path`, skipped hardware/gui/OpenAI markers, passing metadata contract checks, and `app_camera_status.ok: true`
- `pick_place_scenario_matrix.aggregate_status.ok: true` with four scenario IDs and release-frame paths populated
- `pick_place_scenario_matrix.piece_visibility.all_scenarios_available: true` with per-scenario visible fraction, occlusion fraction, and gripper clearance values
- `negative_check.status: "no_reference_media_selected"` when `--include-negative-check` is used
- `artifact_index.status: "ok"` with `artifact_count > 0`, `missing_artifact_count: 0`, an existing `path`, and categories covering real-reference comparison, real projection intake, ranked candidate, perception fixture, SimCamera pose fixture, IK reachability, pick/place scenario, negative check, and logs

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
- `ik_reachability_drill/ik_reachability_drill_summary.json`
- `ik_reachability_drill/ik_reachability_drill_rows.csv`
- `ik_reachability_drill/ik_reachability_drill_heatmap.png`
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
- `visual_review/pick_place_depth_distance_scorecard.png`
- `visual_review/pick_place_depth_distance_scorecard.json`
- `visual_review/pick_place_depth_distance_metrics.json`
- `visual_review/pick_place_depth_distance_metrics.csv`
- `visual_review/pick_place_perceived_depth_comparison.json`
- `visual_review/pick_place_perceived_depth_comparison.csv`
- `visual_review/pick_place_pnp_residual_diagnostics.json`
- `visual_review/pick_place_pnp_residual_diagnostics.csv`
- `visual_review/pick_place_metadata_native_depth_view.png`
- `visual_review/pick_place_metadata_native_depth_view.json`
- `visual_review/pick_place_metadata_native_depth_view.csv`
- `visual_review/pick_place_sequence_distance_annotated_sequence.mp4` when OpenCV MP4 writing is available
- `visual_review/app_entrypoint_frame.jpg`
- `real_projection_intake/real_projection_intake.json`
- `real_projection_intake/real_projection_intake.csv`
- `real_projection_intake/real_projection_intake_contact_sheet.png`
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
- `evidence_bundle/sim_evidence_bundle.md`
- `evidence_bundle/sim_evidence_bundle.json`

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

By default, the standalone visual-review command writes deterministic PNG contact sheets, distance-annotated pick/place sequence frames, `pick_place_depth_distance_scorecard.png`/`.json`, `pick_place_depth_distance_metrics.json`/`.csv`, `pick_place_perceived_depth_comparison.json`/`.csv`, `pick_place_pnp_residual_diagnostics.json`/`.csv`, and `pick_place_metadata_native_depth_view.png`/`.json`/`.csv`, then records why no video was produced. The metric files use millimeters for the reviewer-facing fields and label camera-to-board/piece distances as simulator ground truth. The scorecard is the at-a-glance depth/distance artifact: it combines SimCamera ground truth, the metadata-derived rendered-corner PnP baseline, mm/px residual severity, and either `real_depth_comparable` residuals from `real_projection_intake` or a `missing_real_depth_reference` checklist before reviewers inspect the detailed files. The metadata-native depth view is the camera-model-aligned simulator ground-truth view: it projects board corners/center plus per-stage piece and target centers directly through `camera_matrix_px` and `extrinsics.board_to_camera`, reports `metadata_projected_pixel_xy`, `camera_frame_xyz_mm`, `camera_z_depth_mm`, `camera_range_mm`, `board_plane_distance_mm`, and `source_model: simcamera_metadata`, and links back to the depth-distance and PnP diagnostic artifact paths. Use that view for SO-101 chess pickup depth calibration expectations inside the simulator. The real projection intake links that metadata-native JSON/PNG to selected real reference media and writes a contact sheet plus JSON/CSV rows with `missing_real_depth_reference` until real_capture intrinsics, board pose/extrinsics, and depth references are available. The comparison files add `estimated_camera_to_piece_distance_mm`, `ground_truth_camera_to_piece_distance_mm`, `camera_to_piece_error_mm`, `estimated_camera_to_board_plane_distance_mm`, and `camera_to_board_error_mm` using a metadata-derived rendered-board-corner PnP baseline. The PnP residual diagnostic files explain those residuals by comparing the rendered-corner PnP pose against the simulator ground-truth extrinsics and an internal check that projects 3D board corners from SimCamera metadata back to pixels. If the diagnostic reports `rendered_board_corners_do_not_match_metadata_pinhole_projection` or `not_geometrically_comparable`, treat the rendered-corner PnP result as artifact plumbing and not as a depth-calibration authority; use it to diagnose why rendered overlay geometry disagrees with metadata, not to replace the metadata-native projection/depth view. The current gripper-to-piece value is a board-plane proxy from the rendered gripper overlay, and the comparison estimator is explicitly labeled `metadata_derived_baseline` until real camera/depth estimates are compared. A best-effort MP4 can be tried with `--try-video`, and the full regression suite now passes that flag so local/CI bundles include a recording when the OpenCV build supports MP4 writing. PNG contact sheets, frame sequences, and metric JSON/CSV remain the required review artifacts because codec availability varies.

The report includes the category summary table, artifact and missing counts, hardware/gui/OpenAI skipped markers, the current real-media visibility gap, the reference capture checklist, visual-review contact sheets, pick/place sequence frames, pick/place depth-distance scorecard PNG/JSON, pick/place depth/distance metric JSON/CSV, compact per-stage perceived-depth, metadata-native projection/depth, real projection intake, and PnP residual diagnostic tables, real-reference comparison images, ranked candidate captures, perception fixture evidence, SimCamera pose fixture metadata, app-entrypoint metadata evidence, all pick/place release frames, negative-check status, and child stdout/stderr links.

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
- No real camera intrinsics, real board pose/corner detections, or real depth sidecars are declared yet, so the real projection intake should report `status: "missing_real_depth_reference"` and `comparable: false`.
- Synthetic/example-only sidecar fixtures live under `test_data/real_calibration_sidecars/` to prove schema validation paths. They should not be treated as real SO-101 calibration data.
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
        "depth_distance_scorecard": {
            key: summary["visual_review"]["depth_distance_scorecard"].get(key)
            for key in ("status", "review_status", "at_a_glance", "paths")
        },
        "perceived_depth_comparison": {
            key: summary["visual_review"]["perceived_depth_comparison"].get(key)
            for key in ("status", "frame_count", "paths", "aggregate")
        },
        "pnp_residual_diagnostics": {
            key: summary["visual_review"]["pnp_residual_diagnostics"].get(key)
            for key in ("status", "frame_count", "paths", "aggregate")
        },
        "metadata_native_depth_view": {
            key: summary["visual_review"]["metadata_native_depth_view"].get(key)
            for key in ("status", "frame_count", "row_count", "paths", "source_model")
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
