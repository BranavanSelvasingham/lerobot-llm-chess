# SO-101 Training Rollout Smoke

Use this smoke after the development MuJoCo board-pick probe to collect
deterministic expert rollouts for a narrow chess pick/place curriculum:

```bash
python scripts/smoke_sim_so101_mujoco_board_pick_probe.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_board_pick_probe

python scripts/smoke_sim_so101_training_rollouts.py \
  --development-board-pick-summary-json /private/tmp/lerobot_sim/so101_mujoco_board_pick_probe/so101_mujoco_board_pick_probe_summary.json \
  --output-dir /private/tmp/lerobot_sim/so101_training_rollouts
```

The script writes:

- `so101_training_rollouts_summary.json`
- `so101_training_rollouts.jsonl`
- `so101_training_rollout_episodes.csv`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `README.md`

For focused rollout-boundary coverage, run:

```bash
python scripts/smoke_sim_so101_training_rollouts_matrix.py --output-dir /private/tmp/lerobot_sim/so101_training_rollouts_matrix --python .venv/bin/python
```

The matrix writes `so101_training_rollouts_matrix_summary.json`,
`so101_training_rollouts_matrix_cases.csv`, and `README.md`. It verifies the
default development rollout curriculum, missing and failed board-pick
prerequisite fail-closed behavior, and a short-budget incomplete rollout. The
matrix must keep `observed_evidence_is_policy_training_authority: false` and
`ready_for_policy_training: false`.

Each JSONL transition contains:

- task source/target square
- previous observation
- scripted expert action
- reward, termination, and truncation flags
- next observation
- current MuJoCo status and scene state

The default task set covers center-board, file-edge, back-rank, near-gripper,
and horizontal moves. Custom tasks are repeatable:

```bash
python scripts/smoke_sim_so101_training_rollouts.py \
  --development-board-pick-summary-json /private/tmp/lerobot_sim/so101_mujoco_board_pick_probe/so101_mujoco_board_pick_probe_summary.json \
  --task e4:e5 \
  --task a4:a5 \
  --output-dir /private/tmp/lerobot_sim/so101_training_rollouts_custom
```

The summary must report:

- `all_scripted_pick_place_complete: true`
- `all_mujoco_fallback_free: true`
- `all_mujoco_piece_release_synced: true`
- `episode_count` greater than zero
- `transition_count` greater than zero
- `development_prerequisites_satisfied: true`
- `training_authority_status: "development_rollouts_prerequisites_verified_not_policy_ready"`
- `model_authority: "development_scaffold_not_reviewed"`
- `observed_evidence_is_physical_so101_authority: false`
- `observed_evidence_is_policy_training_authority: false`
- `ready_for_model_backed_ik: false`
- `ready_for_policy_training: false`
- `serious_policy_training_blockers` includes `reviewed_model_backed_board_source_pick_place`

These rollouts are useful as a narrow debugging/imitation-learning curriculum,
but they are not final robot-training evidence. The environment still uses
symbolic piece transfer, and the MJCF is a generated development scaffold. Real
training should wait for a reviewed SO-101 model bundle, calibrated TCP offset,
base-to-board alignment, and contact-validated grasp/place physics using
reviewed model-backed IK. The required board-pick summary proves only the
development-fixture source-board pickup gate; it does not remove those blockers.
The suite-level training-readiness gate therefore distinguishes the rollout's
raw `ready_for_policy_training` flag from the computed
`rollout_policy_training_authority_ready` flag. Both policy-ready rollouts and
the board-source pick/place prerequisite must carry reviewed SO-101 model
authority before the serious-training gate can close.

For reset-specific validation before collecting rollouts, run
[docs/sim_so101_env_resets.md](sim_so101_env_resets.md). That smoke checks
explicit and sampled task resets, phase reset, source-square piece placement,
fallback-free MuJoCo status, and source-square freejoint placement. For direct
MuJoCo board-contact evidence, run
[docs/sim_so101_mujoco_contact_probe.md](sim_so101_mujoco_contact_probe.md).
For direct development board-source pick/place evidence, run
[docs/sim_so101_mujoco_board_pick_probe.md](sim_so101_mujoco_board_pick_probe.md)
and pass its summary JSON to this rollout smoke.
