# SO-101 MuJoCo Contact Probe

Use this smoke after the development MuJoCo scene gate to validate that the
generated chess piece is resettable as a MuJoCo free body and can contact the
board collision geometry:

```bash
python scripts/smoke_sim_so101_mujoco_contact_probe.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_contact_probe
```

The script writes:

- `so101_mujoco_contact_probe_summary.json`
- `so101_mujoco_contact_probe_rows.csv`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `README.md`

The smoke resets `piece_source_freejoint` to several chess squares, lets MuJoCo
settle the piece onto the board, and records body position residuals plus
board/piece contact counts. The summary must report:

- `all_piece_resets_ok: true`
- `all_board_contacts_observed: true`
- `model_authority: "development_scaffold_not_reviewed"`
- `ready_for_model_backed_ik: false`

This is still not grasp validation. It only proves that the generated scene now
has resettable piece state and board-contact plumbing. Gripper/piece grasp,
lift, place, friction tuning, and physical IK truth still require the reviewed
SO-101 model bundle, calibrated TCP, and base-to-board alignment. Run
[SO-101 MuJoCo grasp probe](sim_so101_mujoco_grasp_probe.md) next to record the
current gripper-contact fixture evidence and verify development-fixture
lift/place physics without manual piece motion after the initial fixture setup.
