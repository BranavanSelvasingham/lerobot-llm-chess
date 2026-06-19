# Simulator Calibration Regression Gate

Run this hardware-free gate before changing simulator rendering, camera profiles, board/perception calibration, or anything that could affect the SO-101 chess camera path. It exercises the merged simulator calibration regression suite without connecting to the robot or opening GUI display flows.

Current automation objective: prioritize the MuJoCo-based SO-101 chess robot
simulation path before serious policy training. A valid run should make
Gymnasium and MuJoCo runnable, keep reviewed SO-101 model bundle readiness
visible, validate reviewed-bundle handoff into MuJoCo when ready, validate 3D
scene/reset/contact evidence, verify development-fixture grasp/lift/place
physics, collect scripted pick/place rollouts, and
preserve the remaining required items as explicit follow-up: authoritative
model source, reviewed model-file digest, mesh roots, joint/frame/TCP authority,
calibrated gripper offset, base-to-board alignment, and board-source pickup with
reviewed model-backed IK.

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check
```

The suite passes when `/private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json` has `"ok": true` and `"status": "ok"`. It also writes a root `/private/tmp/lerobot_sim/calibration_regression_suite/README.md`, `/private/tmp/lerobot_sim/calibration_regression_suite/evidence_bundle/sim_evidence_bundle.md`, `/private/tmp/lerobot_sim/calibration_regression_suite/evidence_bundle/sim_evidence_bundle.json`, `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index_report.md`, and `/private/tmp/lerobot_sim/calibration_regression_suite/artifact_index.json`. The suite runs the deterministic hardware-free reference capture manifest checker under `reference_capture_manifest/` as automatic evidence, preserving `reference_capture_manifest_check.json`, `reference_capture_manifest_checklist.csv`, and `README.md`. With no manifest it records `reference_capture_manifest_not_supplied` and exits successfully; with `--reference-capture-manifest` it checks the requested local manifest path, capture counts, provenance/review fields, referenced media/sidecar path availability, missing path counts, and `media_assets_copied_into_repo: false`. A nonexistent manifest records `reference_capture_manifest_unavailable` and still exits successfully. This is an input-readiness gate for the missing real depth-reference and pick/place-video evidence only; even `ready_for_calibration_grade_simcamera_tuning: true` is not physical calibration truth. Feed this suite-indexed section into `scripts/plan_real_depth_capture_session.py --calibration-suite-summary-json ...` when preparing the real-depth operator plan; see [docs/real_depth_capture_operator_guide.md](real_depth_capture_operator_guide.md).

Immediately after the reference capture manifest child, the suite runs `scripts/smoke_real_depth_capture_plan_artifact_index.py` under `real_depth_capture_plan_artifact_index/`. That child is deterministic and hardware-free: it runs the real-depth planner bridge smoke under its own output directory, then indexes planner JSON/Markdown outputs, child logs, next operator actions, and the nested bridge-smoke summary without copying, opening, or decoding media. The suite summary, `child_commands`, `artifact_index.json`, root `README.md`, and `artifact_index_report.md` expose `status`, `source_mode`, `case_count`, evidence statuses, ready/not-ready counts, depth-reference and pick/place-video counts, missing path count, no-copy statuses, next action IDs, JSON/CSV/README paths, `bridge_smoke_summary_json`, `media_assets_copied_into_repo: false`, `media_assets_opened_or_decoded: false`, and the caveat that ready evidence is input readiness only.

For a concise operator-facing next-action view, run `scripts/render_real_depth_capture_operator_action_checklist.py` after the suite or focused index. It consumes either `calibration_regression_summary.json` or `real_depth_capture_plan_artifact_index.json` and writes `real_depth_capture_operator_action_checklist.json`, `real_depth_capture_operator_action_checklist_actions.csv`, and `README.md` with evidence source/status, ready/not-ready case counts, depth and pick/place counts, missing path count, no-copy statuses, next operator action IDs/text grouped by missing-input versus ready-input cases, recommended next commands, and explicit no-copy/no-open/no-decode/input-readiness-only caveats. With no input it exits `0` and records missing evidence diagnostics plus commands to run the suite or focused plan index; an explicitly supplied unreadable or invalid JSON exits nonzero and writes an error JSON artifact.

The suite also runs the deterministic hardware-free SO-101 model bundle manifest checker under `so101_model_bundle_manifest/` as automatic evidence, preserving `so101_model_bundle_manifest_summary.json`, `so101_model_bundle_manifest_checklist.csv`, `so101_model_bundle_manifest_review_packet.json`, `so101_model_bundle_manifest_review_packet.csv`, and `README.md`. With no manifest it records `model_bundle_manifest_not_supplied` and exits successfully; with `--so101-model-bundle-manifest` it records the manifest model path, asset roots, reviewed authority/provenance fields, target frame, TCP/gripper-tip offset, base-to-board alignment, child model contract diagnostics, nested asset preflight diagnostics, and a deterministic review packet derived from the current missing inputs. Manifest data is diagnostic-only unless `ready_for_model_backed_ik: true`, and fixture-only readiness remains machine-labeled with `physical_so101_model_authority_ready: false`. The manifest review packet is operator intake only (`review_packet_not_authority`) and does not promote checklist evidence to reviewed physical SO-101 truth. Immediately after that checker, the suite runs the reviewed MuJoCo bundle gate under `so101_reviewed_mujoco_bundle/`, preserving `so101_reviewed_mujoco_bundle_summary.json`, `so101_reviewed_mujoco_bundle_checklist.csv`, `so101_reviewed_mujoco_bundle_motion_checks.csv`, and `README.md`. With no ready manifest it records `reviewed_mujoco_bundle_not_ready` and exits successfully while writing not-attempted rows for every expected SO-101 joint; with a ready manifest it must load the reviewed model in MuJoCo, map every SO-101 joint, find the target frame, and prove SimRobot joint motion before downstream training evidence is trusted. When readiness is true and no explicit `--ik-model-path` was supplied, the suite can derive the downstream contract/IK model path and contract asset roots from that manifest; otherwise explicit `--ik-model-path` and `--ik-model-asset-root` keep precedence and the summary reports why the bundle stayed diagnostic-only. The suite also runs the deterministic hardware-free SO-101 model-source inventory under `so101_model_source_inventory/` before the model contract checker, preserving `so101_model_source_inventory_summary.json`, `so101_model_source_candidates.csv`, `so101_model_source_inventory_review_packet.json`, `so101_model_source_inventory_review_packet.csv`, `so101_model_source_intake_checklist.json`, `so101_model_source_intake_checklist.csv`, and `README.md` as automatic evidence. It records repo-local model-source candidate counts, authoritative-source counts, provenance/license diagnostics, source-authority review-packet status/action IDs, source-intake checklist status/action IDs/command templates, and a recommended contract-check candidate path only when one is discovered; a ready bundle manifest may supply the reviewed model path as inventory root/authoritative path only when no explicit inventory source options were supplied. The inventory review packet and source-intake checklist are operator intake only (`review_packet_not_authority` and `source_intake_not_authority`), keep observed-evidence and physical-authority flags false, and do not promote filenames, joint names, provenance hints, command templates, or fixture evidence to reviewed physical SO-101 truth. The suite now follows that inventory with `so101_model_bundle_probe/`, preserving `so101_model_bundle_probe_summary.json`, `so101_model_bundle.candidate.json`, `so101_model_bundle_review_packet.json`, `so101_model_bundle_review_packet.csv`, `so101_model_bundle_probe_checklist.csv`, `README.md`, and nested contract/manifest-check artifacts. The probe emits a no-model candidate manifest template in default CI or a draft for the selected inventory candidate when available, and it remains `draft_candidate_not_reviewed` scaffolding. Its review packet is operator intake only (`review_packet_not_authority`) and does not copy observed source hints, joint limits, mesh references, TCP, or board-alignment values into reviewed manifest fields. The suite then runs the deterministic hardware-free SO-101 model contract checker under `so101_model_contract/` before the IK reachability drill, preserving `so101_model_contract_summary.json`, `so101_model_contract_checklist.csv`, and `README.md` as automatic evidence. It records model availability, the requested model path, direct `RobotKinematics` usability, target frame, TCP/gripper-tip source hits, and missing model-to-sim alignment inputs before any model-backed IK residuals are trusted. The IK reachability drill still runs under `ik_reachability_drill/` and preserves `ik_reachability_drill_summary.json`, `ik_reachability_drill_rows.csv`, and `ik_reachability_drill_heatmap.png` as part of the contract. Missing repo-local SO-101 model inputs remain non-failing explicit diagnostics: the inventory reports `missing_authoritative_model`, the bundle probe reports `candidate_model_missing` or a draft needing review, the bundle checker reports `model_bundle_manifest_not_supplied` or `model_bundle_manifest_needs_follow_up`, the reviewed MuJoCo bundle gate reports `reviewed_mujoco_bundle_not_ready`, the contract checker reports `missing_model` / `model_not_supplied`, and the IK drill reports `model_unavailable_fallback_complete` rather than a CI failure. For quick depth-calibration review, open `evidence_bundle/sim_evidence_bundle.md` first; it links the depth/distance scorecard, metadata-native depth view, MP4 recordings when available, real projection residual overlay when comparable real sidecars are supplied, and optional capture-plan entries without inventing capture evidence. For the full artifact inventory, open `artifact_index_report.md`; it is a deterministic Markdown view of the compact artifact index and links the highest-signal generated evidence, including the evidence bundle, reference capture manifest JSON/CSV/README, the Real Depth Capture Plan Artifact Index JSON/CSV/README and nested bridge-smoke summary, reference capture checklist, reference camera tuning diagnostics JSON/CSV/README/optional scorecard, the suite-indexed SimCamera Profile Sweep, the suite-indexed SimCamera Tuning Before/After JSON/CSV/README and child sweep images, visual-review contact sheets, the gripper-camera POV review, the pose fixture, the SO-101 model-source inventory summary/CSV/review-packet/source-intake checklist/README, the SO-101 model bundle probe summary/candidate-manifest/review-packet/checklist/README, the SO-101 model bundle manifest summary/checklist/review-packet/README, the SO-101 reviewed MuJoCo bundle summary/checklist/motion-checks/README, nested child artifacts when a model path is supplied, the SO-101 model contract summary/CSV/README, the IK reachability summary/CSV/heatmap, the pick/place gripper-camera sequence, the pick/place depth/distance scorecard PNG/JSON, the pick/place depth/distance JSON/CSV, the pick/place perceived-depth comparison JSON/CSV, the pick/place PnP residual diagnostic JSON/CSV, the metadata-native SimCamera projection/depth PNG/JSON/CSV, the real projection intake JSON/CSV/contact sheet, and the app-entrypoint frame. For image-first inspection, open `simcamera_tuning_before_after/baseline_profile_sweep/candidate_montage.jpg`, `simcamera_tuning_before_after/current_profile_sweep/candidate_montage.jpg`, `visual_review/pick_place_depth_distance_scorecard.png`, `visual_review/pick_place_sequence_distance_annotated_contact_sheet.png`, `visual_review/gripper_camera_pov_annotated_contact_sheet.png`, `visual_review/sim_camera_pose_fixture_annotated_contact_sheet.png`, `visual_review/pick_place_metadata_native_depth_view.png`, `ik_reachability_drill/ik_reachability_drill_heatmap.png`, `real_projection_intake/real_projection_intake_contact_sheet.png`, and `reference_camera_tuning_diagnostics/reference_camera_tuning_scorecard.png` when produced; for metric review, inspect `evidence_bundle/sim_evidence_bundle.json`, `reference_capture_manifest/reference_capture_manifest_check.json`, `reference_capture_manifest/reference_capture_manifest_checklist.csv`, `real_depth_capture_plan_artifact_index/real_depth_capture_plan_artifact_index.json`, `real_depth_capture_plan_artifact_index/real_depth_capture_plan_artifact_index_cases.csv`, `real_depth_capture_plan_artifact_index/bridge_smoke/real_depth_capture_plan_manifest_bridge_smoke_summary.json`, `simcamera_tuning_before_after/simcamera_tuning_before_after_summary.json`, `simcamera_tuning_before_after/simcamera_tuning_before_after_rows.csv`, `reference_camera_tuning_diagnostics/reference_camera_tuning_diagnostics.json`, `reference_camera_tuning_diagnostics/reference_camera_tuning_diagnostics.csv`, `so101_model_bundle_probe/so101_model_bundle_probe_summary.json`, `so101_model_bundle_probe/so101_model_bundle.candidate.json`, `so101_model_bundle_probe/so101_model_bundle_review_packet.json`, `so101_model_bundle_probe/so101_model_bundle_review_packet.csv`, `so101_model_bundle_manifest/so101_model_bundle_manifest_summary.json`, `so101_model_bundle_manifest/so101_model_bundle_manifest_checklist.csv`, `so101_model_bundle_manifest/so101_model_bundle_manifest_review_packet.json`, `so101_model_bundle_manifest/so101_model_bundle_manifest_review_packet.csv`, `so101_reviewed_mujoco_bundle/so101_reviewed_mujoco_bundle_summary.json`, `so101_reviewed_mujoco_bundle/so101_reviewed_mujoco_bundle_checklist.csv`, `so101_reviewed_mujoco_bundle/so101_reviewed_mujoco_bundle_motion_checks.csv`, `so101_model_source_inventory/so101_model_source_inventory_summary.json`, `so101_model_source_inventory/so101_model_source_candidates.csv`, `so101_model_source_inventory/so101_model_source_inventory_review_packet.json`, `so101_model_source_inventory/so101_model_source_inventory_review_packet.csv`, `so101_model_source_inventory/so101_model_source_intake_checklist.json`, `so101_model_source_inventory/so101_model_source_intake_checklist.csv`, `so101_model_contract/so101_model_contract_summary.json`, `so101_model_contract/so101_model_contract_checklist.csv`, `visual_review/pick_place_depth_distance_scorecard.json`, `visual_review/pick_place_depth_distance_metrics.json` or `.csv`, `visual_review/pick_place_perceived_depth_comparison.json` or `.csv`, `visual_review/pick_place_pnp_residual_diagnostics.json` or `.csv`, `visual_review/pick_place_metadata_native_depth_view.json` or `.csv`, `ik_reachability_drill/ik_reachability_drill_summary.json`, `ik_reachability_drill/ik_reachability_drill_rows.csv`, and `real_projection_intake/real_projection_intake.json` or `.csv`. The root `README.md` repeats those entrypoints, the core JSON summaries, the hardware/gui/OpenAI skipped markers, and the current real-media gap.

The bundle manifest checker also preserves `so101_model_bundle_manifest_intake_checklist.json`, `so101_model_bundle_manifest_intake_checklist.csv`, and `so101_model_bundle_manifest_template.json`. The intake files turn the current missing reviewed-bundle fields into rerun command templates and must stay labeled `bundle_manifest_intake_not_authority` with false observed-evidence and physical-truth flags. The template artifact is a copyable reviewed-manifest scaffold only; it stays labeled `reviewed_manifest_template_not_authority` and cannot close physical SO-101 authority without reviewed inputs and a passing rerun.

The bundle manifest checker now also records `model_identity`: the declared
`model_sha256`, the observed SHA-256 of the resolved `model_path`, match status,
and digest diagnostics. A missing, malformed, or mismatched digest keeps
`ready_for_model_backed_ik` false, so the reviewed MuJoCo bundle gate does not
load or move a stale model file.

The suite also runs `smoke_sim_reference_media_inventory.py` as the first child under `reference_media_inventory/`, preserving `reference_media_inventory.json`, `reference_media_inventory.csv`, and `README.md`. `calibration_regression_summary.json.reference_media_inventory` records inventory status, candidate/image/video/calibration-data counts, currently wired media count, current gripper reference detection, `reference_gaps`, artifact paths, scan roots, and child command diagnostics. The artifact index adds a `reference_media_inventory` category and the rendered report includes a `Reference Media Inventory` section before selected-media and visibility-gap tables.

The follow-on `smoke_sim_reference_media_comparison_set.py` child reads that inventory JSON and writes `comparison_set/comparison_set_summary.json`, `comparison_set/reference_media_comparison_rows.csv`, `comparison_set/README.md`, and, when OpenCV/numpy rendering is available, `comparison_set/reference_media_comparison_contact_sheet.png` plus per-reference derived visual comparisons. Candidate selection is deterministic: active/current gripper reference first, then `camera_pov` + `chessboard_board` + `gripper_arm` class coverage, repo-local paths before external absolute sibling evidence, and image rows before video or calibration-data-only rows. `calibration_regression_summary.json.comparison_set`, `child_commands.comparison_set.diagnostics`, `artifact_index.json.reference_media_comparison`, and the rendered `Reference Media Comparison` report section expose status, selected candidate/media counts, visual comparison count, contact sheet path/status, JSON/CSV/README paths, `media_assets_copied_into_repo: false`, external selected count, and the missing depth/pick-place-video/no-video diagnostics. Its diagnostics intentionally preserve `missing_depth_reference`, `missing_pick_place_video`, `no_videos`, synthetic/example rows as non-closing real gaps, and external absolute paths as local evidence only.

The suite then invokes `smoke_sim_reference_camera_tuning_diagnostics.py` as a child under `reference_camera_tuning_diagnostics/`, passing the child-produced `comparison_set/comparison_set_summary.json`. It writes `reference_camera_tuning_diagnostics.json`, `reference_camera_tuning_diagnostics.csv`, `README.md`, and an optional `reference_camera_tuning_scorecard.png` when OpenCV/numpy can read existing visual artifacts. `calibration_regression_summary.json.reference_camera_tuning_diagnostics`, `child_commands.reference_camera_tuning_diagnostics.diagnostics`, `artifact_index.json.reference_camera_tuning_diagnostics`, and the rendered `Reference Camera Tuning Diagnostics` report section expose status, selected comparison count, visual comparison count, metadata-only count, suggested tuning dimensions, scorecard path/status, JSON/CSV/README paths, `media_assets_copied_into_repo: false`, external local-only evidence, and carried `missing_depth_reference`, `missing_pick_place_video`, and `no_videos` gaps. If metrics or images are absent, status can be `metadata_only` or `no_reference_media_selected` and still exit successfully.

The suite also runs `smoke_sim_profile_calibration_sweep.py` as a deterministic child under `sim_camera_profile_sweep/`, using the current gripper-reference profile, the default `archive/chess_test_images/current_view.jpg` reference image, and fixed marker time `0.0`. It preserves `summary.json`, `candidate_montage.jpg`, current/best overlay, side-by-side, absolute-difference heatmap images, and all candidate frames under `sim_camera_profile_sweep/candidates/`. `calibration_regression_summary.json.sim_camera_profile_sweep`, `child_commands.sim_camera_profile_sweep.diagnostics`, `artifact_index.json.sim_camera_profile_sweep`, and the rendered `SimCamera Profile Sweep` report section expose status, profile name, current gripper finger width, marker time, candidate count, current MAD/RMSE, best candidate id/name, best MAD/RMSE, deltas versus current, ranked candidates, remaining tuning prompts, and the caveat that full-frame image delta is hardware-free coarse review evidence only.

The suite also runs `smoke_simcamera_tuning_before_after.py` as a deterministic child under `simcamera_tuning_before_after/`, using the documented `72px` baseline gripper finger-width override, the current canonical `current_gripper_reference` profile, the default reference image, and fixed marker time `0.0`. It preserves `simcamera_tuning_before_after_summary.json`, `simcamera_tuning_before_after_rows.csv`, `README.md`, and child profile sweep artifacts under `baseline_profile_sweep/` and `current_profile_sweep/`: summaries, montages, current/best overlays, absolute-difference heatmaps, side-by-side images, and candidate directories. `calibration_regression_summary.json.simcamera_tuning_before_after`, `child_commands.simcamera_tuning_before_after.diagnostics`, `artifact_index.json.sim_camera_tuning_before_after`, and the rendered `SimCamera Tuning Before/After` report section expose before/after status, baseline/current widths, marker time, current-vs-baseline MAD/RMSE deltas, best-candidate deltas, candidate counts, remaining prompt count/details, `media_assets_copied_into_repo: false`, artifact paths, carried `missing_real_depth_reference` and `missing_pick_place_video` gaps, and the caveat that full-frame image delta is hardware-free coarse evidence rather than physical calibration truth. Dependency gaps stay non-failing only when the standalone child reports `dependency_unavailable`; normal child failures still fail the suite.

Current gripper-reference SimCamera tuning uses these diagnostics as hardware-free evidence only. The 2026-06-16 owner check under `/private/tmp/lerobot_sim/simcamera_tuning_owner_check` first recorded baseline suite diagnostics with selected comparisons `3`, visual comparisons `1`, metadata-only rows `2`, `media_assets_copied_into_repo: false`, missing depth reference `true`, missing pick/place video `true`, and artifact-index missing artifacts `0`. The reviewed deterministic profile sweep compared the previous `72px` gripper finger width against the `fingers_narrow_8px` candidate and promoted the conservative `64px` finger width: the current-profile mean absolute delta against `archive/chess_test_images/current_view.jpg` moved from `74.013` to `73.690`, with board corners still sourced from `camera_metadata_pinhole_projection` and tracked gripper opening still `47px`. Each suite run now reruns the sweep for the current profile, keeps narrower opening/finger and board-framing candidates as review prompts when ranked, and does not claim physical calibration truth.

For focused review of future gripper-reference tuning changes, the same before/after child can be run standalone before changing the canonical profile or rerunning the full suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_simcamera_tuning_before_after.py --output-dir /private/tmp/lerobot_sim/simcamera_tuning_before_after --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --baseline-gripper-finger-width-px 72 --marker-time-seconds 0.0
```

The smoke reuses `smoke_sim_profile_calibration_sweep.py` twice under `baseline_profile_sweep/` and `current_profile_sweep/`. The baseline child applies the documented gripper finger-width override, defaulting to the previous `72px` value; the current child uses the checked-out canonical `current_gripper_reference` profile. It writes `simcamera_tuning_before_after_summary.json`, `simcamera_tuning_before_after_rows.csv`, and `README.md` at the requested output root. Those files report baseline/current profile names, gripper finger widths, fixed marker time, candidate counts, current-vs-best MAD/RMSE, the current-profile delta versus the baseline current candidate, best-candidate deltas, gripper overlay inputs, remaining review prompts, and paths to each child sweep summary, montage, current/best overlay, absolute-difference, and side-by-side images.

This before/after smoke is a formal review path for the suite-indexed SimCamera Profile Sweep, not a new tuning source of truth. It records `media_assets_copied_into_repo: false`, does not copy or modify media assets, does not mutate `SIM_CAMERA_CALIBRATION_PROFILES`, and preserves missing real depth-reference and pick/place-video gaps unless separate reviewed real sidecars/captures exist.

The suggested dimensions are review prompts for future simulator tuning only: camera framing/board scale/board crop, board color/texture/lighting, gripper overlay geometry/occlusion, piece size/contrast, and missing depth/video capture needs. This diagnostics path does not update SimCamera constants, renderer behavior, camera/UI runtime, robot execution, OpenAI/LLM paths, IK behavior, or media assets. Synthetic comparison evidence remains hardware-free review evidence and does not close missing real depth-reference or pick/place-video gaps.

When operators produce the missing real depth-reference and pick/place-video inputs, pass the local manifest to the integrated [reference capture manifest checker](sim_reference_capture_manifest.md):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_capture_manifest --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --reference-capture-manifest /absolute/path/to/reference_capture_manifest.json
```

The suite writes `reference_capture_manifest/reference_capture_manifest_check.json`, `.csv`, and `README.md`, carries the same fields into `calibration_regression_summary.json.reference_capture_manifest`, and indexes them under the `Reference Capture Manifest` report section. This sits after reference media inventory, reference comparison, reference camera tuning diagnostics, and SimCamera before/after evidence: those children show what local media exists and which gaps remain, while the manifest checker shows whether the operator has supplied reviewed real capture inputs for the missing depth-reference and pick/place-video gaps. It still does not copy media, mutate SimCamera constants, or make physical calibration claims.

To scan optional sibling evidence without committing media assets, pass repeatable roots:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_reference_roots --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --reference-media-root . --reference-media-root /absolute/path/to/reference/media/root
```

Supplying `--reference-media-root` forwards repeatable `--root` values to the inventory child and replaces the default repo-root-only inventory scan. Use `--reference-media-root .` when adding a sibling checkout. Empty explicit roots remain non-failing evidence: the inventory reports `media_inventory_empty`, the comparison-set child records `no_reference_media_selected` as a non-failing diagnostic, and the rest of the hardware-free suite still writes deterministic artifacts.

To ask the integrated suite to try model-backed IK, pass an optional model path:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_model --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --ik-model-path /absolute/path/to/so101.urdf
```

That still stays hardware-free. The integrated model-source inventory always
runs first against its default repo-local roots and does not treat
`--ik-model-path` as authoritative source evidence. The suite forwards the
optional path only to `scripts/smoke_sim_so101_model_contract.py --model-path`
and `scripts/smoke_sim_ik_reachability_drill.py --model-path`, preserves those
child commands under `child_commands.so101_model_contract.command` and
`child_commands.ik_reachability_drill.command`, and exposes the contract result
under `so101_model_contract.status`, `so101_model_contract.model_request_status`,
`so101_model_contract.robot_kinematics_status`, and
`so101_model_contract.artifacts`. The IK drill continues to expose the requested
path under `ik_reachability_drill.configured_model_path`, with the richer
request probe mirrored under `ik_reachability_drill.configured_model_request`,
plus `ik_reachability_drill.model_diagnostic.selected_model_path` when the
child can use it. If the supplied path is missing or unusable, the suite still
exits successfully and records a `missing_model` or `model_unavailable`
diagnostic instead of turning the hardware-free gate red. The contract section
also mirrors the child asset-preflight result under
`so101_model_contract.model_asset_preflight`, including `status`,
`mesh_reference_count`, `present_asset_count`, `missing_asset_count`,
`unresolved_reference_count`, and child artifact paths. The artifact index and
Markdown report expose the same data in a dedicated
`so101_model_asset_preflight` category before IK reachability, so missing mesh
or unresolved asset references are visible before residual checks.

If the reviewed model file and mesh/assets directory are separate, add
repeatable suite-level asset roots:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_model_assets --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --ik-model-path /absolute/path/to/so101.urdf --ik-model-asset-root /absolute/path/to/assets
```

`--ik-model-asset-root` is forwarded only to
`scripts/smoke_sim_so101_model_contract.py --model-asset-root`, which forwards
it to the nested asset preflight as `--asset-root`. It is not forwarded to the
IK reachability drill and does not alter `RobotKinematics` arguments. The suite
records the configured roots under `so101_model_contract_config`, mirrors the
contract checker root diagnostics under
`so101_model_contract.model_asset_root_configuration`, and preserves the nested
preflight roots/counts under
`so101_model_contract.model_asset_preflight`. A nonexistent asset root remains
non-failing diagnostic evidence; checked paths are still visible in the child
CSV/summary so reviewers can see what would have resolved.

To ask the integrated suite to scan reviewed model-source locations, pass
suite-level inventory options. These forward only to
`scripts/smoke_sim_so101_model_source_inventory.py`:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_reviewed_source --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --so101-model-source-root /absolute/path/to/reviewed/source/root --so101-authoritative-model-root /absolute/path/to/reviewed/source/root
```

Use `--so101-model-source-root` to replace the inventory child's default
repo-local scan roots. Use `--so101-model-source-extra-root` to keep the default
repo-local roots and append an additional root. Use
`--so101-authoritative-model-path` or `--so101-authoritative-model-root` only
after provenance, license, mesh dependencies, and source authority have been
reviewed. Pair authoritative declarations with
`--so101-source-authority-source-reference`,
`--so101-source-authority-license-basis`, all three
`--so101-source-authority-review-scope` values (`model_identity`, `provenance`,
and `license`), `--so101-source-authority-reviewed-by`, and a stable artifact
handle: `--so101-source-authority-review-id` or
`--so101-source-authority-review-url`. The review-evidence groups are recorded
as `source_authority_review.review_evidence_required_groups`,
`review_evidence_satisfied_required_groups`, and
`review_evidence_missing_required_groups`; a reviewer identity without an
artifact handle is still blocked as `authority_review_evidence:review_trace`
and `authority_review_evidence:review_artifact`. Placeholder
source references or license bases are recorded as
`required_metadata_placeholder_fields` and do not satisfy source-authority
readiness. The scope fields are recorded as
`source_authority_review_scope_ready`,
`source_authority_required_review_scope_ids`,
`source_authority_supplied_review_scope_ids`, and
`source_authority_missing_review_scope_ids`, so a generic reviewer token cannot
close source authority by itself. The source/root options are repeatable. When
these options are supplied, the
suite records them in
`calibration_regression_summary.json.so101_model_source_inventory.source_configuration`,
mirrors them in `so101_model_source_inventory_config`, preserves the exact child
command in `child_commands.so101_model_source_inventory.command`, and surfaces
them in `artifact_index.json` and `artifact_index_report.md`. The source
inventory summary also exposes `source_authority_gate_status` and
`source_authority_blockers` so missing authoritative source or missing review
metadata remains machine-readable before any bundle manifest is trusted.
If an authoritative root matches multiple model files, the suite reports
`so101_model_source_inventory.status: "ambiguous_authoritative_model"`,
`authoritative_source_selection_status: "multiple_authoritative_candidates"`,
and `source_authority_blocked_ambiguous_authoritative_model`; narrow the root or
rerun with `--so101-authoritative-model-path` so exactly one reviewed model
source is selected before bundle consistency or MuJoCo motion can close.

This reviewed-source mode still does not import, copy, or fabricate model
assets. An empty reviewed root is valid evidence that no authoritative source
was found: the suite should still exit `0` with
`so101_model_source_inventory.status: "missing_authoritative_model"`,
`candidate_count: 0`, `authoritative_candidate_count: 0`,
`source_authority_gate_status` set to
`source_authority_blocked_missing_authoritative_model`, and a source-inventory
review packet with `review_packet_model_authority: "review_packet_not_authority"`.
`--ik-model-path`
continues to mean "try this model path in the contract checker and IK drill";
it never marks source authority for the inventory. To use the same file as an
authoritative source, pass it separately through
`--so101-authoritative-model-path` after review.

To inspect model-source roots outside the integrated suite, run the focused
hardware-free model-source inventory:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_source_inventory.py --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_preflight
```

See [docs/sim_so101_model_source_inventory.md](sim_so101_model_source_inventory.md)
for the inventory schema, default roots, external-root workflow, and missing
provenance/alignment inputs. The inventory should identify an authoritative
candidate before `--ik-model-path` results are treated as more than explicit
missing-model or untrusted-model diagnostics. After selecting a candidate, run
the focused hardware-free contract checker:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_contract.py --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight
```

To inspect a candidate model explicitly:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

This checker writes `so101_model_contract_summary.json`,
`so101_model_contract_checklist.csv`, `README.md`, and nested
`so101_model_asset_preflight/` summary/CSV/README evidence. It records whether the
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

For a reviewed model-backed IK bundle, use
[docs/sim_so101_model_bundle_manifest.md](sim_so101_model_bundle_manifest.md)
to validate one JSON manifest that ties together the selected model path,
asset roots, authority/provenance, reviewed joint-limit authority, mesh evidence,
target-frame/TCP offset, and base-to-board alignment. The integrated suite runs that checker automatically in
no-manifest diagnostic mode.

If you have a candidate model path and mesh roots but not a reviewed manifest,
run the focused probe/generator first:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_bundle_probe.py --model-path /absolute/path/to/so101.urdf --asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/so101_model_bundle_probe
```

When source authority has already been reviewed, pass reviewer metadata plus all
top-level authority scopes before expecting the candidate manifest to carry a
non-empty `authority` block:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_model_bundle_probe.py --model-path /absolute/path/to/so101.urdf --asset-root /absolute/path/to/assets --authority-reviewed-by operator --authority-review-id review-ticket --authority-review-scope model_identity --authority-review-scope provenance --authority-review-scope license --output-dir /private/tmp/lerobot_sim/so101_model_bundle_probe
```

The probe writes `so101_model_bundle.candidate.json`,
`so101_model_bundle_probe_summary.json`,
`so101_model_bundle_review_packet.json`,
`so101_model_bundle_review_packet.csv`,
`so101_model_bundle_probe_checklist.csv`, and nested child evidence from the
existing model contract checker, asset preflight, and bundle manifest checker.
The integrated suite now also runs this probe automatically under
`so101_model_bundle_probe/` after the model-source inventory. When the inventory
has a recommended contract-check candidate, the suite forwards that candidate to
the probe; otherwise default CI still emits a no-model candidate manifest
template as explicit, non-failing review scaffolding. The probe is intended to
follow the model-source inventory and precede a reviewed manifest: it does not
scan for authority, does not copy external assets, and does not fill calibrated
TCP or base-to-board values. The generated draft keeps
`authority` and `provenance` empty by default, records TODO placeholders for
joint limits, TCP, and base-to-board alignment, and therefore remains
diagnostic-only until the manifest checker reports
`ready_for_model_backed_ik: true`.
The integrated suite forwards ready source-authority reviewer metadata and
scopes into the probe only when a candidate model is present; it does not use
source-review metadata to authorize a no-model default run.
The review packet groups observed candidate source, joint-limit, mesh, TCP, and
board-alignment evidence into operator review items, but it reports
`model_authority: "review_packet_not_authority"` and never fills reviewed
manifest fields itself.

The model-source inventory and bundle manifest checker reject placeholder review
evidence. Non-empty values such as `TODO`, `TBD`, `unknown`, or `placeholder`
are recorded as diagnostics and do not satisfy source-authority, joint-limit,
mesh-asset, target-frame, TCP-offset, or base-to-board authority readiness.

To supply a reviewed bundle to the suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_bundle --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 --include-negative-check --so101-model-bundle-manifest /absolute/path/to/so101_model_bundle.json
```

The suite records the exact child command under
`child_commands.so101_model_bundle_manifest.command` and exposes
`so101_model_bundle_manifest.status`,
`so101_model_bundle_manifest.ready_for_model_backed_ik`,
`so101_model_bundle_manifest.physical_authority_gate_status`,
`so101_model_bundle_manifest.physical_authority_blockers`,
`so101_model_bundle_manifest.model_path`,
`so101_model_bundle_manifest.asset_roots`,
`so101_model_bundle_manifest.joint_limits`,
`so101_model_bundle_manifest.mesh_assets`,
`so101_model_bundle_manifest.target_frame`,
`so101_model_bundle_manifest.tcp_offset`,
`so101_model_bundle_manifest.base_to_board_alignment`,
`so101_model_bundle_manifest.contract_checker`,
`so101_model_bundle_manifest.model_asset_preflight`,
`so101_model_bundle_manifest.review_packet_status`,
`so101_model_bundle_manifest.review_packet_action_ids`, and
`so101_model_bundle_manifest.forwarding` in the top-level summary. If the
bundle is not ready, or if an explicit `--ik-model-path` was supplied, the
manifest remains diagnostic-only and the forwarding reason is preserved. If the
bundle is ready and no explicit `--ik-model-path` was supplied, the suite may
derive the downstream contract/IK model path and contract asset roots from the
manifest. Explicit `--ik-model-asset-root` values still take precedence for the
contract checker asset preflight.

The top-level summary also exposes `so101_reviewed_model_authority_gate`, which
aggregates the source inventory, bundle manifest, and reviewed MuJoCo handoff.
It reports `reviewed_model_authority_ready` only when source authority,
physical bundle authority, source-to-bundle model path/digest consistency, and
physical-reviewed MuJoCo motion are all true, and when no child summary is
still carrying hardware-free fixture readiness or fixture-motion evidence;
otherwise it reports ordered blockers and keeps downstream fixture evidence
separate from reviewed physical SO-101 truth. The source inventory must
identify the same reviewed model path and SHA-256 digest as the bundle
manifest. The
suite also writes the same
gate under `so101_reviewed_model_authority_gate/` as JSON, checklist CSV,
blocker-packet, and README review artifacts so the current highest-priority
blocker can be inspected without digging through the full suite summary. The
checklist CSV preserves priority, status, prior-blocker IDs, and next-action IDs
from the blocker packet, so downstream MuJoCo motion rows remain
`blocked_by_prior_requirements` until source and physical bundle authority are
ready. The gate summary also rolls child source-inventory, bundle-manifest, and
reviewed-MuJoCo missing work into ordered `next_required_for_goal`,
`next_required_action_ids`, and `next_required_action_count` fields. The blocker
packet is review intake only
(`blocker_packet_not_authority`); its immediate `blocker_packet_next_action_ids`
must be included in that ordered gate queue while development fixture evidence
stays outside reviewed physical SO-101 truth. The source/bundle consistency
item must point at the exact failed sub-step: missing model path, path mismatch,
missing model SHA-256, or digest mismatch.

The suite also records the reviewed MuJoCo handoff under
`so101_reviewed_mujoco_bundle/`. It consumes the bundle manifest checker's
summary, exits successfully with `reviewed_mujoco_bundle_not_ready` while no
ready reviewed bundle exists, and becomes a hard model-load/joint-motion gate
when the manifest reports `ready_for_model_backed_ik: true`. Its summary keeps
`reviewed_model_motion_checked` as the compatibility motion flag and adds
`motion_authority_status`, `physical_reviewed_model_motion_checked`,
`hardware_free_fixture_motion_checked`, and
`motion_evidence_not_physical_so101_authority` to separate reviewed physical
SO-101 authority from fixture-only automation coverage. Focused usage:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_reviewed_mujoco_bundle.py --manifest-path /absolute/path/to/so101_model_bundle.json --require-ready-reviewed-model --output-dir /private/tmp/lerobot_sim/so101_reviewed_mujoco_bundle_required
```

See [docs/sim_so101_reviewed_mujoco_bundle.md](sim_so101_reviewed_mujoco_bundle.md)
for the focused gate contract.

The integrated suite also runs the SO-101 MuJoCo development gates as automatic
evidence: `so101_reviewed_mujoco_bundle/`, `so101_mujoco_scene/`,
`so101_chess_env/`, `so101_env_resets/`, `so101_mujoco_contact_probe/`,
`so101_mujoco_grasp_probe/`, `so101_mujoco_board_pick_probe/`, and
`so101_training_readiness_gate/`, and `so101_training_rollouts/`. These children
require Gymnasium and MuJoCo, generate or consume the development-only MJCF
scaffold, validate resettable chess-piece freejoint state, prove board contact,
record gripper-contact fixture evidence, verify development-fixture lift/place
physics when contact, transfer, target placement, board contact, and retreat
checks pass, verify seeded development board-source pick/place, and collect
deterministic scripted rollout JSONL/CSV evidence only after the board-pick
summary is supplied as a rollout prerequisite. The training-readiness gate
aggregates reviewed model authority, reviewed model-backed board-source
pick/place, and rollout authority into one explicit serious-training blocker.
It also emits `priority_gate_queue`, `priority_gate_order`,
`next_priority_gate_id`, `next_priority_action_ids`, and
`so101_training_readiness_gate_priority_queue.csv` so the missing work stays
ordered as reviewed model authority, MuJoCo scene validity, Gymnasium task
wiring, scripted contact/grasp/pick/place evidence, and only then focused
training rollouts. A later gate can carry hardware-free automation evidence
while remaining `blocked_by_prior_requirements` or `development_evidence_only`
until the earlier reviewed SO-101 gate is physically authoritative. They are
priority automation gates for the 3D training path, but serious training
remains blocked until the reviewed MuJoCo bundle gate reports motion checked and
board-source pickup works with reviewed model-backed IK. See
[SO-101 reviewed MuJoCo bundle](sim_so101_reviewed_mujoco_bundle.md),
[SO-101 MuJoCo scene](sim_so101_mujoco_scene.md),
[SO-101 chess env](sim_so101_chess_env.md),
[SO-101 env resets](sim_so101_env_resets.md),
[SO-101 contact probe](sim_so101_mujoco_contact_probe.md),
[SO-101 grasp probe](sim_so101_mujoco_grasp_probe.md),
[SO-101 board pick probe](sim_so101_mujoco_board_pick_probe.md), and
[SO-101 training rollouts](sim_so101_training_rollouts.md).

To guard the source-authority state machine without hardware or repo-local
SO-101 assets, run the focused source-authority matrix smoke:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_source_authority_matrix.py --output-dir /private/tmp/lerobot_sim/so101_source_authority_matrix --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
```

The smoke creates synthetic URDF fixtures under the output directory, invokes
`scripts/smoke_sim_so101_model_source_inventory.py` for missing-root,
unverified-candidate, missing-review-metadata, placeholder-review-metadata,
thin-review-metadata, placeholder-source/license-metadata,
non-SO-101 authoritative-source rejection, complete-source-review,
single-authoritative-root review, and ambiguous-authoritative-root cases, and writes
`so101_source_authority_matrix_summary.json`,
`so101_source_authority_matrix_cases.csv`, and `README.md`. The
source-authority-ready fixture case proves only the inventory state transition
to `source_authority_ready`, including that a narrowed authoritative root
selects the same authoritative model path as an explicit authoritative path;
the non-SO-101 authoritative fixture must stay blocked and must not queue bundle
probing even when complete review metadata is supplied;
every case keeps `source_intake_not_authority`,
`review_packet_not_authority`, and false physical-authority flags.

To guard the bundle-forwarding contract without hardware or repo-local SO-101
assets, run the focused ready-bundle smoke:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_bundle_ready_forwarding.py --output-dir /private/tmp/lerobot_sim/so101_bundle_ready_forwarding --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
```

The smoke creates synthetic manifests, a fixture-only ready MJCF model, and
mesh fixtures under the output directory, invokes
`scripts/smoke_sim_calibration_regression_suite.py` as the system under test,
and writes
`so101_bundle_ready_forwarding_summary.json`,
`so101_bundle_ready_forwarding_cases.csv`, and `README.md`. It requires a ready
manifest to forward the manifest-derived model path and mesh asset root when no
explicit `--ik-model-path` is supplied, requires the reviewed MuJoCo bundle
gate to report `reviewed_mujoco_bundle_motion_checked` for the ready MJCF
fixture while preserving `hardware_free_fixture_motion_checked` as non-physical
SO-101 authority, requires explicit `--ik-model-path` to take precedence and
leave the ready manifest diagnostic-only for downstream IK/contract forwarding,
requires a ready-shaped manifest with mismatched `model_sha256` to remain not
ready and not forward, requires incomplete placeholder-alignment,
placeholder-review, thin-review, invalid-review-URL, and placeholder-provenance
manifests to remain not ready and not forward, requires accepted review metadata
to include reviewer identity plus a stable artifact handle (`review_id` or
HTTP(S) `review_url`), requires
the current simulator-contract target frame
`gripper_frame_link` to be declared and visible in the actual model before
forwarding, requires malformed TCP-offset and base-to-board transform payloads
to remain diagnostic-only instead of forwarding to downstream contract/IK
checks, and requires
`artifact_index.missing_artifact_count: 0` for every suite case.

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

For the root-scanning inventory that emits JSON, CSV, README, real-reference classifications, optional sibling-root evidence, and explicit visibility gaps, see [docs/sim_reference_media_inventory.md](sim_reference_media_inventory.md).

See [docs/sim_reference_media_intake.md](sim_reference_media_intake.md) for the manifest fields used to describe camera POV, board/piece/gripper visibility, calibration target intent, failure-mode coverage, simulator profile wiring, and limitations for future repo-local SO-101 photos/videos.

## GitHub Actions Signal

The focused `Simulator Calibration Regression` workflow runs the same hardware-free suite for pull requests targeting `feat/telemetry-recording` when simulator, camera, chess perception, smoke-script, report-renderer, reference-image, or gate documentation paths change. It uses Python 3.12, installs only the Python modules needed by this suite, verifies the generated summary fields, now checks the reference media inventory JSON/CSV/README, reference camera tuning diagnostics JSON/CSV/README/optional scorecard, integrated SO-101 model bundle manifest JSON/CSV/README, SO-101 reviewed model authority gate JSON/checklist/blocker-packet/README, SO-101 model bundle probe JSON/candidate/review-packet/checklist/README, SO-101 reviewed MuJoCo bundle JSON/checklist/motion-checks/README, SO-101 model-source inventory JSON/CSV/review-packet/source-intake/README, the focused SO-101 source-authority matrix JSON/CSV/README, the focused SO-101 model-bundle manifest matrix JSON/CSV/README, the focused SO-101 reviewed-authority gate matrix JSON/CSV/README, the focused SO-101 reviewed-MuJoCo bundle matrix JSON/CSV/README, the focused SO-101 MuJoCo scene matrix JSON/CSV/README, the focused SO-101 chess-env matrix JSON/CSV/README, the focused SO-101 board-pick probe matrix JSON/CSV/README, the focused SO-101 training-rollouts matrix JSON/CSV/README, the focused SO-101 training-readiness gate matrix JSON/CSV/README, the SO-101 model contract JSON/CSV/README, and the IK reachability summary/CSV/heatmap contract. It writes a job summary naming the uploaded artifact, asserting the focused model-bundle manifest matrix artifacts, and printing the matrix status, case count, failed case IDs, non-authority model status, false physical-SO-101-authority flag, and false policy-training readiness flag. It uploads the suite output directory, source-authority matrix output directory, model-bundle manifest matrix output directory, reviewed-authority gate matrix output directory, reviewed-MuJoCo bundle matrix output directory, MuJoCo scene matrix output directory, chess-env matrix output directory, board-pick probe matrix output directory, training-rollouts matrix output directory, and training-readiness gate matrix output directory as one workflow artifact. By default it leaves `REFERENCE_MEDIA_ROOTS`, `IK_MODEL_PATH`, `IK_MODEL_ASSET_ROOTS`, `SO101_MODEL_BUNDLE_MANIFEST`, `SO101_MODEL_SOURCE_ROOTS`, `SO101_MODEL_SOURCE_EXTRA_ROOTS`, `SO101_AUTHORITATIVE_MODEL_PATHS`, `SO101_AUTHORITATIVE_MODEL_ROOTS`, and the `SO101_SOURCE_AUTHORITY_*` review metadata vars empty so CI keeps the existing repo-root-only and fallback-only behavior. A caller can set `REFERENCE_MEDIA_ROOTS` as a newline-separated path list to append repeatable `--reference-media-root` values into the suite; include `.` in that list when adding sibling roots and keeping the checked-out repo in the inventory. A caller can set `SO101_MODEL_BUNDLE_MANIFEST` to forward `--so101-model-bundle-manifest` into the suite without requiring a model in default CI. A caller can set `IK_MODEL_PATH` to forward `--ik-model-path` into the model contract checker and IK drill without changing the workflow structure. A caller can set `IK_MODEL_ASSET_ROOTS` as a newline-separated path list to append repeatable `--ik-model-asset-root` values for the contract checker asset preflight without changing IK drill behavior. A caller can also set the SO-101 source env vars as newline-separated path lists to append repeatable reviewed-source inventory options: `SO101_MODEL_SOURCE_ROOTS` maps to `--so101-model-source-root`, `SO101_MODEL_SOURCE_EXTRA_ROOTS` maps to `--so101-model-source-extra-root`, `SO101_AUTHORITATIVE_MODEL_PATHS` maps to `--so101-authoritative-model-path`, `SO101_AUTHORITATIVE_MODEL_ROOTS` maps to `--so101-authoritative-model-root`, and `SO101_SOURCE_AUTHORITY_REVIEW_SCOPES` maps to repeatable `--so101-source-authority-review-scope`. The scalar `SO101_SOURCE_AUTHORITY_REVIEWED_BY`, `SO101_SOURCE_AUTHORITY_REVIEWED_AT`, `SO101_SOURCE_AUTHORITY_REVIEW_ID`, `SO101_SOURCE_AUTHORITY_REVIEW_URL`, `SO101_SOURCE_AUTHORITY_SOURCE_REFERENCE`, and `SO101_SOURCE_AUTHORITY_LICENSE_BASIS` vars forward the matching source-authority metadata fields. The inventory does not mark `IK_MODEL_PATH` authoritative. After downloading the artifact, open `artifact_index_report.md` first, then follow its links to images, JSON summaries, and child logs; the sibling `so101_source_authority_matrix/README.md` summarizes the focused source-authority matrix cases, `so101_model_bundle_manifest_matrix/README.md` summarizes the manifest authority and geometry cases, `so101_reviewed_authority_gate_matrix/README.md` summarizes the reviewed-authority gate contract cases, `so101_reviewed_mujoco_bundle_matrix/README.md` summarizes the reviewed-MuJoCo bundle motion-authority cases, `so101_mujoco_scene_matrix/README.md` summarizes the development-scene placement validity cases, `so101_chess_env_matrix/README.md` summarizes the Gymnasium fallback/fail-closed/development-MuJoCo cases, `so101_mujoco_board_pick_probe_matrix/README.md` summarizes the seeded board-pick fixture boundary cases, `so101_training_rollouts_matrix/README.md` summarizes debug-rollout and fail-closed cases, and `so101_training_readiness_gate_matrix/README.md` summarizes the serious-training boundary cases.

The workflow now installs `gymnasium` and `mujoco` and treats the SO-101
reviewed MuJoCo bundle plus scene/env/reset/contact/grasp/rollout summaries as
required artifact categories. Default CI records the reviewed bundle as not
ready when no manifest exists; a ready manifest must pass MuJoCo model load and
joint-motion checks before scripted curriculum evidence is trusted. The workflow
also runs the focused `so101_reviewed_authority_gate_matrix` contract smoke to
exercise source-missing, bundle-missing, source/bundle path-mismatch,
fixture-only, motion-missing, and all-ready injected gate states without treating
the matrix itself as reviewed physical SO-101 evidence. The matrix also verifies
that physical-reviewed MuJoCo motion needs a consistent child status and
`motion_authority_status`; a lone true motion boolean cannot close reviewed
model authority. It also verifies that contradictory child summaries with both
physical-ready and fixture-only evidence fail the aggregate authority gate
closed. It also runs the focused
`so101_reviewed_mujoco_bundle_matrix` smoke to prove missing/not-ready manifests
do not attempt motion, `--require-ready-reviewed-model` fails closed,
placeholder review metadata and generic or missing field-specific review scopes
stay `needs_review` without MuJoCo motion, malformed TCP offsets and incomplete
base-to-board transforms stay not ready, and ready synthetic fixture motion remains
`hardware_free_fixture_motion_checked_not_physical_so101_authority`. It also runs the focused
`so101_mujoco_scene_matrix` smoke to prove generated development scenes load
across center, corner, back-rank, and edge placements with 64 square geoms,
target marker/site presence, SimRobot joint sync, and Gymnasium scripted
completion while remaining non-authoritative. The same matrix requires invalid
scene requests, such as invalid chess squares, identical source/target squares,
or a non-positive step budget, to fail closed with summary/CSV/README artifacts
and no generated model XML or manifest. It also runs the focused
`so101_chess_env_matrix` smoke to prove Gymnasium task wiring can run in
explicit fallback mode, `--require-mujoco` fails closed without a model path or
with an invalid model path, invalid task configuration and incomplete scripted
episodes fail closed, and the generated development MJCF path remains
`development_scaffold_not_reviewed` with `ready_for_policy_training: false`.
It also runs the focused
`so101_mujoco_board_pick_probe_matrix` smoke to prove the current seeded
development fixture performs `e4 -> e5` board-source pick/place while recording
expected place/pick gaps for alternate target/source squares and fail-closed
invalid source/target task requests without generating model XML or manifests.
These gap and invalid-task cases are required evidence that the fixture is not
generalized reviewed model-backed IK, and every case remains non-authoritative
and not policy-ready.
It also runs the focused
`so101_training_rollouts_matrix` smoke to prove valid development prerequisites
allow debug imitation rollouts while missing/failed board-pick prerequisites,
incomplete final board contact or target-tolerance evidence, and too-short
rollout budgets fail closed without becoming policy-training authority. The
same matrix requires malformed rollout tasks, invalid chess squares, identical
source/target task squares, and non-positive step budgets to fail closed without
generating model XML or manifests. It also runs the focused
`so101_training_readiness_gate_matrix` contract smoke to prove development,
draft, fixture-seeded, manually reset-pose-corrected, raw-rollout-ready, and
all-ready injected states do not cross the serious-training boundary without
reviewed model authority. The
workflow asserts the motion-authority fields so hardware-free fixture motion remains labeled as
automation coverage, not reviewed physical SO-101 truth. TCP/gripper offset,
base-to-board alignment, and board-source pickup with reviewed model-backed IK
remain separate required items before serious policy training.

The workflow also checks SO-101 source-intake checklist JSON/CSV artifacts under
`so101_model_source_inventory/`. These artifacts expose
`source_intake_status`, `source_intake_action_ids`, command templates, and false
authority flags for the first reviewed-model-source acquisition gate.

The workflow also treats `reference_media_inventory`, `reference_media_comparison`, `reference_camera_tuning_diagnostics`, `sim_camera_profile_sweep`, `simcamera_tuning_before_after`, `sim_camera_pose_fixture`, `so101_model_bundle_manifest`, `so101_reviewed_model_authority_gate`, `so101_model_bundle_probe`, `so101_reviewed_mujoco_bundle`, `so101_model_source_inventory`, `so101_model_contract`, `ik_reachability_drill`, `gripper_camera_pov_review`, `visual_review`, `real_projection_intake`, `evidence_bundle`, `app_entrypoint_metadata`, `pick_place_scenario_matrix.piece_visibility`, and `artifact_index.json` as part of the artifact contract. The reference media inventory must report a deterministic summary JSON, CSV, and README under `reference_media_inventory/`, expose status, candidate counts, image/video/calibration-data counts, current gripper reference detection, currently wired media count, scan roots, and `reference_gaps`; default CI expects repo-root-only evidence and explicit gaps such as `missing_depth_reference` and `missing_pick_place_video`. The reference media comparison must report deterministic summary JSON, rows CSV, README, and optional contact sheet under `comparison_set/`, expose selected candidate/media counts, visual comparison count, contact sheet status, no-media/no-video/dependency diagnostics, external selected count, and `media_assets_copied_into_repo: false`. The reference camera tuning diagnostics must report deterministic JSON, CSV, README, and optional scorecard under `reference_camera_tuning_diagnostics/`, expose selected/visual/metadata-only comparison counts, suggested tuning dimensions, scorecard status/path, external local-only evidence, `media_assets_copied_into_repo: false`, and carried `missing_depth_reference`, `missing_pick_place_video`, and `no_videos` gaps without claiming physical calibration readiness. The SimCamera Profile Sweep must report deterministic JSON, montage, current/best overlays, absolute-difference heatmaps, side-by-side images, candidate directory, current/best MAD/RMSE, and remaining prompts. The SimCamera Tuning Before/After child must report deterministic JSON, CSV, README, baseline/current child sweep summaries, montages, overlays, absolute-difference heatmaps, side-by-side images, candidate directories, baseline width `72`, canonical current width, marker time `0.0`, current-vs-baseline and best-candidate MAD/RMSE deltas, remaining prompts, `media_assets_copied_into_repo: false`, and carried missing real depth and pick/place-video gaps. The pose fixture must report deterministic nominal and perturbed case IDs, raw frames, annotated frames, per-case metadata JSON, projected board corners, and target/piece centers. The SO-101 model bundle manifest checker must report a deterministic summary JSON, checklist CSV, and README, expose status, manifest request, model path, asset roots, reviewed joint limits, mesh evidence, target frame, TCP offset, base-to-board alignment, child contract/preflight diagnostics when a model path is supplied, readiness, model-authority class, physical-authority readiness, fixture-only readiness, synthetic authority fields, and forwarding reason; default CI must preserve `model_bundle_manifest_not_supplied` as explicit non-failing evidence. The SO-101 reviewed model authority gate must report deterministic JSON, checklist CSV, blocker-packet JSON/CSV, and README, expose `ready`, source-authority readiness, physical bundle-authority readiness, physical-reviewed MuJoCo motion readiness, blocker count/list, blocker-packet status/model-authority/item count/action IDs, and the fixture-not-physical-truth caveat. The SO-101 model bundle probe must report deterministic summary JSON, candidate manifest JSON, review-packet JSON/CSV, checklist CSV, README, child contract summary/checklist, and child manifest-check summary/checklist, expose `model_authority: "draft_candidate_not_reviewed"`, `review_packet_model_authority: "review_packet_not_authority"`, selected model path, model request status, observed source/joint/mesh hints, manifest status, review-packet status/item count, missing inputs, and next required action IDs, and preserve the default no-model template as non-failing scaffolding. The SO-101 reviewed MuJoCo bundle gate must report deterministic summary JSON, checklist CSV, motion-checks CSV, and README, expose manifest status, ready flag, model path, model-authority class, physical-authority readiness, fixture-only readiness, missing inputs, `reviewed_model_motion_checked`, per-joint motion row status, `motion_authority_status`, physical-reviewed motion status, fixture-motion status, and non-physical motion-evidence status; default CI must preserve `reviewed_mujoco_bundle_not_ready` with not-attempted joint rows, while ready manifests must pass MuJoCo model load and SimRobot joint motion. The SO-101 model-source inventory must report a deterministic summary JSON, candidates CSV, and README, expose status, candidate counts, authoritative candidate count, recommended contract-check path when present, and preserve `missing_authoritative_model` as explicit non-failing CI evidence when no reviewed source exists. The SO-101 model contract checker must report a deterministic summary JSON, checklist CSV, and README, expose model request status, direct RobotKinematics status, target frame, and artifact paths, and preserve `missing_model` / `model_not_supplied` as explicit non-failing CI evidence when no model is supplied. The IK reachability drill must report a deterministic summary JSON, rows CSV, and heatmap PNG, expose row counts and counts-by-feasibility, and preserve model diagnostic status so `model_unavailable_fallback_complete` is explicit but non-failing when no repo-local SO-101 model is available. The gripper-camera POV review must report a small open/approach/grasp/release state sequence with raw frames, annotated frames, per-state metadata JSON, target square center and projected square polygon, gripper opening, SimCamera metadata contract checks, and piece visibility/occlusion/clearance rows. The visual review must report stable PNG contact sheets for gripper POV, pose fixture, and pick/place sequence frames, plus distance-annotated pick/place sequence frames, pick/place depth-distance scorecard PNG/JSON, pick/place depth/distance JSON/CSV metrics, pick/place perceived-depth comparison JSON/CSV metrics, pick/place PnP residual diagnostic JSON/CSV metrics, metadata-native SimCamera projection/depth PNG/JSON/CSV metrics, and a copied app-entrypoint frame for convenient bundle browsing. The evidence bundle must write `evidence_bundle/sim_evidence_bundle.md` and `.json` after real projection intake and the real-depth-aware visual-review refresh are complete; missing optional capture-plan artifacts and codec-dependent MP4s remain non-fatal. The depth/distance metrics must label simulator ground truth separately from perceived depth, include camera-to-board/piece distances, target/piece world coordinates, projected pixel coordinates, projection residuals, and a clearly sourced gripper-to-piece proxy when true end-effector depth is unavailable. The depth-distance scorecard must summarize SimCamera ground truth, the metadata-derived rendered-corner PnP baseline, mean/max simulator baseline residuals, corner residuals in pixels, and a `real_depth_reference` section whose status is either `real_depth_comparable` with real-vs-sim residual metrics or `missing_real_depth_reference` with required sidecar inputs. The perceived-depth comparison must add a clearly labeled metadata-derived rendered-board-corner PnP baseline with estimated camera-to-piece/board distances, simulator-ground-truth distances, signed/absolute residuals, estimator source/status, and an explicit note that it is not real-camera depth perception. The PnP residual diagnostic must compare simulator ground-truth extrinsics, the rendered-board-corner PnP estimate, and metadata-projected 3D board corners for the same frames; it must report corner ordering assumptions, board size, reprojection residuals, camera-center/board distances, source comparability, and reason labels when sources are not geometrically comparable. The metadata-native projection/depth view must project board corners/center plus per-stage piece and target square centers directly through `camera_metadata.camera_matrix_px` and `camera_metadata.extrinsics.board_to_camera`, report `metadata_projected_pixel_xy`, `camera_frame_xyz_mm`, `camera_z_depth_mm`, `camera_range_mm`, `board_plane_distance_mm`, `source_model: simcamera_metadata`, and link back to the existing depth-distance and PnP diagnostic artifact paths. The real projection intake must link selected real reference media to that metadata-native depth view, report `real_reference_media_path`, `real_intrinsics_status`, `real_board_pose_status`, `real_depth_status`, `sim_metadata_native_depth_view_path`, `sim_expected_projected_points`, `comparable`, `depth_comparable`, `missing_inputs`, next capture requirements, and residual artifacts when real_capture sidecars are present. The app-entrypoint smoke must report a synthetic frame, a metadata sidecar when requested, skipped hardware/gui/OpenAI markers, passing app-facing metadata contract checks, and the same compact `app_camera_status` readout shown by `chess_robot_ui_llm_v2.py --sim`. All four pick/place scenarios must report available visibility evidence, each target release frame path must exist, and each `target_release_open` row must include visible fraction, occlusion fraction, and gripper-clearance fields. The generated artifact index must exist, report `status: "ok"`, have a nonzero artifact count, have no missing artifacts, and include populated categories for reference media inventory, reference media comparison, reference camera tuning diagnostics, SimCamera profile sweep, SimCamera tuning before/after, the evidence bundle, visual-review contact sheets, sequence frames, depth-distance scorecard, depth/distance metrics, perceived-depth comparison metrics, PnP residual diagnostic metrics, metadata-native projection/depth metrics, real-reference comparisons when inventory candidates are selected, real projection intake, ranked candidates, perception fixture evidence, SimCamera pose fixture evidence, SO-101 model-source inventory evidence, SO-101 reviewed model authority gate evidence, SO-101 model bundle probe evidence, SO-101 model bundle manifest evidence, SO-101 reviewed MuJoCo bundle evidence, SO-101 model contract evidence, IK reachability evidence, gripper-camera POV evidence, app-entrypoint evidence, pick/place scenario release frames, the negative check, and child logs. These are structural availability checks rather than exact metric-value thresholds.

The SO-101 reviewed model authority gate contract also requires
`source_bundle_consistency_ready`, `source_bundle_consistency_status`, and the
nested `source_bundle_consistency` object in both the top-level summary and the
artifact-index metrics. The gate only becomes ready when the status is
`source_bundle_model_path_and_digest_consistent`, the bundle model path matches
the selected authoritative source candidate path, and the selected source
SHA-256 matches the bundle manifest declared model digest. The selected source
candidate must also be covered by the authoritative path/root declarations from
the source inventory. If source authority is otherwise reported ready but no
authoritative path/root declaration is present, the status is
`source_authoritative_model_selection_unconfigured`; if the selected candidate
falls outside those declarations, the status is
`source_authoritative_model_selection_mismatch`. The observed digest of the
resolved bundle model file is reported for diagnostics, but it does not
substitute for the reviewed manifest declaration. When the bundle child reports
physical authority, the aggregate gate still fails closed if the observed digest
is missing (`bundle_model_observed_digest_missing`) or conflicts with the reviewed
declaration (`bundle_model_observed_digest_mismatch`). The nested object records
those checks as
`selected_authoritative_candidate_covered_by_source_configuration`,
`selected_authoritative_candidate_path_matches_bundle`, and
`selected_authoritative_candidate_sha256_matches_bundle`; `matched_by` is
populated only as `selected_authoritative_candidate_path_and_sha256` when the
selected source coverage, path identity, and digest identity checks close. If
source authority is otherwise reported ready but the
selected authoritative source model path is absent, the consistency status is
`source_authoritative_model_path_missing` and the blocker points back to
selecting the reviewed source model path. An authoritative root alone is not
enough to authorize a different model file in the same tree, and a path match
with a digest mismatch is also blocked. The gate also fails closed when a source
inventory reports `source_authority_ready` while still carrying source blockers
or pending source-authority actions; those contradictory states must be resolved
before source/bundle identity consistency is checked. The same fail-closed rule
applies when a bundle manifest summary reports physical bundle authority ready
while still carrying physical-authority blockers or pending bundle-authority
actions. The reviewed-authority matrix includes
ready-source-with-stale-blocker, ready-source-with-pending-action,
physical-bundle-ready-with-stale-blocker, and
physical-bundle-ready-with-pending-action cases,
missing selected source path, unconfigured selected source authority,
selected-source/outside-authority mismatch, same-root unselected-model,
source-digest-missing, malformed selected-source digest,
bundle-declared-digest-missing, bundle-observed-digest-missing,
bundle-observed-digest-mismatch, and
source/bundle digest-mismatch
negative cases so even physical-motion-ready injected state remains blocked on
those mismatches. If source or bundle authority is not ready yet, the consistency
check remains `not_checked_prerequisites_not_ready` rather than overclaiming
reviewed physical SO-101 authority. The blocker packet
separates immediate `action_required` items from `blocked_by_prior_requirements`
items so reviewed MuJoCo motion proof stays downstream of reviewed physical
bundle authority and source/bundle model identity consistency.
The gate reports `physical_reviewed_model_motion_reported` separately from
`physical_reviewed_model_motion_status_ready`; it only reports
`physical_reviewed_model_motion_checked: true` when the reviewed-MuJoCo child
status is `reviewed_mujoco_bundle_motion_checked` and
`motion_authority_status` is `physical_reviewed_model_motion_checked`, when the
child summary has no reviewed-motion missing inputs or pending actions, and when
the motion evidence matches the reviewed bundle model identity. A child summary
that reports physical reviewed motion while still carrying missing inputs or
pending motion actions is treated as contradictory and remains blocked. The
physical-reviewed MuJoCo motion summary must carry the same reviewed bundle
model path and declared SHA-256 as the bundle manifest, and its observed
model-file SHA-256 must be present and match that reviewed motion declaration.
The nested
`reviewed_mujoco_motion_bundle_consistency` object reports
`reviewed_mujoco_motion_model_path_missing`,
`reviewed_mujoco_motion_model_path_mismatch`,
`reviewed_mujoco_motion_model_digest_missing`,
`reviewed_mujoco_motion_model_observed_digest_missing`,
`reviewed_mujoco_motion_model_observed_digest_mismatch`,
`reviewed_mujoco_motion_model_digest_mismatch`, or the ready status
`reviewed_mujoco_motion_matches_bundle_model_identity`; the aggregate gate stays
blocked until the reviewed-motion model path, declared digest, and observed
model-file digest match the reviewed bundle identity. The generated artifact
index and HTML/Markdown report surface
`physical_reviewed_model_motion_child_ready`,
`reviewed_mujoco_motion_bundle_consistency_status`, and the reviewed-authority
checklist status/next-action/prior-blocker maps so reviewers can distinguish
child MuJoCo motion from aggregate reviewed SO-101 authority and verify priority
semantics without opening the gate JSON by hand.

The standalone model-bundle manifest matrix writes
`so101_model_bundle_manifest_matrix_summary.json`, `.csv`, and `README.md`.
It reports `model_authority: "model_bundle_manifest_matrix_not_authority"`,
`observed_evidence_is_physical_so101_authority: false`, and
`ready_for_policy_training: false`. It covers missing manifests, a ready
synthetic fixture manifest that must stay
`hardware_free_regression_fixture_not_physical_so101_authority`, placeholder
alignment, placeholder/thin/invalid review evidence, generic review scopes,
ready-shaped review metadata with pending follow-up, weak field-specific
authority, placeholder provenance, reviewed-status fixture provenance, wrong
target frame, invalid TCP/alignment payloads, and mismatched model SHA. Ready
fixture cases exercise the manifest state machine only; they must keep
`physical_so101_model_authority_ready: false`.

The standalone reviewed-authority gate matrix writes
`so101_reviewed_authority_gate_matrix_summary.json`, `.csv`, and `README.md`.
It reports `model_authority: "contract_matrix_not_authority"`,
`observed_evidence_is_authority: false`, and
`physical_so101_model_authority_ready: false` even though it includes an
`all_ready_contract_state` case to exercise the ready branch. That case is a
state-machine guard only; it is not evidence that a reviewed physical SO-101
bundle exists. It also includes an inconsistent-motion negative case: even when
the injected physical motion boolean is true, the top-level authority gate stays
blocked unless the reviewed-MuJoCo child status and motion-authority status also
match physical reviewed motion. The matrix also includes physical-motion child
ready states with missing or mismatched reviewed model path and missing or
mismatched reviewed model digest; all stay blocked and point operators back to
regenerating or aligning the motion evidence with the reviewed bundle identity.

The standalone reviewed-MuJoCo bundle matrix writes
`so101_reviewed_mujoco_bundle_matrix_summary.json`, `.csv`, and `README.md`.
It reports `model_authority: "reviewed_mujoco_bundle_matrix_not_authority"` and
`observed_evidence_is_physical_so101_authority: false`. It covers the default
missing-manifest diagnostic, the fail-closed `--require-ready-reviewed-model`
path, a not-ready placeholder manifest, placeholder review metadata on otherwise
complete fields, generic-review-scope and per-field weak-authority fixtures,
manifest/model target-frame mismatches that must block motion authority,
non-standard JSON constants that must parse-fail, malformed, non-finite, and
out-of-range TCP/alignment manifest payloads, unavailable model paths,
non-finite or reversed joint limits, malformed, unavailable, or non-directory asset-root declarations, unresolved model mesh references, a
ready manifest whose declared body-joint bounds intentionally mismatch the
loaded MuJoCo `jnt_range`, and a ready synthetic fixture manifest whose MuJoCo/SimRobot motion
check must remain
`hardware_free_fixture_motion_checked_not_physical_so101_authority`.

The standalone MuJoCo scene matrix writes
`so101_mujoco_scene_matrix_summary.json`, `.csv`, and `README.md`. It reports
`model_authority: "so101_mujoco_scene_matrix_not_authority"`,
`observed_evidence_is_physical_so101_authority: false`,
`ready_for_model_backed_ik: false`, and `ready_for_policy_training: false`.
It covers multiple valid source/target board placements and verifies each child
scene remains `development_scaffold_not_reviewed` with 64 square geoms, target
frame site presence, target marker presence, model load, SimRobot sync, and
scripted environment completion. It also covers invalid-square,
same-source/target, and non-positive max-step requests that must fail closed
without writing a model XML or manifest. Reviewed MuJoCo handoff cases also
cover not-ready, fixture-only, forged-ready, and incomplete-ready payloads that
must fail closed when a reviewed handoff is required; the valid ready-handoff
case records `reviewed_mujoco_handoff_contract_ok: true` and
`reviewed_mujoco_handoff_physical_motion_checked: true` but still keeps
`scene_uses_reviewed_mujoco_handoff: false` until the scene actually consumes a
reviewed model bundle.

The standalone chess-env matrix writes `so101_chess_env_matrix_summary.json`,
`.csv`, and `README.md`. It reports
`model_authority: "so101_chess_env_matrix_not_authority"`,
`observed_evidence_is_physical_so101_authority: false`, and
`ready_for_policy_training: false`. It covers joint-state fallback allowed,
Gymnasium-required fallback allowed, fail-closed `--require-mujoco` with no model
path or an invalid model path, and generated development-MuJoCo env wiring that remains
`development_scaffold_not_reviewed`. Invalid Gymnasium task configuration and
too-short scripted episode budgets must fail closed without becoming fallback
success evidence.

The standalone board-pick probe matrix writes
`so101_mujoco_board_pick_probe_matrix_summary.json`, `.csv`, and `README.md`.
It reports
`model_authority: "so101_mujoco_board_pick_probe_matrix_not_authority"`,
`observed_evidence_is_physical_so101_authority: false`,
`ready_for_model_backed_ik: false`, and `ready_for_policy_training: false`.
It covers the current seeded `e4 -> e5` board-source pick/place fixture plus
alternate target/source cases that must record expected place/pick gaps, plus
invalid source/target task cases that must write fail-closed summary/CSV/README
artifacts without generating model XML or manifests. Those gap and invalid
cases make the fixture boundary explicit before reviewed model-backed IK is
available. The matrix also exports and asserts the detailed contact path:
source-start, two-finger contact, board-contact clearance during lift, transfer,
placement without manual piece-pose edits, release-contact clearance, final
board contact, and final target XY tolerance.

The standalone training-rollouts matrix writes
`so101_training_rollouts_matrix_summary.json`, `.csv`, and `README.md`. It
reports `model_authority: "so101_training_rollouts_matrix_not_authority"`,
`observed_evidence_is_physical_so101_authority: false`,
`observed_evidence_is_policy_training_authority: false`,
`ready_for_model_backed_ik: false`, and `ready_for_policy_training: false`.
It covers the default development rollout curriculum, missing and failed
board-pick prerequisites, an otherwise broad-true board-pick prerequisite that
is missing final board contact and target-tolerance evidence, a short-budget
incomplete rollout, and invalid rollout task requests. Invalid rollout tasks
must write summary/JSONL/CSV/README artifacts without generating model XML or
manifests. Only the valid development-prerequisite case may pass as debug
curriculum evidence; the other cases must fail closed without becoming
policy-training authority.

The standalone training-readiness gate matrix writes
`so101_training_readiness_gate_matrix_summary.json`, `.csv`, and `README.md`.
It reports `model_authority: "training_readiness_contract_matrix_not_authority"`,
`observed_evidence_is_policy_training_authority: false`, and
`ready_for_policy_training: false` even though it includes an
`all_ready_reviewed_contract_state` case to exercise the ready branch. That case
is a state-machine guard only; it is not evidence that serious policy training is
ready. The matrix also rejects a board-pick state that carries reviewed model
authority and raw model-backed IK readiness but used manual piece-pose correction
after reset, because serious training needs repeatable board-source pick/place
from the reset scene state. It also rejects an injected reviewed-authority-ready
state whose reviewed MuJoCo motion flag is false; the next priority gate must
remain `mujoco_scene_validity` so serious training cannot advance on
source/bundle authority without reviewed motion evidence, or on fixture-only,
malformed raw-ready, incomplete-item, or physical-truth-claiming downstream
handoff states. The accepted handoff flag is derived from a summary-level
reviewed MuJoCo downstream handoff contract, not from a raw
`downstream_handoff_ready` boolean alone.

The SO-101 model-source inventory artifact contract also includes
`so101_model_source_intake_checklist.json` and `.csv`. The checklist must mirror
`next_required_action_ids`, preserve scanned roots and command templates, and
include source-review command flags for license basis, source reference, review
scopes, reviewer identity, and at least one review trace field. It must report
`source_intake_model_authority: "source_intake_not_authority"` with false
observed-evidence and physical-authority flags.

For the SO-101 model-source inventory contract, CI also requires
`so101_model_source_inventory_review_packet.json` and `.csv`, with
`review_packet_model_authority: "review_packet_not_authority"`,
`review_packet_observed_evidence_is_authority: false`, and
`review_packet_physical_so101_model_authority_ready: false`. The packet is a
review intake artifact, not reviewed physical SO-101 truth.

For the SO-101 model bundle manifest contract, CI also requires a deterministic
manifest review packet: `so101_model_bundle_manifest_review_packet.json` and
`.csv`, with `review_packet_model_authority: "review_packet_not_authority"`,
`review_packet_observed_evidence_is_authority: false`, item/action metadata,
and the fixture-not-physical-truth caveat.

CI also requires `so101_model_bundle_manifest_intake_checklist.json` and
`.csv`, with `bundle_intake_model_authority` set to
`"bundle_manifest_intake_not_authority"`, false observed-evidence and
physical-truth flags, action IDs matching `next_required_action_ids`, and
command templates for rerunning the manifest checker after the reviewed bundle
manifest is supplied or updated.

For the SO-101 model bundle manifest contract, CI also requires
`physical_authority_gate_status` and `physical_authority_blockers`. The blocker
list must be empty only when `physical_so101_model_authority_ready` is true;
default no-manifest CI must include `supply_reviewed_so101_model_bundle_manifest`,
and fixture-only manifests must retain
`synthetic_fixture_authority_not_physical_so101:<field>` blockers.

The artifact contract also includes the dedicated `so101_model_asset_preflight`
index/report category. It is sourced from the contract checker's nested child
preflight and must expose summary/CSV/README artifacts plus status, mesh
reference count, present count, missing count, and unresolved count before the
IK reachability section.

The model bundle manifest summary and artifact-index metrics must expose
`next_required_for_goal`, `next_required_action_ids`, and
`next_required_action_count`; in default CI the first action remains
`supply_reviewed_so101_model_bundle_manifest`, keeping reviewed SO-101 model
authority ahead of downstream policy work. The manifest review packet must keep
`review_packet_action_ids` in that same priority order rather than sorting them
alphabetically, so operator review follows the gate sequence.

The artifact contract also includes dedicated `so101_mujoco_scene`,
`so101_chess_env`, `so101_env_resets`, `so101_mujoco_contact_probe`,
`so101_mujoco_grasp_probe`, `so101_mujoco_board_pick_probe`, and
`so101_training_rollouts` categories. They must
expose summary JSON artifacts plus their generated model/manifest, CSV, JSONL,
or README evidence where applicable. Default CI expects `status: "ok"` for the
scene/env/reset/contact/rollout gates and
`status: "contact_grasp_lift_place_physics_verified"` for the grasp probe when
the development fixture lifts, transfers, lands near target, contacts the board,
and clears gripper contact after retreat. It expects
`status: "development_board_source_pick_place_verified"` for the board-source
probe when the seeded development pose picks from the board, lifts, transfers,
places near target, and clears gripper contact after retreat. Visible
`next_required_for_goal` entries remain part of the contract when children emit
them.

This CI signal is still a simulator/perception regression gate only. It does not connect to SO-101 hardware, open GUI calibration flows, or replace later physical robot validation.

## What This Proves

The suite orchestrates these existing smoke scripts as subprocesses and records each child command, return code, stdout path, stderr path, and expected JSON path under `child_commands`:

- `smoke_sim_reference_media_inventory.py` finds real reference media that can calibrate the simulator.
- `smoke_sim_reference_media_comparison_set.py` runs real-reference comparison artifacts for selected images.
- `smoke_sim_real_projection_intake.py` links selected real media to the metadata-native SimCamera projection/depth view and reports missing real calibration inputs.
- `smoke_sim_real_calibration_sidecars.py` validates hardware-free JSON sidecar schemas for future real intrinsics, extrinsics or board pose, ordered board corners, and metric depth references.
- `smoke_simcamera_tuning_before_after.py` compares the documented 72px gripper-reference baseline against the current canonical SimCamera profile and preserves child sweep artifacts without copying media.
- `smoke_sim_calibration_session_report.py` ranks baseline and perturbed local SimCamera candidates.
- `smoke_sim_perception_regression_fixture.py` packages the selected ranked candidate into perception fixture evidence.
- `smoke_sim_camera_pose_fixture.py` renders deterministic nominal, perturbed, overview, and gripper-state SimCamera pose review frames plus per-case metadata.
- `smoke_sim_so101_model_source_inventory.py` records deterministic repo-local SO-101 model-source inventory evidence, candidate/provenance/authority counts, source-authority review scope readiness, source-authority gate status/blockers, review-packet JSON/CSV intake, source-intake checklist JSON/CSV command templates, and explicit missing-authoritative-model diagnostics before contract or IK checks.
- `smoke_sim_so101_model_bundle_probe.py` records deterministic SO-101 bundle draft evidence, including the default no-model candidate manifest template, selected candidate path when available, review-packet JSON/CSV intake, child contract/manifest diagnostics, observed source/joint/mesh hints, and explicit non-authoritative draft status.
- `smoke_sim_so101_model_bundle_manifest.py` records deterministic SO-101 model bundle manifest evidence, including default no-manifest diagnostics, reviewed manifest fields, child contract/preflight diagnostics, readiness, and downstream forwarding decisions. The suite aggregates this with source-inventory and reviewed-MuJoCo evidence under `so101_reviewed_model_authority_gate`, including a blocker-packet JSON/CSV review artifact.
- `smoke_sim_so101_model_contract.py` records deterministic model availability, RobotKinematics usability, joint/frame/TCP contract, nested asset-preflight mesh evidence, and missing alignment inputs before model-backed IK residuals are trusted.
- `smoke_sim_ik_reachability_drill.py` records deterministic Cartesian, delta, and radial command feasibility evidence plus explicit missing-model fallback diagnostics.
- `smoke_sim_so101_mujoco_scene.py` validates the development-only SO-101 MuJoCo chess scene, joint sync, board/piece collision geoms, and scripted env loop.
- `smoke_sim_so101_chess_env.py` validates the Gymnasium-facing SO-101 chess environment against the generated MuJoCo model.
- `smoke_sim_so101_env_resets.py` validates task reset options, sampled resets, and MuJoCo piece-freejoint reset state.
- `smoke_sim_so101_mujoco_contact_probe.py` validates development-scaffold chess-piece freejoint resets and board contacts.
- `smoke_sim_so101_mujoco_grasp_probe.py` records development-scaffold gripper/piece fixture contact, lift, transfer, target placement, board contact, release, and retreat without manual freejoint edits after fixture setup.
- `smoke_sim_so101_mujoco_board_pick_probe.py` records seeded development-scaffold board-source pick/place from `e4` to `e5`, including source contact, lift-off, target placement, release, and retreat without manual freejoint edits after the initial source reset.
- `smoke_sim_so101_training_rollouts.py` collects deterministic scripted JSONL/CSV rollout evidence for focused pick/place curriculum debugging only after the development board-pick summary is supplied and verified.
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
- `reference_media_inventory.status: "media_inventory_complete"` or `"media_inventory_empty"` with candidate, image, video, calibration-data, currently wired media counts, current gripper reference detection, `reference_gaps`, scan roots, and JSON/CSV/README artifact paths populated
- `child_commands.*.ok: true`
- `comparison_set.status: "ok"` when selected reference media exists, or `"no_reference_media_selected"` as a non-failing diagnostic for empty explicit roots
- `simcamera_tuning_before_after.status: "ok"` with baseline width `72`, current canonical width, marker time `0.0`, candidate counts, current-vs-baseline MAD/RMSE deltas, best-candidate deltas, remaining prompt count/details, `media_assets_copied_into_repo: false`, carried missing real depth and pick/place-video gaps, and child sweep artifact paths populated
- `calibration_session.selected_candidate` populated with the rank-1 candidate
- `perception_fixture.status: "ok"` and fixture artifact paths populated
- `sim_camera_pose_fixture.status: "ok"` with deterministic nominal and perturbed case IDs, frame paths, annotated-frame paths, and metadata paths populated
- `so101_model_bundle_manifest.status: "model_bundle_manifest_not_supplied"`, `"model_bundle_manifest_unavailable"`, `"model_bundle_manifest_parse_error"`, `"model_bundle_manifest_schema_error"`, `"model_bundle_manifest_needs_follow_up"`, or `"model_bundle_manifest_ready_for_model_backed_ik"` with readiness, physical-authority gate status/blockers, model path, asset roots, joint limits, mesh evidence, target frame, TCP offset, base-to-board alignment, ordered `next_required_for_goal` actions, matching ordered `next_required_action_ids` and `review_packet_action_ids`, forwarding reason, and summary/CSV/review-packet/README artifact paths populated. Accepted review metadata must provide reviewer identity plus a stable artifact handle (`review_id` or HTTP(S) `review_url`); a lone non-placeholder reviewer string, malformed review URL, or date-only trace is insufficient for reviewed physical authority or fixture forwarding.
  The bundle-intake status/action IDs must mirror the same next-action order,
  keep `bundle_manifest_intake_not_authority`, and keep observed-evidence and
  physical-truth flags false while populating summary/CSV/review-packet,
  bundle-intake, and README artifact paths.
  Bundle authority review metadata must also declare explicit `review_scope` or `review_scopes` values; top-level authority scope readiness is mirrored into artifact-index metrics as `authority_required_review_scope_ids`, `authority_supplied_review_scope_ids`, `authority_missing_review_scope_ids`, and `authority_review_scope_ready`.
- `so101_reviewed_mujoco_bundle.status: "reviewed_mujoco_bundle_not_ready"` in default CI or `"reviewed_mujoco_bundle_motion_checked"` when a ready manifest is supplied, with `reviewed_model_motion_checked`, per-joint motion-check CSV rows, `motion_authority_status`, physical-reviewed motion, fixture-motion, non-physical motion-evidence fields, downstream handoff `missing_inputs`, downstream handoff pending actions, and summary/checklist/motion-checks/downstream-handoff/README artifact paths populated. Any raw-ready or fixture-ready downstream handoff with non-empty missing inputs or pending actions must fail closed before scene, Gymnasium, pick/place, or training readiness gates treat it as usable.
- `so101_model_source_inventory.status: "missing_authoritative_model"`, `"ambiguous_authoritative_model"`, or `"authoritative_model_found"` with candidate counts, authoritative candidate count, authoritative source-selection status, selected authoritative path and SHA-256 digest when exactly one candidate is selected, source-authority review scope readiness/missing scope IDs, source-authority review evidence required/satisfied/missing groups, source-authority gate status/blockers, review-packet status/model-authority/item count/action IDs, false observed-evidence-as-authority and physical-authority-ready flags, recommended contract-check path when present, and summary/CSV/review-packet/README artifact paths populated. Accepted source-authority review evidence must provide reviewer identity plus a stable artifact handle (`review_id` or HTTP(S) `review_url`); a lone non-placeholder reviewer string, malformed review URL, or date-only trace is insufficient for source authority.
- `so101_model_bundle_probe.status: "candidate_model_missing"`, `"candidate_model_unavailable"`, `"candidate_manifest_needs_review"`, or `"candidate_manifest_ready_for_model_backed_ik"` with `model_authority: "draft_candidate_not_reviewed"`, selected model path, model request status, observed source/joint/mesh hints, manifest status, review-packet status/item count, `missing_inputs`, `next_required_action_ids`, and summary/candidate-manifest/review-packet/checklist/README plus child contract/manifest-check artifacts populated; default CI must keep `ready_for_model_backed_ik: false`
- `so101_reviewed_model_authority_gate.status: "reviewed_model_authority_blocked"` until source authority, physical bundle authority, source-to-bundle model path/digest consistency, and physical-reviewed MuJoCo motion are all true; the gate must expose `ready`, `blockers`, `blocker_count`, ordered `next_required_for_goal`/`next_required_action_ids`, source/bundle/consistency/motion readiness booleans, blocker-packet status/model-authority/item count/action-required IDs/blocked-by-prior IDs, checklist status/next-action/prior-blocker mappings that agree with the blocker packet, `development_fixture_evidence_not_physical_so101_truth`, and summary/checklist/blocker-packet/README artifact paths
- `so101_model_source_inventory.source_configuration.scan_mode: "default_repo_roots"` in the default run or `"explicit_roots"` when `--so101-model-source-root` is supplied, with configured roots/authority lists preserved
- `so101_model_contract.status: "missing_model"`, `"model_unavailable"`, `"model_contract_checked"`, `"model_contract_needs_follow_up"`, or `"model_suffix_supported_not_directly_usable"` with `model_request_status`, `robot_kinematics_status`, `target_frame`, and summary/CSV/README artifact paths populated
- `so101_model_contract.model_asset_preflight.status: "missing_model"`, `"model_unavailable"`, `"asset_preflight_checked"`, `"asset_preflight_limited_diagnostics"`, or `"asset_preflight_needs_follow_up"` with mesh, present, missing, unresolved counts and nested summary/CSV/README artifact paths populated
- `ik_reachability_drill.status: "ok_model_backed"` or `"model_unavailable_fallback_complete"` with `row_count > 0`, populated `counts_by_feasibility`, and summary/CSV/heatmap artifact paths populated
- `ik_reachability_drill.configured_model_path` populated when `--ik-model-path` is supplied, otherwise `null`
- `ik_reachability_drill.configured_model_request` mirrored from the child diagnostic when `--ik-model-path` is supplied
- `so101_mujoco_scene.status: "ok"` with `model_authority: "development_scaffold_not_reviewed"`, `observed_evidence_is_physical_so101_authority: false`, `ready_for_model_backed_ik: false`, `ready_for_policy_training: false`, `mujoco_scene_validity_status: "development_scene_validated_not_physical_authority"`, source/target squares and max-step budget recorded, `square_geom_count: 64`, target-frame site and target marker present, MuJoCo load/sync checks passing, reviewed MuJoCo handoff intake fields populated from the reviewed-bundle downstream handoff, `reviewed_mujoco_handoff_contract_ok` recorded, `scene_uses_reviewed_mujoco_handoff: false`, and summary/model/manifest/CSV/README artifact paths populated
- `so101_mujoco_scene_matrix` includes invalid-square, same-source/target, non-positive max-step, required not-ready handoff, required fixture-only handoff, forged-ready handoff, incomplete-ready handoff, ready-handoff-with-missing-input, and ready-handoff-with-pending-action cases that must fail closed, keep authority/readiness flags false, write summary/CSV/README artifacts, and leave model XML and manifest paths absent for fail-closed cases
- `so101_chess_env.status: "ok"` with `model_authority: "development_scaffold_not_reviewed"` when the generated MuJoCo model is loaded, `ready_for_model_backed_ik: false`, `ready_for_policy_training: false`, strict Gymnasium/MuJoCo dependencies available, `mujoco_backend_required: true`, `mujoco_backend_loaded: true`, `joint_state_fallback_active: false`, `gymnasium_task_wiring_status: "development_mujoco_env_scripted"`, `training_authority_status: "development_mujoco_env_verified_not_policy_ready"`, serious-training blockers including `reviewed_so101_model_bundle`, symbolic contact model recorded, scripted pick/place complete, and summary/CSV/README artifact paths populated; invalid task configuration or incomplete scripted pick/place must return nonzero with false policy/model readiness
- `so101_env_resets.status: "ok"` with `all_resets_ok: true`, `all_mujoco_fallback_free: true`, reset count populated, and summary/CSV/model/manifest/README artifact paths populated
- `so101_mujoco_contact_probe.status: "ok"` with `all_piece_resets_ok: true`, `all_board_contacts_observed: true`, probe count populated, and summary/CSV/model/manifest/README artifact paths populated
- `so101_mujoco_grasp_probe.status: "contact_grasp_lift_place_physics_verified"` with `gripper_contact_observed: true`, `two_finger_contact_observed: true`, `lift_verified: true`, `transfer_verified: true`, `place_without_manual_piece_pose_verified: true`, `release_contact_cleared: true`, `final_board_contact_observed: true`, `final_target_xy_error_m <= target_xy_tolerance_m`, `manual_piece_pose_used_after_fixture: false`, probe count populated, open `next_required_for_goal` items, and summary/CSV/model/manifest/README artifact paths populated
- `so101_mujoco_board_pick_probe.status: "development_board_source_pick_place_verified"` with `model_authority: "development_scaffold_not_reviewed"`, `observed_evidence_is_physical_so101_authority: false`, `ready_for_model_backed_ik: false`, `ready_for_policy_training: false`, `source_pick_started_at_source: true`, `close_two_finger_contact_observed: true`, `lift_verified: true`, `board_contact_cleared_during_lift: true`, `transfer_verified: true`, `place_without_manual_piece_pose_verified: true`, `board_source_pick_place_verified: true`, `release_contact_cleared_after_retreat: true`, `final_board_contact_observed: true`, `final_target_xy_error_m <= target_xy_tolerance_m`, `manual_piece_pose_used_after_reset: false`, `robot_pose_seeded_for_source_fixture: true`, open structured `next_required_for_goal` items, `next_required_action_ids` including `supply_reviewed_so101_model_bundle_manifest`, `calibrate_reviewed_tcp_and_base_to_board_alignment`, and `repeat_board_pick_with_reviewed_model_backed_ik`, and summary/CSV/model/manifest/README artifact paths populated
- `so101_training_readiness_gate.status: "serious_training_blocked"` until
  reviewed model authority, reviewed physical MuJoCo motion, reviewed MuJoCo
  downstream handoff, reviewed model-backed board-source pick/place, and
  policy-ready rollout evidence are all true. The gate must expose `ready`,
  blocker count/list, `reviewed_model_authority_ready`,
  `reviewed_model_physical_motion_checked`,
  `reviewed_mujoco_downstream_handoff_status`,
  `reviewed_mujoco_downstream_handoff_contract_status`,
  `reviewed_mujoco_downstream_handoff_contract_ok`, raw
  `reviewed_mujoco_downstream_handoff_raw_ready`, accepted
  `reviewed_mujoco_downstream_handoff_ready`,
  `reviewed_mujoco_downstream_handoff_model_authority`,
  `reviewed_mujoco_downstream_handoff_observed_evidence_is_authority`,
  `reviewed_mujoco_downstream_handoff_physical_truth_claimed`,
  `reviewed_mujoco_downstream_handoff_missing_item_ids`,
  `reviewed_mujoco_downstream_handoff_missing_inputs`,
  `reviewed_mujoco_downstream_handoff_pending_action_ids`,
  `reviewed_mujoco_downstream_handoff_ready_has_open_work`,
  `reviewed_mujoco_downstream_handoff_contract_blockers`,
  `reviewed_mujoco_downstream_fixture_handoff_ready_not_physical_so101_authority`,
  `reviewed_model_backed_board_source_pick_place`,
  `board_pick_reviewed_model_authority_ready`,
  `board_pick_detailed_evidence_ready`, raw
  `rollout_ready_for_policy_training`, computed
  `rollout_policy_training_authority_ready`, `rollout_status`,
  `rollout_training_authority_status`, `rollout_use`,
  `rollout_observed_evidence_is_policy_training_authority`,
  `rollout_serious_policy_training_blockers`,
  `development_fixture_evidence_not_policy_training_truth`, and
  summary/checklist/README artifact paths. `board_pick_detailed_evidence_ready`
  must require source-start, two-finger contact, lift, board-contact clearance,
  transfer, placement without manual pose, release contact cleared, final board
  contact, and final target XY error within tolerance instead of trusting a
  single broad board-pick boolean. `rollout_policy_training_authority_ready`
  must require rollout `status: "ok"`, `training_authority_status:
  "reviewed_policy_training_rollouts_ready"`, `rollout_use: "policy_training"`,
  true policy-authority evidence, and no serious-policy blockers. The focused
  readiness matrix has negative cases for missing reviewed MuJoCo downstream
  handoff, fixture-only handoff, raw-ready handoff without physical reviewed
  model motion, incomplete handoff items, physical-truth-claiming handoff,
  missing release clearance, missing final board contact, target XY error
  outside tolerance, failed rollout status, wrong rollout authority status,
  debug rollout use, missing policy-authority evidence, and nonempty
  serious-policy blockers.
- `so101_training_rollouts.status: "ok"` with `model_authority: "development_scaffold_not_reviewed"`, `observed_evidence_is_physical_so101_authority: false`, `observed_evidence_is_policy_training_authority: false`, `ready_for_model_backed_ik: false`, scripted episodes/transitions populated, `all_mujoco_fallback_free: true`, `all_mujoco_piece_release_synced: true`, `development_prerequisites_satisfied: true`, `training_authority_status: "development_rollouts_prerequisites_verified_not_policy_ready"`, `ready_for_policy_training: false`, `board_pick_prerequisite.status: "development_board_pick_prerequisite_verified"`, serious-policy blockers including `reviewed_model_backed_board_source_pick_place`, and summary/JSONL/CSV/model/manifest/README artifact paths populated
- `gripper_camera_pov_review.status: "ok"` with open/approach/grasp/release state IDs, frame paths, annotated-frame paths, metadata paths, metadata contract checks, target center geometry, gripper state, and piece visibility rows populated
- `visual_review.status: "ok"` with gripper POV, pose fixture, and pick/place sequence contact-sheet PNG paths populated, distance-annotated pick/place sequence frames populated under `frame_sequences`, `depth_distance_scorecard.paths.png`/`.json` populated with the at-a-glance simulator-vs-baseline residual scorecard and missing-real-depth labels, `distance_metrics.paths.json`/`.csv` populated with simulator-ground-truth depth/distance fields, `perceived_depth_comparison.paths.json`/`.csv` populated with estimate-vs-ground-truth residual fields, `pnp_residual_diagnostics.paths.json`/`.csv` populated with source-comparability residual fields, `metadata_native_depth_view.paths.png`/`.json`/`.csv` populated with camera-model-aligned simulator projection/depth fields, and `recordings.*` populated with either a best-effort MP4 path or a skipped reason
- `real_projection_intake.status: "missing_real_depth_reference"` in the current default state, with JSON/CSV/PNG paths populated, `real_reference_media_path` pointing at the selected image, `sim_metadata_native_depth_view_path` populated, `comparable: false`, missing real intrinsics/board-pose/depth inputs listed, residual paths unset, and sidecar valid/invalid/missing counts populated when a manifest declares sidecar paths
- `reference_capture_checklist.status: "action_required"` while only `archive/chess_test_images/current_view.jpg` is represented, with missing video, calibration-target, failure-mode, and post-pick capture requirements listed
- `app_entrypoint_metadata.status: "ok"` with `ok: true`, `frame_path`, `metadata_path`, skipped hardware/gui/OpenAI markers, passing metadata contract checks, and `app_camera_status.ok: true`
- `pick_place_scenario_matrix.aggregate_status.ok: true` with four scenario IDs and release-frame paths populated
- `pick_place_scenario_matrix.piece_visibility.all_scenarios_available: true` with per-scenario visible fraction, occlusion fraction, and gripper clearance values
- `negative_check.status: "no_reference_media_selected"` when `--include-negative-check` is used
- `artifact_index.status: "ok"` with `artifact_count > 0`, `missing_artifact_count: 0`, an existing `path`, and categories covering reference media inventory, real-reference comparison when selected media exists, real projection intake, ranked candidate, perception fixture, SimCamera pose fixture, SO-101 model-source inventory, SO-101 reviewed model authority gate, SO-101 model bundle probe, SO-101 model bundle manifest, SO-101 reviewed MuJoCo bundle, SO-101 model contract, IK reachability, SO-101 MuJoCo scene/env/reset/contact/grasp evidence, SO-101 training readiness, rollout evidence, pick/place scenario, negative check, and logs

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

- `reference_media_inventory/reference_media_inventory.json`
- `reference_media_inventory/reference_media_inventory.csv`
- `reference_media_inventory/README.md`
- `comparison_set/comparison_set_summary.json`
- `comparison_set/reference_media_comparison_rows.csv`
- `comparison_set/README.md`
- `comparison_set/reference_media_comparison_contact_sheet.png` when rendering dependencies are available
- `comparison_set/references/*/side_by_side.jpg`
- `comparison_set/references/*/overlay.jpg`
- `comparison_set/references/*/absolute_difference_heatmap.jpg`
- `simcamera_tuning_before_after/simcamera_tuning_before_after_summary.json`
- `simcamera_tuning_before_after/simcamera_tuning_before_after_rows.csv`
- `simcamera_tuning_before_after/README.md`
- `simcamera_tuning_before_after/baseline_profile_sweep/summary.json`
- `simcamera_tuning_before_after/baseline_profile_sweep/candidate_montage.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/current_overlay.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/current_absolute_difference_heatmap.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/current_side_by_side.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/best_overlay.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/best_absolute_difference_heatmap.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/best_side_by_side.jpg`
- `simcamera_tuning_before_after/baseline_profile_sweep/candidates/*`
- `simcamera_tuning_before_after/current_profile_sweep/summary.json`
- `simcamera_tuning_before_after/current_profile_sweep/candidate_montage.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/current_overlay.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/current_absolute_difference_heatmap.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/current_side_by_side.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/best_overlay.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/best_absolute_difference_heatmap.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/best_side_by_side.jpg`
- `simcamera_tuning_before_after/current_profile_sweep/candidates/*`
- `session/session_summary.json`
- `session/candidates/*/comparison/side_by_side.jpg`
- `session/candidates/*/comparison/absolute_difference_heatmap.jpg`
- `session/candidates/*/board_pose/frame_annotated.jpg`
- `session/candidates/*/pick_place/06_target_release_open.jpg`
- `fixture/fixture_summary.json`
- `sim_camera_pose_fixture/sim_camera_pose_fixture_summary.json`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_summary.json`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_checklist.csv`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_review_packet.json`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_review_packet.csv`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_intake_checklist.json`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_intake_checklist.csv`
- `so101_model_bundle_manifest/so101_model_bundle_manifest_template.json`
- `so101_model_bundle_manifest/README.md`
- `so101_model_source_inventory/so101_model_source_inventory_summary.json`
- `so101_model_source_inventory/so101_model_source_candidates.csv`
- `so101_model_source_inventory/so101_model_source_inventory_review_packet.json`
- `so101_model_source_inventory/so101_model_source_inventory_review_packet.csv`
- `so101_model_source_inventory/so101_model_source_intake_checklist.json`
- `so101_model_source_inventory/so101_model_source_intake_checklist.csv`
- `so101_model_source_inventory/README.md`
- `so101_reviewed_model_authority_gate/so101_reviewed_model_authority_gate.json`
- `so101_reviewed_model_authority_gate/so101_reviewed_model_authority_gate_checklist.csv`
- `so101_reviewed_model_authority_gate/so101_reviewed_model_authority_blocker_packet.json`
- `so101_reviewed_model_authority_gate/so101_reviewed_model_authority_blocker_packet.csv`
- `so101_reviewed_model_authority_gate/README.md`
- `so101_model_bundle_probe/so101_model_bundle_probe_summary.json`
- `so101_model_bundle_probe/so101_model_bundle.candidate.json`
- `so101_model_bundle_probe/so101_model_bundle_review_packet.json`
- `so101_model_bundle_probe/so101_model_bundle_review_packet.csv`
- `so101_model_bundle_probe/so101_model_bundle_probe_checklist.csv`
- `so101_model_bundle_probe/README.md`
- `so101_training_readiness_gate/so101_training_readiness_gate.json`
- `so101_training_readiness_gate/so101_training_readiness_gate_checklist.csv`
- `so101_training_readiness_gate/so101_training_readiness_gate_priority_queue.csv`
- `so101_training_readiness_gate/README.md`
- `so101_model_contract/so101_model_contract_summary.json`
- `so101_model_contract/so101_model_contract_checklist.csv`
- `so101_model_contract/README.md`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_summary.json`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_assets.csv`
- `so101_model_contract/so101_model_asset_preflight/README.md`
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

The report includes the category summary table, artifact and missing counts, hardware/gui/OpenAI skipped markers, a `Reference Media Inventory` section with candidate counts, current gripper reference detection, linked JSON/CSV/README artifacts, and reference gaps, the suite-indexed `SimCamera Tuning Before/After` section with 72px baseline-vs-current deltas and child sweep links, the reference capture checklist, visual-review contact sheets, pick/place sequence frames, pick/place depth-distance scorecard PNG/JSON, pick/place depth/distance metric JSON/CSV, compact per-stage perceived-depth, metadata-native projection/depth, real projection intake, and PnP residual diagnostic tables, real-reference comparison images, ranked candidate captures, perception fixture evidence, SimCamera pose fixture metadata, app-entrypoint metadata evidence, all pick/place release frames, negative-check status, and child stdout/stderr links.

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
