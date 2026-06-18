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

With no manifest, or with a manifest whose bundle checker does not report
`ready_for_model_backed_ik: true` after checking reviewed joint limits, mesh
evidence, target-frame authority, TCP offset, and base-to-board alignment, the
smoke exits `0` with `status: "reviewed_mujoco_bundle_not_ready"` and
`reviewed_model_motion_checked: false`.

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
`reviewed_mujoco_bundle_motion_checked`. The fixture is automation coverage,
not physical SO-101 model authority.

Passing this gate is still not full physical readiness. It proves reviewed-model
handoff into MuJoCo and SimRobot joint motion. Contact-validated gripper
grasp/lift/place physics and board-source pickup with reviewed model-backed IK
remain required before serious policy training.
