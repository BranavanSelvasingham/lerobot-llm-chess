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
`model_authority: "downstream_handoff_not_authority"`,
`observed_evidence_is_authority: false`, and
`physical_so101_truth_claimed: false`. Its `downstream_handoff_ready` flag is
true only when physical reviewed model authority and MuJoCo/SimRobot motion are
both true; fixture-positive runs instead report
`fixture_handoff_ready_not_physical_so101_authority: true`.
Downstream consumers must also reject any raw-ready or fixture-ready handoff
that still carries non-empty `missing_inputs`, `next_required_for_goal`, or
`next_required_action_ids`. A ready-shaped handoff with open work is
contradictory and cannot unblock scene, Gymnasium, pick/place, or training
readiness gates.

The joint-limit comparison converts manifest body-joint limits from degrees to
MuJoCo radians and covers `shoulder_pan`, `shoulder_lift`, `elbow_flex`,
`wrist_flex`, and `wrist_roll`. The gripper is reported as skipped in
`joint_limit_model_consistency` because the manifest uses percent-style command
limits while MuJoCo gripper joints may be slide openings in meters. The SimRobot
motion proof still checks the gripper separately by translating the commanded
percentage through the loaded MuJoCo `gripper` joint range and requiring an
actual before/after qpos delta. If any body
joint's declared bounds differ from the loaded model, the gate reports
`status: "reviewed_mujoco_bundle_motion_failed"` with
`joint_limit_model_consistency` in `missing_inputs`; this prevents a
reviewed-looking manifest from trusting motion evidence for a model with
different configured bounds.

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
negative fixture whose MuJoCo
`gripper` joint has an effectively immobile qpos range. That case must keep
`ready_for_model_backed_ik: true` from the manifest checker, but the motion gate
must fail with `simrobot_mujoco_joint_motion` because the gripper's before/after
qpos delta is below the required motion threshold.

Passing this gate is still not full physical readiness. It proves reviewed-model
handoff into MuJoCo and SimRobot joint motion. Contact-validated gripper
grasp/lift/place physics and board-source pickup with reviewed model-backed IK
remain required before serious policy training.
