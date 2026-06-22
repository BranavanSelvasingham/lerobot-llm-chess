# SO-101 MuJoCo Grasp Probe

Use this smoke after the board-contact probe to validate gripper contact plus a
development-fixture lift, transfer, place, release, and retreat sequence in the
generated MJCF scene.

```bash
python scripts/smoke_sim_so101_mujoco_grasp_probe.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_grasp_probe
```

Artifacts:

- `so101_mujoco_grasp_probe_summary.json`
- `so101_mujoco_grasp_probe_rows.csv`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `README.md`

The smoke manually places a contact-tuned fixture piece between the development
gripper fingers once, closes the generated gripper, records whether gripper and
two-finger contact are visible, then runs lift, transfer, lower, release, and
retreat without manually moving the piece freejoint again.

Expected current status is
`contact_grasp_lift_place_physics_verified`: contact plumbing is visible, the
piece lifts under gripper contact, transfers toward `e5`, lands on the board
within the target tolerance, and gripper contact clears after retreat.
The summary must keep `model_authority: "development_scaffold_not_reviewed"`,
`observed_evidence_is_physical_so101_authority: false`,
`observed_evidence_is_policy_training_authority: false`,
`development_fixture_evidence_not_physical_so101_truth: true`,
`development_fixture_evidence_not_policy_training_truth: true`,
`ready_for_model_backed_ik: false`, and `ready_for_policy_training: false`.

Pinned-source simulation gate evidence from the next-step run:

```bash
python scripts/smoke_sim_so101_mujoco_grasp_probe.py \
  --output-dir /private/tmp/lerobot_sim/so101_mujoco_grasp_probe_next_gate
```

Expected key fields are `ok: true`,
`status: "contact_grasp_lift_place_physics_verified"`,
`lift_place_physics_verified: true`, `ready_for_model_backed_ik: false`, and
`ready_for_policy_training: false`.

This is still not physical SO-101 grasp truth. It uses the generated
`development_scaffold_not_reviewed` MJCF, an enlarged/lightened contact-tuned
fixture piece, and a fixture-start grasp. Follow it with
`smoke_sim_so101_mujoco_board_pick_probe.py` for seeded development board-source
pickup evidence. Serious policy training still needs reviewed SO-101 model
authority, calibrated TCP/gripper offset, base-to-board alignment, and
board-source pickup with reviewed model-backed IK.
