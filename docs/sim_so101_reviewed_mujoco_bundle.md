# SO-101 Reviewed MuJoCo Bundle Gate

`scripts/smoke_sim_so101_reviewed_mujoco_bundle.py` is the bridge between a
reviewed SO-101 model bundle manifest and MuJoCo training evidence.

Default mode is diagnostic-only when no reviewed bundle is ready:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_reviewed_mujoco_bundle.py --output-dir /private/tmp/lerobot_sim/so101_reviewed_mujoco_bundle
```

It writes:

- `so101_reviewed_mujoco_bundle_summary.json`
- `so101_reviewed_mujoco_bundle_checklist.csv`
- `so101_reviewed_mujoco_bundle_motion_checks.csv`
- `so101_reviewed_mujoco_bundle_downstream_handoff.json`
- `so101_reviewed_mujoco_bundle_downstream_handoff.csv`
- `README.md`

The summary carries the manifest checker's `model_authority`,
`physical_so101_model_authority_ready`,
`hardware_free_regression_fixture_ready`, and
`synthetic_fixture_authority_fields` fields. It also carries the manifest
checker diagnostics for source authority, provenance, joint-limit authority,
model-file identity, mesh-asset authority, target-frame authority, TCP offset,
and base-to-board alignment so the direct MuJoCo handoff gate shows why a bundle
is not ready
without attempting motion. Placeholder review metadata such as `TODO` or `TBD`
must keep those authority fields in `needs_review`, leave
`ready_for_model_backed_ik: false`, and keep
`motion_authority_status: "not_checked_manifest_not_ready"`. Generic review
scopes such as `model_bundle`, or missing per-field authority objects for joint
limits, mesh assets, target frame, TCP offset, or base-to-board alignment, must
also keep the manifest not ready and prevent MuJoCo motion. A hardware-free synthetic fixture
may exercise the positive MuJoCo motion path, but it stays labeled as
`hardware_free_regression_fixture_not_physical_so101_authority`. Motion evidence
also carries `motion_authority_status`,
`physical_reviewed_model_motion_checked`,
`hardware_free_fixture_motion_checked`, and
`motion_evidence_not_physical_so101_authority` so fixture-only motion cannot be
mistaken for reviewed physical SO-101 authority.

With no manifest, or with a manifest whose bundle checker does not report
`ready_for_model_backed_ik: true` after checking reviewed joint limits, mesh
evidence, model-file SHA-256 identity, target-frame authority, TCP offset, and
base-to-board alignment, the smoke exits `0` with
`status: "reviewed_mujoco_bundle_not_ready"` and
`reviewed_model_motion_checked: false`. In that not-ready state,
`motion_authority_status` is `not_checked_manifest_not_ready`, and all motion
authority booleans are `false`. The motion-checks CSV still writes one row for
each expected SO-101 joint with `status: "not_attempted_manifest_not_ready"` so
reviewers can distinguish missing model authority from missing artifact
evidence.

To reuse the integrated suite's manifest result:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_reviewed_mujoco_bundle.py --manifest-summary-path /private/tmp/lerobot_sim/calibration_regression_suite/so101_model_bundle_manifest/so101_model_bundle_manifest_summary.json --output-dir /private/tmp/lerobot_sim/so101_reviewed_mujoco_bundle
```

To make readiness mandatory:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_reviewed_mujoco_bundle.py --manifest-path /absolute/path/to/so101_model_bundle.json --require-ready-reviewed-model --output-dir /private/tmp/lerobot_sim/so101_reviewed_mujoco_bundle_required
```

When the manifest is ready, this gate must:

- load the reviewed model with `mujoco.MjModel.from_xml_path`
- find every expected SO-101 joint by name
- find the manifest target frame in the MuJoCo model
- require every expected SO-101 MuJoCo joint to enforce its range with
  `jnt_limited`
- compare the manifest body-joint limits against MuJoCo `jnt_range` values
- instantiate `SimRobot` with the reviewed model path
- verify the MuJoCo backend has no joint-state fallback
- send a deterministic joint action and confirm mapped qpos motion for all six
  SO-101 joints, including gripper qpos range mapping from the 0-100 command

Ready manifests also populate `so101_reviewed_mujoco_bundle_motion_checks.csv`
with one row per SO-101 joint. Rows preserve target, qpos, movement, range, and
authority fields from the SimRobot/MuJoCo check; fixture-only ready cases remain
machine-labeled as hardware-free evidence and not reviewed physical SO-101
truth.

Every run also writes `so101_reviewed_mujoco_bundle_downstream_handoff.json`
and `.csv`. The handoff snapshots the exact model identity, target frame, TCP
offset, base-to-board transform, joint limits, mesh evidence, and MuJoCo motion
authority that later scene, Gymnasium, and reviewed-model-backed pick/place
gates must consume. It always reports
`schema: "lerobot.sim.so101_reviewed_mujoco_bundle_downstream_handoff.v1"`,
`model_authority: "downstream_handoff_not_authority"`,
`observed_evidence_is_authority: false`, and
`physical_so101_truth_claimed: false`. It also keeps
`ready_for_policy_training: false`,
`observed_evidence_is_policy_training_authority: false`,
`policy_training_authority_claimed: false`, and
`development_fixture_evidence_not_policy_training_truth: true` so a model-motion
handoff cannot be mistaken for serious-training authority. Its
`downstream_handoff_ready` flag is
true only when physical reviewed model authority and MuJoCo/SimRobot motion are
both true; fixture-positive runs instead report
`fixture_handoff_ready_not_physical_so101_authority: true`.
Raw-ready and fixture-ready handoffs must also carry
`reviewed_model_identity_contract_ok: true` with the reviewed model path,
declared SHA-256, observed SHA-256, `model_identity.status: "present"`, and
`matches: true`; scene and training-readiness consumers reject handoffs that
claim readiness without that model identity checkpoint.
Downstream consumers must also reject any raw-ready or fixture-ready handoff
that still carries non-empty `missing_inputs`, `next_required_for_goal`, or
`next_required_action_ids`. A ready-shaped handoff with open work is
contradictory and cannot unblock scene, Gymnasium, pick/place, or training
readiness gates. The producer gate now fails that contradiction directly with
`status: "reviewed_mujoco_bundle_handoff_blocked_open_work"`,
`downstream_handoff_status: "handoff_blocked_open_work"`,
`ready_handoff_has_open_work: true`,
`ready_handoff_open_work_missing_inputs`,
`ready_handoff_open_work_pending_action_ids`, and
`ready_handoff_open_work_blockers` populated.
The handoff JSON also carries `handoff_open_work_contract_ok` plus a nested
`handoff_open_work_contract` that mirrors those summary-level missing inputs,
pending action IDs, and blockers so downstream consumers can reject drift
between the producer summary and the handoff artifact.
The handoff also carries a priority contract:
`downstream_priority_gate_id: "reviewed_mujoco_handoff"`,
`downstream_priority_gate_order` equal to `mujoco_scene_validity`,
`gymnasium_task_wiring`, and
`reviewed_model_backed_contact_grasp_pick_place`,
`next_downstream_gate_after_ready: "mujoco_scene_validity"`,
`blocks_downstream_gates_until_ready: true`, and
`ready_does_not_imply_policy_training_ready: true`.

The joint-limit comparison converts manifest body-joint limits from degrees to
MuJoCo radians and covers `shoulder_pan`, `shoulder_lift`, `elbow_flex`,
`wrist_flex`, and `wrist_roll`. The gripper is reported as skipped in
`joint_limit_model_consistency` because the manifest uses percent-style command
limits while MuJoCo gripper joints may be slide openings in meters. The SimRobot
motion proof still checks the gripper separately by translating the commanded
percentage through the loaded MuJoCo `gripper` joint range and requiring an
actual before/after qpos delta. Matching range metadata is not enough: the gate
also records `mujoco_joint_limit_enablement` and fails with
`mujoco_joint_limits_enabled` in `missing_inputs` when any SO-101 joint has a
range but MuJoCo reports `jnt_limited` false. If any body
joint's declared bounds differ from the loaded model, the gate reports
`status: "reviewed_mujoco_bundle_motion_failed"` with
`joint_limit_model_consistency` in `missing_inputs`; this prevents a
reviewed-looking manifest from trusting motion evidence for a model with
different configured bounds or non-enforced bounds.

The positive path is covered without hardware by the focused forwarding smoke:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/smoke_sim_so101_bundle_ready_forwarding.py --output-dir /private/tmp/lerobot_sim/so101_bundle_ready_forwarding --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
```

That smoke creates a fixture-only ready MJCF model bundle, verifies the
integrated suite forwards it, and requires this gate to report
`reviewed_mujoco_bundle_motion_checked`. The compatibility field
`reviewed_model_motion_checked` is `true` for that fixture-positive path, but
`motion_authority_status` must be
`hardware_free_fixture_motion_checked_not_physical_so101_authority`,
`hardware_free_fixture_motion_checked` must be `true`, and
`physical_reviewed_model_motion_checked` must remain `false`. The fixture is
automation coverage and must also report
`physical_so101_model_authority_ready: false`; it is not physical SO-101 model
authority.
Ready-shaped manifests whose authority sections still carry pending review
actions or missing review inputs are negative forwarding cases in the same
smoke: they must remain diagnostic-only and must not feed downstream contract,
IK, or reviewed-MuJoCo motion checks.

The focused reviewed-MuJoCo bundle matrix also carries
`generated_reviewed_contract_motion_checked`, a generated contract fixture that
removes synthetic authority flags and exercises the positive
`physical_reviewed_model_motion_checked` branch. That case is branch and schema
coverage only. The matrix summary remains
`model_authority: "reviewed_mujoco_bundle_matrix_not_authority"` and
`observed_evidence_is_physical_so101_authority: false`; the generated fixture is
not a reviewed physical SO-101 asset.

The reviewed MuJoCo bundle matrix also includes generic-review-scope and
per-field weak-authority fixtures. It also includes a ready-shaped manifest
whose authority sections still carry pending review actions or missing review
inputs. Those cases must stay
`reviewed_mujoco_bundle_not_ready`, report the missing review inputs, and avoid
MuJoCo motion. The matrix also covers a manifest target-frame mismatch and a
model file that lacks the manifest target-frame site; both must stay diagnostic
only before motion authority is attempted. It covers a ready-looking manifest
whose declared model path is unavailable, invalid joint-limit payloads such as
non-finite values and lower bounds that are not below upper bounds, and those
must stay not-ready before motion authority is attempted. It also covers
malformed, unavailable, or non-directory `asset_roots` metadata and a
ready-looking manifest whose model still references a mesh that cannot be
resolved from the model directory or declared asset roots; those cases must
report `asset_roots` or `mesh_assets` as the blocker and avoid motion. It also
includes a ready-manifest
negative fixture whose MuJoCo `shoulder_pan` joint keeps the same range but has
`limited="false"`; that case must fail with
`mujoco_joint_limits_enabled` while `joint_limit_model_consistency` still
matches. The matrix also includes a ready-manifest negative fixture whose MuJoCo
`gripper` joint has an effectively immobile qpos range. That case must keep
`ready_for_model_backed_ik: true` from the manifest checker, but the motion gate
must fail with `simrobot_mujoco_joint_motion` because the gripper's before/after
qpos delta is below the required motion threshold. A separate ready-summary
fixture proves that even when MuJoCo and SimRobot motion succeed, non-empty
handoff missing inputs or pending action IDs force
`reviewed_mujoco_bundle_handoff_blocked_open_work` and keep
`downstream_handoff_ready` and
`fixture_handoff_ready_not_physical_so101_authority` false.
The matrix asserts the flattened summary schema and downstream handoff JSON
schema match the current handoff schema and priority contract before later
gates can trust the artifact.

Passing this gate is still not full physical readiness. It proves reviewed-model
handoff into MuJoCo and SimRobot joint motion. Contact-validated gripper
grasp/lift/place physics and board-source pickup with reviewed model-backed IK
remain required before serious policy training.
