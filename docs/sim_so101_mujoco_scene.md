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
- `observed_evidence_is_physical_so101_authority: false`
- `observed_evidence_is_policy_training_authority: false`
- `development_fixture_evidence_not_physical_so101_truth: true`
- `development_fixture_evidence_not_policy_training_truth: true`
- `ready_for_model_backed_ik: false`
- `ready_for_policy_training: false`
- `mujoco_scene_validity_status: "development_scene_validated_not_physical_authority"`
- source and target squares, `square_geom_count: 64`, target-frame site
  presence, and target marker presence
- `mujoco_model_load.ok: true`
- `mujoco_model_load.required_model_joints` containing the six controlled
  SO-101 joints plus `piece_source_freejoint`, with `missing_joints: []`
- `mujoco_model_load.required_limited_joints` containing the six controlled
  SO-101 joints, with no missing, unlimited, or invalid-range required joints
- `mujoco_model_load.required_gripper_collision_geoms` containing both gripper
  finger collision geoms, with `missing_gripper_collision_geoms: []`
- `sim_robot_mujoco_sync.ok: true`
- `sim_robot_mujoco_sync.after_status.fallback: null`
- `env_scripted_pick_place.scripted_pick_place_complete: true`

The smoke can also ingest the reviewed MuJoCo downstream handoff emitted by
`smoke_sim_so101_reviewed_mujoco_bundle.py`:

```bash
python scripts/smoke_sim_so101_mujoco_scene.py \
  --reviewed-mujoco-handoff-json /path/to/so101_reviewed_mujoco_bundle_downstream_handoff.json \
  --require-reviewed-mujoco-handoff
```

The intake is contract-checked before readiness is trusted. A handoff must use
the current downstream schema, include the complete item set
(`model_authority`, `model_identity`, `target_frame`, `tcp_offset_m`,
`base_to_board_alignment`, `joint_limits`, `mesh_assets`, `mujoco_motion`, and
`downstream_gate_handoff`), preserve false physical-truth claims, and make
`downstream_handoff_ready` coherent with physical reviewed MuJoCo motion. It
also requires the handoff gate list to keep `mujoco_scene_validity`,
`gymnasium_task_wiring`, and reviewed-model-backed pick/place explicit. Ready
handoffs must also preserve
`downstream_priority_gate_id: "reviewed_mujoco_handoff"`,
`downstream_priority_gate_order` in that same order,
`next_downstream_gate_after_ready: "mujoco_scene_validity"`,
`blocks_downstream_gates_until_ready: true`, and
`ready_does_not_imply_policy_training_ready: true`. Ready
or fixture-ready handoffs must also carry a present/matching
`reviewed_model_identity_contract_ok` checkpoint with reviewed model path and
declared/observed SHA-256 evidence, plus
`mujoco_motion_inputs.mujoco_joint_limit_enablement` with
`status: "so101_mujoco_joints_limited"` and no missing limited SO-101 joints.
Fixture motion, incomplete ready payloads, forged ready flags, missing
downstream gate entries, missing model-identity evidence, missing declared or
observed reviewed model SHA-256 values, mismatched reviewed model hashes,
missing/enforced joint-limit evidence, mismatched handoff `next_required_action_ids`
versus action IDs derived from `next_required_for_goal`, or handoffs that
point the next downstream gate away from `mujoco_scene_validity` or claim
authority, physical SO-101 truth, or policy-training authority fail closed when
the handoff is required.

Invalid scene requests fail closed with artifacts instead of a traceback. For
example, an invalid chess square or identical source/target square writes
`so101_mujoco_scene_summary.json`, an empty steps CSV, and `README.md`, returns
nonzero, reports `status: "invalid_task_configuration"`, keeps
`ready_for_model_backed_ik: false` and `ready_for_policy_training: false`, and
does not generate a model XML or manifest.

For focused scene-placement coverage, run:

```bash
python scripts/smoke_sim_so101_mujoco_scene_matrix.py --output-dir /private/tmp/lerobot_sim/so101_mujoco_scene_matrix
```

The matrix writes `so101_mujoco_scene_matrix_summary.json`,
`so101_mujoco_scene_matrix_cases.csv`, and `README.md`. It validates generated
development scenes across center, corner, back-rank, and edge placements, plus
fail-closed invalid source-square, invalid target-square, same-source/target,
and non-positive max-step cases, fail-closed required handoff cases for
not-ready, fixture-only, forged-ready, and incomplete-ready handoffs, ready
handoffs with open review work, and ready
handoffs that claim authority/physical SO-101 truth, drift explicit handoff
action IDs from `next_required_for_goal`, omit enforced SO-101 model identity
hash evidence, omit enforced SO-101 joint-limit evidence,
or drift the next downstream gate away from
`mujoco_scene_validity`, plus valid optional and required ready-handoff intake
cases that still keep the generated scene development-only,
while keeping every case labeled as non-authoritative development scaffolding.
Passing matrix cases also assert the required model joint set, finite limited
joint ranges for the six controlled SO-101 joints, and both gripper collision
geoms so scene-validity regressions cannot hide behind aggregate load status.

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
