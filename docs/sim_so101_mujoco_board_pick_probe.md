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
IK. It also expects malformed board-pick requests, such as invalid source
squares, invalid target squares, or identical source/target squares, to fail
closed with summary, CSV, and README artifacts while leaving model XML and
manifest files ungenerated.
The matrix explicitly exports and checks the contact path booleans for
board-contact clearance during lift, release-contact clearance after retreat,
final board contact, and final target XY tolerance so downstream rollout gates
do not have to infer those conditions from one aggregate pick/place flag.
It also checks the machine-readable phase contract:
`pick_place_phase_evidence`, `pick_place_phase_ids`,
`pick_place_failed_phase_ids`, `pick_place_phase_count`, and
`pick_place_all_required_phases_verified`. The required phases are
`source_reset`, `two_finger_grasp`, `lift_clearance`,
`transfer_toward_target`, and `release_place`. The matrix reports
`phase_evidence_contract_ok` and `phase_evidence_contract_error_count`, and
each case records `phase_evidence_contract_errors`; these checks require the
phase row `ok` values, failed-phase IDs, aggregate all-required flag, and
top-level pick/place booleans to agree.
The probe and matrix also expose a stage-sequence contract:
`required_stage_sequence`, `observed_stage_sequence`, `stage_sequence_order_ok`,
`stage_sequence_contract_ok`, `stage_sequence_contract_errors`, and
`manual_piece_pose_after_reset_stage_ids`. Valid cases must record the expected
reset/lower/close/lift/transfer/lower/release/retreat row order, and invalid
cases must fail closed without generated model artifacts.

The smoke resets the free piece onto source square `e4`, seeds the development
robot at a source-pick pose, closes on the board piece, lifts it off the board,
transfers toward `e5`, lowers, releases, and retreats without manually moving
the piece freejoint after the initial reset.

Expected current status is
`development_board_source_pick_place_verified`: the source pick starts at the
source square, two-finger contact is visible after close/settle, the piece
lifts while board contact clears, the transfer moves toward the target, the
piece lands back on the board within the target XY tolerance, and gripper
contact clears after retreat. The placement check now also records
`final_place_z_error_m` against `place_z_tolerance_m`, so the release/place
phase is not only an XY check.

This is still development evidence, not physical SO-101 grasp truth. It uses
the generated `development_scaffold_not_reviewed` MJCF, an enlarged/lightened
contact-tuned piece, and a seeded source robot pose. Serious policy training
still needs reviewed SO-101 model authority, calibrated TCP/gripper offset,
base-to-board alignment, and the same board-source pick/place proof using
reviewed model-backed IK instead of direct pose seeding.
The summary and matrix keep this boundary explicit through
`observed_evidence_is_physical_so101_authority: false`,
`observed_evidence_is_policy_training_authority: false`,
`development_fixture_evidence_not_physical_so101_truth: true`,
`development_fixture_evidence_not_policy_training_truth: true`,
`ready_for_model_backed_ik: false`, and
`ready_for_policy_training: false`.
The training-readiness gate reports that promotion boundary through
`board_pick_authority_status` and `board_pick_authority_blockers`, so detailed
phase/stage evidence can be distinguished from reviewed model-backed
pick/place authority.
The summary keeps that handoff machine-readable through
`next_required_for_goal`, `next_required_action_ids`, and
`next_required_action_count`; current action IDs include
`supply_reviewed_so101_model_bundle_manifest`,
`calibrate_reviewed_tcp_and_base_to_board_alignment`, and
`repeat_board_pick_with_reviewed_model_backed_ik`.
