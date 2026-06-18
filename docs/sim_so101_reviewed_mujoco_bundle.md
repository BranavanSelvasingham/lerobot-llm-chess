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
- `README.md`

The summary carries the manifest checker's `model_authority`,
`physical_so101_model_authority_ready`,
`hardware_free_regression_fixture_ready`, and
`synthetic_fixture_authority_fields` fields. A hardware-free synthetic fixture
may exercise the positive MuJoCo motion path, but it stays labeled as
`hardware_free_regression_fixture_not_physical_so101_authority`. Motion evidence
also carries `motion_authority_status`,
`physical_reviewed_model_motion_checked`,
`hardware_free_fixture_motion_checked`, and
`motion_evidence_not_physical_so101_authority` so fixture-only motion cannot be
mistaken for reviewed physical SO-101 authority.

With no manifest, or with a manifest whose bundle checker does not report
`ready_for_model_backed_ik: true` after checking reviewed joint limits, mesh
evidence, target-frame authority, TCP offset, and base-to-board alignment, the
smoke exits `0` with `status: "reviewed_mujoco_bundle_not_ready"` and
`reviewed_model_motion_checked: false`. In that not-ready state,
`motion_authority_status` is `not_checked_manifest_not_ready`, and all motion
authority booleans are `false`.

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
- instantiate `SimRobot` with the reviewed model path
- verify the MuJoCo backend has no joint-state fallback
- send a deterministic joint action and confirm mapped qpos motion

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

Passing this gate is still not full physical readiness. It proves reviewed-model
handoff into MuJoCo and SimRobot joint motion. Contact-validated gripper
grasp/lift/place physics and board-source pickup with reviewed model-backed IK
remain required before serious policy training.
