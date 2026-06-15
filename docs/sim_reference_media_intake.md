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
real-camera depth evidence.

To turn the current gap into a capture plan without adding hardware requirements, generate the reference capture checklist from an existing inventory or suite summary:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_capture_checklist.py /private/tmp/lerobot_sim/reference_media_inventory/reference_media_inventory.json --output-dir /private/tmp/lerobot_sim/reference_capture_checklist
```

The checklist writes `reference_capture_checklist.json` and `reference_capture_checklist.md`. It marks the current `archive/chess_test_images/current_view.jpg` frame as the only represented real-media baseline, lists missing overhead, calibration-target, approach/release video, occlusion/failure-mode, lighting-variant, and post-pick verification captures, and includes suggested filenames plus manifest fields for future SO-101 media.
