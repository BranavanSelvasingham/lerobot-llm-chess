# SO-101 MuJoCo Board Pick Probe

Use this smoke after the gripper fixture probe to validate board-source
pick/place behavior in the generated development MJCF scene.

```bash
python scripts/smoke_sim_so101_mujoco_board_pick_probe.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_board_pick_probe
```

Artifacts:

- `so101_mujoco_board_pick_probe_summary.json`
- `so101_mujoco_board_pick_probe_rows.csv`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `README.md`

For focused seeded-fixture boundary coverage, run:

```bash
python scripts/smoke_sim_so101_mujoco_board_pick_probe_matrix.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_board_pick_probe_matrix
```

The matrix writes `so101_mujoco_board_pick_probe_matrix_summary.json`,
`so101_mujoco_board_pick_probe_matrix_cases.csv`, and `README.md`. It expects
the current seeded `e4 -> e5` fixture to pass and alternate target/source
placements to record place/pick gaps. Those gap cases are intentional: they
show that direct seeded source pose is not generalized reviewed model-backed
IK.

The smoke resets the free piece onto source square `e4`, seeds the development
robot at a source-pick pose, closes on the board piece, lifts it off the board,
transfers toward `e5`, lowers, releases, and retreats without manually moving
the piece freejoint after the initial reset.

Expected current status is
`development_board_source_pick_place_verified`: the source pick starts at the
source square, two-finger contact is visible after close/settle, the piece
lifts while board contact clears, the transfer moves toward the target, the
piece lands within the target XY tolerance, and gripper contact clears after
retreat.

This is still development evidence, not physical SO-101 grasp truth. It uses
the generated `development_scaffold_not_reviewed` MJCF, an enlarged/lightened
contact-tuned piece, and a seeded source robot pose. Serious policy training
still needs reviewed SO-101 model authority, calibrated TCP/gripper offset,
base-to-board alignment, and the same board-source pick/place proof using
reviewed model-backed IK instead of direct pose seeding.
