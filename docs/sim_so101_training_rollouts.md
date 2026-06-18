# SO-101 Training Rollout Smoke

Use this smoke after the development MuJoCo scene gate to collect deterministic
expert rollouts for a narrow chess pick/place curriculum:

```bash
python scripts/smoke_sim_so101_training_rollouts.py --output-dir /private/tmp/lerobot_sim/so101_training_rollouts
```

The script writes:

- `so101_training_rollouts_summary.json`
- `so101_training_rollouts.jsonl`
- `so101_training_rollout_episodes.csv`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `README.md`

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
- `model_authority: "development_scaffold_not_reviewed"`
- `ready_for_model_backed_ik: false`

These rollouts are useful as a narrow debugging/imitation-learning curriculum,
but they are not final robot-training evidence. The environment still uses
symbolic piece transfer, and the MJCF is a generated development scaffold. Real
training should wait for a reviewed SO-101 model bundle, calibrated TCP offset,
base-to-board alignment, and contact-validated grasp/place physics.

For reset-specific validation before collecting rollouts, run
[docs/sim_so101_env_resets.md](sim_so101_env_resets.md). That smoke checks
explicit and sampled task resets, phase reset, source-square piece placement,
fallback-free MuJoCo status, and source-square freejoint placement. For direct
MuJoCo board-contact evidence, run
[docs/sim_so101_mujoco_contact_probe.md](sim_so101_mujoco_contact_probe.md).
