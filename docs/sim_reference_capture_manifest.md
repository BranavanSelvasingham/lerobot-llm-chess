# Simulator Reference Capture Manifest

Use this hardware-free checker after the reference media inventory, reference media comparison, reference camera tuning diagnostics, SimCamera before/after evidence, and capture checklist have identified the current real-media gap. It validates an operator-maintained manifest for the missing real depth-reference and pick/place-video inputs needed before future SimCamera tuning should be described as calibration-grade.

The checker does not open cameras, move SO-101 hardware, modify simulator constants, run robot execution paths, call OpenAI, or copy photos/videos into the repository.

## Integrated Suite Path

The calibration regression suite runs this checker every time under `reference_capture_manifest/`. The default no-manifest run is green and records `reference_capture_manifest_not_supplied` with the open gaps:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py \
  --output-dir /private/tmp/lerobot_sim/calibration_regression_suite \
  --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
```

To check a local operator manifest through the full artifact path:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py \
  --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_capture_manifest \
  --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  --reference-capture-manifest /absolute/path/to/reference_capture_manifest.json
```

The suite exposes the result in `calibration_regression_summary.json.reference_capture_manifest`, `child_commands.reference_capture_manifest`, `artifact_index.json.reference_capture_manifest`, and the `Reference Capture Manifest` section of `artifact_index_report.md`. A nonexistent manifest path stays non-failing and records `reference_capture_manifest_unavailable`.

## Use In The Real Depth Operator Plan

The existing [real depth capture operator plan](real_depth_capture_operator_guide.md) can consume either the focused checker JSON or the full suite summary:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/plan_real_depth_capture_session.py \
  --calibration-suite-summary-json /private/tmp/lerobot_sim/calibration_regression_suite/calibration_regression_summary.json \
  --output-dir /private/tmp/lerobot_sim/real_depth_capture_plan_from_suite
```

That bridge copies no media and opens no media. It carries the suite-indexed capture-manifest status, readiness flag, capture counts, missing path count, diagnostics/gaps, manifest path, and local-only/no-copy status into the operator plan. Not-ready evidence becomes explicit next actions for depth reference capture, pick/place video capture, sidecars, provenance/review, and local-only no-copy policy. Ready evidence is still only input readiness; physical calibration claims require later sidecar/intake validation and residual comparison evidence.

For a narrow regression of that planner bridge without running the full suite, use:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_real_depth_capture_plan_manifest_bridge.py \
  --output-dir /private/tmp/lerobot_sim/real_depth_capture_plan_bridge_smoke
```

The bridge smoke creates a no-manifest checker JSON with `reference_capture_manifest_not_supplied`, a ready synthetic manifest/checker result, and a minimal ready suite summary under its output directory only. It invokes `scripts/plan_real_depth_capture_session.py` for the missing direct-check JSON and ready suite-summary paths, then writes JSON/CSV/README artifacts summarizing planner exits, evidence status, readiness, capture counts, no-copy status, caveats, and next operator actions. Its ready case uses text placeholders for path-existence checks; it does not copy, open, decode, modify, or commit photos/videos.

## Focused Checker

No-manifest diagnostic run:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_capture_manifest.py \
  --output-dir /private/tmp/lerobot_sim/reference_capture_manifest
```

Manifest run:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_capture_manifest.py \
  --manifest-path /absolute/path/to/reference_capture_manifest.json \
  --output-dir /private/tmp/lerobot_sim/reference_capture_manifest
```

The output directory contains:

- `reference_capture_manifest_check.json`: deterministic manifest status, readiness, diagnostics, path checks, and required-field results.
- `reference_capture_manifest_checklist.csv`: flat required-field and path-existence rows for review.
- `README.md`: human-readable status, required fields, diagnostics, and path checks.

If `--manifest-path` is omitted, the script exits `0` with `status: "reference_capture_manifest_not_supplied"` and writes the required-field artifacts. If the requested manifest path does not exist, it exits `0` with `status: "reference_capture_manifest_unavailable"`. Missing referenced media or sidecar paths are diagnostics, not process failures.

## Manifest Shape

The checker accepts a JSON object. Prefer this shape for new operator manifests:

```json
{
  "schema": "lerobot.sim.reference_capture_manifest.v1",
  "media_assets_copied_into_repo": false,
  "local_only_no_copy_policy": {
    "enabled": true,
    "operator_acknowledged": true
  },
  "provenance": {
    "capture_operator": "operator name",
    "capture_date_utc": "YYYY-MM-DD",
    "source": "real SO-101 chess setup",
    "camera_id": "camera identifier"
  },
  "review": {
    "reviewed_by": "reviewer name",
    "review_date_utc": "YYYY-MM-DD",
    "review_status": "operator_reviewed"
  },
  "depth_reference_captures": [
    {
      "capture_id": "so101_depth_reference_001",
      "media_path": "../local_reference_media/depth_reference_001.png",
      "depth_sidecar_path": "../local_reference_media/depth_reference_001.json",
      "measured_depth_targets": [
        {
          "id": "board_center_range",
          "distance_m": 0.506,
          "pixel_xy": [320.0, 207.0]
        }
      ],
      "board_camera_pose_notes": "Board/camera pose notes or transform source.",
      "camera_intrinsics_or_capture_metadata": {
        "status": "measured or sidecar-linked"
      }
    }
  ],
  "pick_place_video_captures": [
    {
      "capture_id": "so101_pick_place_001",
      "media_path": "../local_reference_media/pick_place_001.mp4",
      "capture_metadata_path": "../local_reference_media/pick_place_001_metadata.json",
      "gripper_arm_visibility_notes": "Fingers, wrist, pickup, release, and occlusion are visible.",
      "board_camera_pose_notes": "Same camera/board setup as the depth reference."
    }
  ]
}
```

Relative paths resolve against the manifest directory. The checker only tests whether referenced media and sidecar paths exist; it does not copy, decode, or validate the capture content.

## Readiness

The checker reports `ready_for_calibration_grade_simcamera_tuning: true` only when:

- At least one depth-reference capture exists.
- At least one pick/place-video capture exists.
- All referenced media and sidecar files exist.
- Provenance and review fields are present.
- Depth/distance sidecar fields and measured targets are populated.
- The manifest explicitly preserves `media_assets_copied_into_repo: false` and a local-only/no-copy policy.

Otherwise it reports `reference_capture_manifest_needs_follow_up` with diagnostics such as `missing_depth_reference`, `missing_pick_place_video`, `missing_depth_sidecar`, `missing_provenance_review`, `missing_referenced_paths`, and `media_assets_copied_into_repo=false`.

## Relation To Existing Evidence

The reference media inventory finds and classifies available local evidence, then preserves gaps such as missing real depth and missing pick/place video. The reference comparison and reference camera tuning diagnostics can select images and produce hardware-free image/metadata review artifacts, but they still carry those gaps forward. The SimCamera profile sweep and SimCamera tuning before/after smoke compare synthetic baseline/current evidence and explicitly report `media_assets_copied_into_repo: false`, missing real depth, and missing pick/place-video inputs.

This manifest checker is the operator-facing bridge after those diagnostics: it verifies that the missing real captures and sidecars have been produced locally and reviewed, without adding media assets or changing runtime behavior. In the integrated suite it appears beside reference media inventory, reference comparison, camera tuning diagnostics, SimCamera before/after evidence, the capture checklist, and SimCamera pose evidence so reviewers can see input readiness and remaining gaps in one artifact bundle. Even a ready manifest is still an input-readiness signal. Physical calibration claims require subsequent real sidecar comparison/residual evidence from the existing intake path, not just the manifest check.
