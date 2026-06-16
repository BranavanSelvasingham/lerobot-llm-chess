# Simulator Reference Media Inventory

Use this hardware-free inventory before treating synthetic simulator frames as calibration evidence. It scans local project or optional sibling roots, records image/video/reference-data candidates, and reports whether real-world POV evidence is present for board appearance, camera viewpoint, gripper occlusion, depth/workspace geometry, calibration targets, and pick/place motion.

Default repo-only scan:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_media_inventory.py --output-dir /private/tmp/lerobot_sim/reference_media_inventory
```

Explicit multi-root scan, keeping the repo plus an optional sibling checkout:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_media_inventory.py \
  --root . \
  --root /Users/branavan/GitHub/lerobot-chess \
  --output-dir /private/tmp/lerobot_sim/reference_media_inventory_with_sibling
```

Supplying any `--root` replaces the default, so use `--root .` when adding sibling roots. Unreadable or missing roots are reported under `scan.scan_issues`; media is never copied into the repository or output directory.

The output directory contains:

- `reference_media_inventory.json`: deterministic summary, per-candidate metadata, classifications, simulator wiring, and gaps.
- `reference_media_inventory.csv`: flat review rows with path, root, extension, size, dimensions/duration when available, and heuristic classifications.
- `README.md`: reviewer entrypoint with counts, roots, missing evidence, and renderer guidance.

Candidates include common image and video extensions plus `.json`, `.yaml`, and `.yml` files whose path or first small text chunk contains camera/calibration/board/depth keywords. The script excludes VCS, virtualenv, cache, build, and generated temp directories. Image dimensions are read with Pillow when already installed, otherwise by limited stdlib header parsing for supported formats. Video duration and dimensions are read only when `ffprobe` or OpenCV is already available. Missing metadata is non-failing.

Each candidate gets transparent heuristic classes:

- `camera_pov`
- `chessboard_board`
- `gripper_arm`
- `calibration_target`
- `depth_distance`
- `ui_demo_screenshot`
- `unknown`

Top-level `status` is `media_inventory_complete` when candidates are found and `media_inventory_empty` when none are found. `reference_gaps` can include `missing_gripper_pov`, `missing_board_closeup`, `missing_depth_reference`, `missing_calibration_target`, and `missing_pick_place_video`.

Synthetic/example fixture paths are still listed as candidates, but they do not close real-reference gaps. The gaps are intended to answer whether reviewed real project or sibling evidence exists, not whether schema fixtures exercise downstream code.

Future simulator renderers should use found project or sibling media as local reference evidence for synthetic camera framing, board texture/lighting, gripper occlusion, and workspace geometry. Keep large photos/videos out of this repository unless they are intentionally reviewed fixtures; instead, record their local paths, provenance, and limitations in the inventory/manifest workflow and preserve explicit visibility gaps rather than inventing calibration truth.
