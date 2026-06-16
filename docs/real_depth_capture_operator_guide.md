# Real Depth Capture Operator Guide

Use this guide when preparing the first physical SO-101 depth/distance capture for simulator calibration. The workflow is intentionally hardware-free until the operator supplies files and measurements.

## Plan The Session

Generate the default missing-input operator package:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/plan_real_depth_capture_session.py \
  --output-dir /private/tmp/lerobot_sim/real_depth_capture_plan_missing
```

Generate the synthetic positive fixture package that proves residual and scorecard plumbing only:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/plan_real_depth_capture_session.py \
  --manifest test_data/real_calibration_sidecars/reference_media_manifest.synthetic_real_capture_test.json \
  --scenario-label synthetic_real_capture_fixture \
  --output-dir /private/tmp/lerobot_sim/real_depth_capture_plan_fixture
```

The planner writes a Markdown operator plan and JSON report. It does not open cameras, move motors, start GUI code, call OpenAI, or modify SimCamera geometry. In the default missing-input state, it does not validate the placeholder manifest path; it tells the operator to generate sidecars first, then validate the generated manifest under the capture-sidecar output directory.

## Physical Measurements Needed

- Reference media: repo-local SO-101 gripper-camera chessboard image, `capture_id`, `camera_id`, and image resolution.
- Intrinsics: real camera matrix, distortion model, distortion coefficients, calibration source, and matching image size.
- Extrinsics: camera-to-board or board-to-camera transform with the documented OpenCV camera frame convention.
- Board corners: ordered `a1,h1,h8,a8` image coordinates, confidence if available, and board size if known.
- Depth references: measured camera range or z-depth to board center, piece center/top, or target square; include units, scale, target labels, and optional pixel locations.

## Produce Sidecars

After the operator has real measurements, use the existing sidecar helper and pass `--real-capture` only for physical SO-101 data:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/prepare_real_calibration_capture_sidecars.py \
  --image-path path/to/real_so101_depth_capture.jpg \
  --capture-id so101_depth_capture_001 \
  --camera-id so101_gripper_camera \
  --image-size 640x480 \
  --camera-matrix-json '[[fx,0,cx],[0,fy,cy],[0,0,1]]' \
  --distortion-json '[k1,k2,p1,p2,k3]' \
  --corner a1:x,y --corner h1:x,y --corner h8:x,y --corner a8:x,y \
  --distance board_center:0.500:x,y \
  --real-capture \
  --require intrinsics --require extrinsics --require board_pose --require depth \
  --output-dir /private/tmp/lerobot_sim/real_capture_sidecars
```

Validate the generated manifest or sidecars before running the full suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_real_calibration_sidecars.py \
  --manifest /private/tmp/lerobot_sim/real_capture_sidecars/reference_media_manifest.generated_sidecars.json \
  --require-valid-count 4 \
  --output-dir /private/tmp/lerobot_sim/real_capture_sidecar_validation
```

## Generate Scorecard Evidence

Run the full regression suite with the real-capture manifest:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py \
  --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  --reference-media-manifest /private/tmp/lerobot_sim/real_capture_sidecars/reference_media_manifest.generated_sidecars.json \
  --output-dir /private/tmp/lerobot_sim/real_depth_capture_suite
```

Inspect these outputs:

- `visual_review/pick_place_depth_distance_scorecard.png`
- `visual_review/pick_place_depth_distance_scorecard.json`
- `real_projection_intake/real_projection_intake.json`
- `real_projection_intake/real_projection_residuals.json`
- `real_projection_intake/real_projection_residual_overlay_contact_sheet.png`

The default state should report `missing_real_depth_reference`. A real physical capture with valid `real_capture: true` sidecars should report `real_depth_comparable`. Synthetic fixtures may exercise that path, but they are not calibration truth.
