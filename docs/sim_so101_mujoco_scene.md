# SO-101 Development MuJoCo Scene

Use this smoke to prove the MuJoCo/Gymnasium plumbing before a reviewed SO-101
model bundle is available:

```bash
python scripts/smoke_sim_so101_mujoco_scene.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_scene
```

The script writes:

- `so101_mujoco_scene_summary.json`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `so101_mujoco_scene_env_steps.csv`
- `README.md`

The generated MJCF includes:

- SO-101 development scaffold joints: `shoulder_pan`, `shoulder_lift`,
  `elbow_flex`, `wrist_flex`, `wrist_roll`, and `gripper`
- approximate capsule/box collision geoms for arm links and gripper fingers
- a chess board collision box
- 64 square visual geoms
- a resettable `piece_source_freejoint` chess-piece body and target marker
- `gripper_frame_link` as the target-frame site

The summary must report:

- `model_authority: "development_scaffold_not_reviewed"`
- `ready_for_model_backed_ik: false`
- `mujoco_model_load.ok: true`
- `sim_robot_mujoco_sync.ok: true`
- `sim_robot_mujoco_sync.after_status.fallback: null`
- `env_scripted_pick_place.scripted_pick_place_complete: true`

This scene is intentionally not an authoritative model bundle. It is generated
from approximate repo-local dimensions and exists to validate MuJoCo loading,
joint synchronization, board/piece collision geometry availability, and the
training-facing environment API. It must not be used as physical SO-101 IK truth.

For the real model-backed path, replace this scaffold with a reviewed
URDF/MJCF/Xacro/XML model bundle that passes
[docs/sim_so101_model_bundle_manifest.md](sim_so101_model_bundle_manifest.md),
including mesh asset roots, authority/provenance, target frame, calibrated TCP
offset, and base-to-board alignment.

After this scene smoke passes, use
[docs/sim_so101_mujoco_contact_probe.md](sim_so101_mujoco_contact_probe.md) to
validate resettable piece freejoint state and board/piece contact plumbing.
Then use
[docs/sim_so101_training_rollouts.md](sim_so101_training_rollouts.md) to collect
strict-MuJoCo scripted expert rollouts across a small chess move curriculum.
Those rollouts begin the focused training path while still carrying the same
development-scaffold limitations.
