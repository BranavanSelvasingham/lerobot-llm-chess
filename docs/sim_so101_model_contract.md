# SO-101 Model Contract Checker

Use this hardware-free checker after a candidate SO-101 model source has been
inventoried and asset-preflighted, but before passing any path to simulator
model-backed IK through `--ik-model-path`.

```bash
python scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

The checker writes:

- `so101_model_contract_summary.json`
- `so101_model_contract_checklist.csv`
- `README.md`
- `so101_model_asset_preflight/so101_model_asset_preflight_summary.json`
- `so101_model_asset_preflight/so101_model_asset_preflight_assets.csv`
- `so101_model_asset_preflight/README.md`

It exits `0` for actionable diagnostics. No supplied model reports
`status: "missing_model"`. A missing supplied path reports
`status: "model_unavailable"`. A supplied model with missing mesh assets
reports `status: "model_asset_preflight_needs_follow_up"` and records the child
asset preflight counts/artifact paths before `RobotKinematics` initialization is
attempted.

## Review Order

Run the source inventory first:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --root /absolute/path/to/model/source --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_external
```

Then run the focused asset preflight if you need standalone mesh evidence:

```bash
python scripts/smoke_sim_so101_model_asset_preflight.py --model-path /absolute/path/to/so101.urdf --asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/so101_model_asset_preflight
```

The contract checker also runs that asset preflight as a child diagnostic under
its own output directory whenever it is invoked. Use the contract checker output
as the final gate before forwarding a reviewed model path to a later
`--ik-model-path` run.

## Artifact Fields

High-signal JSON fields:

- `status`
- `model_request.status`
- `model_asset_preflight.status`
- `model_asset_preflight.mesh_reference_count`
- `model_asset_preflight.present_asset_count`
- `model_asset_preflight.missing_asset_count`
- `model_asset_preflight.unresolved_reference_count`
- `model_asset_preflight.artifacts.summary_json`
- `model_asset_preflight.artifacts.assets_csv`
- `robot_kinematics_path.status`
- `robot_kinematics_initialization.status`
- `artifacts.summary_json`
- `artifacts.checklist_csv`

Missing or unresolved mesh assets are a contract blocker, not a failing smoke
test. The checker records them as evidence and skips optional
`RobotKinematics` initialization so the first reported cause is the asset
preflight result rather than a later placo mesh-loading exception.
