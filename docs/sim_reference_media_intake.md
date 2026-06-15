# Simulator Reference Media Intake

Use this intake path when adding future real SO-101 chess photos or videos for simulator calibration review. Media must stay repo-local, use supported image/video extensions, and be described by a JSON manifest instead of relying only on path/name heuristics.

Run the inventory without a manifest to preserve the current default behavior:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_media_inventory.py --output-dir /private/tmp/lerobot_sim/reference_media_inventory
```

Run it with the example manifest:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_media_inventory.py --manifest archive/reference_media_manifest.example.json --output-dir /private/tmp/lerobot_sim/reference_media_inventory_manifest
```

The manifest schema is intentionally compact:

- `relative_path`: repo-relative image/video path. It must resolve inside the repository and exist.
- `camera_view`: camera point of view, such as gripper-mounted, overhead, side, or recovery camera.
- `board_visibility`: board corners, files/ranks, occlusions, and crop quality.
- `piece_layout`: piece placement and whether the media is a scale/layout reference.
- `gripper_visibility`: whether fingers, wrist, and pickup zone are visible.
- `calibration_targets`: intended utility categories. Recognized targets include `camera_pov`, `board_corners`, `piece_scale`, `gripper_visibility`, `workspace_geometry`, `lighting`, and `failure_mode`.
- `failure_mode`: `none_documented` for nominal media, or a short label such as `missed_grasp`, `occluded_piece`, `bad_lighting`, or `recovery_motion`.
- `sim_profiles`: simulator profiles the media should inform, for example `current_gripper_reference`.
- `declared_tags`, `notes`, and `limitations`: review context that should survive into generated inventory JSON.
- Optional calibration sidecar paths for projection/depth comparison: `real_intrinsics_path`,
  `real_extrinsics_path`, `real_board_pose_path`, `board_corner_detections_path`,
  `real_depth_path`, and `depth_reference_path`. These should point to repo-local JSON
  artifacts with image size/camera matrix/distortion, real board pose or ordered `a1,h1,h8,a8`
  corner detections, and depth units/scale when true depth is available.

Calibration sidecar schemas are intentionally hardware-free validation scaffolding. They define
the shape of future real capture files but do not make real calibration available:

- Intrinsics sidecars use `schema: "lerobot.sim.real_calibration_sidecar.intrinsics.v1"`,
  `sidecar_type: "intrinsics"`, `camera_id`, `calibration_source`, `image_size_px`,
  `camera_matrix_px`, `distortion_coefficients`, and `units: "pixels"`.
- Extrinsics sidecars use `schema: "lerobot.sim.real_calibration_sidecar.extrinsics.v1"`,
  `sidecar_type: "extrinsics"`, `camera_id`, `transform_convention` set to
  `board_to_camera` or `camera_to_board`, `coordinate_frame_convention`, and either a
  `transform.matrix_4x4` or `translation_m` plus `rotation_matrix`.
- Board-pose or corner-detection sidecars use
  `schema: "lerobot.sim.real_calibration_sidecar.board_pose.v1"`,
  `sidecar_type: "board_pose"`, `image_size_px`, `corner_order: ["a1", "h1", "h8", "a8"]`,
  four ordered `corners[].pixel_xy` detections, and `detection_source`.
- Depth-reference sidecars use `schema: "lerobot.sim.real_calibration_sidecar.depth.v1"`,
  `sidecar_type: "depth"`, `depth_units`, `depth_scale_to_m`, `reference_frame`, and either
  `metric_references[]` with measured `distance_m` values or depth-map metadata.
- Synthetic fixtures must set `example_only: true`; they validate schema shape but do not
  make projection/depth rows comparable. Future real captures should set `real_capture: true`
  and include capture provenance in source/notes fields.

Validate the synthetic/example-only complete fixture set:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_real_calibration_sidecars.py --manifest test_data/real_calibration_sidecars/reference_media_manifest.synthetic_sidecars.example.json --require-valid-count 4 --output-dir /private/tmp/lerobot_sim/real_calibration_sidecars_valid
```

Validate a deliberate negative missing-field fixture:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_real_calibration_sidecars.py --sidecar test_data/real_calibration_sidecars/invalid_intrinsics_missing_camera_matrix.synthetic.json --expect-invalid --output-dir /private/tmp/lerobot_sim/real_calibration_sidecars_invalid
```

Current real-media state:

- The only wired real reference remains `archive/chess_test_images/current_view.jpg`.
- No real SO-101 videos were added.
- No failure-mode media was added.
- Hardware, GUI display, real camera capture, and OpenAI paths remain skipped.

The inventory output records `manifest_summary`, per-record `declared_metadata`, `manifest_validation`, merged `reference_tags`, and `calibration_utility` coverage. Downstream comparison artifacts keep the selected record metadata, so future real media can be reviewed without changing simulator rendering constants or physical robot paths.

The full regression suite also writes `real_projection_intake/real_projection_intake.json`,
`.csv`, and `real_projection_intake_contact_sheet.png`. That artifact links selected
real reference media to `visual_review/pick_place_metadata_native_depth_view.json`.
Until the optional calibration sidecars above are supplied, rows should report
`status: "missing_real_calibration"`, `comparable: false`, missing real intrinsics,
missing real board pose/corner detections, and missing real depth rather than inventing
real-camera depth evidence. When sidecar paths are declared, the intake validates the
sidecar JSON shape and reports `sidecar_validation`, `sidecar_valid_count`,
`sidecar_invalid_count`, and `sidecar_missing_count` so reviewers can distinguish valid
schemas from missing or malformed inputs. Valid `example_only` sidecars are reported as
`valid_example`; they do not satisfy real calibration availability.

When a selected media row declares sidecars that validate with `real_capture: true`, the
intake additionally writes `real_projection_residuals.json`,
`real_projection_residuals.csv`, and
`real_projection_residual_overlay_contact_sheet.png`. Those files compare real-sidecar
projection/depth data against the metadata-native SimCamera expectation: projected-point
pixel residuals, ordered board-corner detection residuals, camera z/range residuals,
metric depth-reference residuals, and camera-to-board-plane residuals. These residual
artifacts are not emitted for `example_only: true` fixtures.

To turn the current gap into a capture plan without adding hardware requirements, generate the reference capture checklist from an existing inventory or suite summary:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_capture_checklist.py /private/tmp/lerobot_sim/reference_media_inventory/reference_media_inventory.json --output-dir /private/tmp/lerobot_sim/reference_capture_checklist
```

The checklist writes `reference_capture_checklist.json` and `reference_capture_checklist.md`. It marks the current `archive/chess_test_images/current_view.jpg` frame as the only represented real-media baseline, lists missing overhead, calibration-target, approach/release video, occlusion/failure-mode, lighting-variant, and post-pick verification captures, and includes suggested filenames plus manifest fields for future SO-101 media.
