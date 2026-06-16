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

Integrated suite scan with the same repeatable roots:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_calibration_regression_suite.py \
  --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_reference_roots \
  --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  --reference-media-root . \
  --reference-media-root /Users/branavan/GitHub/lerobot-chess
```

The integrated suite writes the inventory under `reference_media_inventory/` and mirrors status, candidate counts, image/video/calibration-data counts, currently wired media count, current gripper reference detection, `reference_gaps`, scan roots, child command diagnostics, and JSON/CSV/README artifact paths into `calibration_regression_summary.json.reference_media_inventory`. It then runs the comparison smoke from that inventory JSON under `comparison_set/` and mirrors comparison status, selected candidate/media counts, visual comparison count, contact sheet path/status, JSON/CSV/README paths, external selected count, `media_assets_copied_into_repo: false`, and missing depth/pick-place-video/no-video diagnostics into `calibration_regression_summary.json.comparison_set`, `child_commands.comparison_set.diagnostics`, `artifact_index.json.reference_media_comparison`, and the rendered `Reference Media Comparison` report section. Empty explicit roots remain successful evidence: the inventory reports `media_inventory_empty`, and the suite records the comparison-set `no_reference_media_selected` diagnostic without failing the hardware-free gate.

The output directory contains:

- `reference_media_inventory.json`: deterministic summary, per-candidate metadata, classifications, simulator wiring, and gaps.
- `reference_media_inventory.csv`: flat review rows with path, root, extension, size, dimensions/duration when available, and heuristic classifications.
- `README.md`: reviewer entrypoint with counts, roots, missing evidence, and renderer guidance.

Focused inventory-driven SimCamera comparison:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_reference_media_comparison_set.py \
  --inventory-json /private/tmp/lerobot_sim/reference_media_inventory/reference_media_inventory.json \
  --output-dir /private/tmp/lerobot_sim/reference_media_comparison_set
```

This smoke reads an existing inventory JSON and ranks a small candidate set before rendering any image artifact. The ranking is deterministic and favors the active/current gripper reference, records classified as `camera_pov` + `chessboard_board` + `gripper_arm`, repo-local media before external absolute sibling paths, and image rows before videos or calibration-data-only rows. It writes `comparison_set_summary.json`, `reference_media_comparison_rows.csv`, `README.md`, and, when OpenCV/numpy rendering is available, `reference_media_comparison_contact_sheet.png` plus per-reference derived side-by-side/overlay/difference images under `references/`.

The comparison smoke never copies media into the repository. Repo-local and sibling media paths remain references to local evidence only; the generated artifacts live under the requested output directory. If rendering dependencies are unavailable, the smoke preserves metadata-only evidence and records the dependency gap instead of failing the inventory review path.

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

The comparison smoke carries those gaps forward in `diagnostics`: `missing_depth_reference`, `missing_pick_place_video`, `no_videos`, synthetic/example rows remaining diagnostic-only, and external absolute paths being local evidence only. That makes the artifact useful for camera-first simulator tuning while still making clear that missing depth, pick/place video, and physical calibration inputs remain open.

Future simulator renderers should use found project or sibling media as local reference evidence for synthetic camera framing, board texture/lighting, gripper occlusion, and workspace geometry. Keep large photos/videos out of this repository unless they are intentionally reviewed fixtures; instead, record their local paths, provenance, and limitations in the inventory/manifest workflow and preserve explicit visibility gaps rather than inventing calibration truth.
