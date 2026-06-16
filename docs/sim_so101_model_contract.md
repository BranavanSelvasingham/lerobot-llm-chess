# SO-101 Model Contract Checker

Use this hardware-free checker after a candidate SO-101 model source has been
inventoried and asset-preflighted, but before passing any path to simulator
model-backed IK through `--ik-model-path`.

```bash
python scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

When a reviewed URDF/MJCF source references meshes from a separate directory,
pair it with repeatable asset roots:

```bash
python scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --model-asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

`--model-path` names the candidate model file being inspected. It is the path
that may later become `--ik-model-path` for model-backed IK. `--model-asset-root`
is only mesh-resolution context forwarded to the nested asset preflight as
`--asset-root`; it is repeatable, diagnostic, and never passed into
`RobotKinematics`. Source authority still comes from the inventory
`--so101-authoritative-model-path` or `--so101-authoritative-model-root`
options after provenance/license review.

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
- `model_asset_root_configuration.asset_roots`
- `model_asset_root_configuration.asset_root_checks`
- `model_asset_preflight.status`
- `model_asset_preflight.asset_roots`
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

When the full simulator calibration regression suite runs this checker, it
mirrors `model_asset_preflight` into the suite summary and indexes the nested
summary/CSV/README as `so101_model_asset_preflight` artifacts. The rendered
artifact report shows this section before IK reachability with mesh, present,
missing, and unresolved counts.

The full suite equivalent is:

```bash
python scripts/smoke_sim_calibration_regression_suite.py --ik-model-path /absolute/path/to/so101.urdf --ik-model-asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_model
```

The suite records those roots in `so101_model_contract_config`, mirrors the
contract checker's `model_asset_root_configuration`, and preserves the child
command under `child_commands.so101_model_contract.command`.

For reviewed model-backed IK readiness, collect the model path, asset roots,
authority/provenance, target-frame/TCP offset, and base-to-board alignment in a
[SO-101 model bundle manifest](sim_so101_model_bundle_manifest.md). The bundle
manifest checker wraps this contract checker and its nested asset preflight, but
does not replace source inventory review or make `--ik-model-path`
authoritative by itself.
