# SO-101 Model Asset Preflight

Use this hardware-free preflight after a candidate SO-101 model source has been
identified, but before trusting `RobotKinematics` initialization or
model-backed IK residuals. It checks whether mesh assets referenced by the model
are actually available from the model directory and any explicitly supplied
asset roots.

```bash
python scripts/smoke_sim_so101_model_asset_preflight.py --model-path /absolute/path/to/so101.urdf --asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/so101_model_asset_preflight
```

The script writes:

- `so101_model_asset_preflight_summary.json`
- `so101_model_asset_preflight_assets.csv`
- `README.md`

It exits `0` for actionable diagnostics. No supplied model reports
`status: "missing_model"` with `model_request.status: "model_not_supplied"`.
A missing supplied path reports `status: "model_unavailable"`. A URDF with
missing mesh dependencies reports
`status: "asset_preflight_needs_follow_up"` and lists missing rows under
`missing_assets`.

## Scope

For `.urdf` files, the preflight parses XML `<mesh filename="...">`
references. It checks:

- absolute paths directly
- `file://` paths as local filesystem paths
- relative paths below the model directory and each repeated `--asset-root`
- simple `package://` and `model://` path forms below the model directory and
  supplied asset roots

The script does not perform ROS package lookup, xacro expansion, MJCF include
resolution, Gazebo model lookup, network access, or asset copying. For `.xml`,
`.mjcf`, and `.xacro`, it emits limited static diagnostics and only checks
literal mesh attributes visible in the file.

`--asset-root` is mesh-resolution context only. It lets a reviewed model file
live separately from STL/DAE/OBJ assets, but it does not make the model source
authoritative, does not copy assets into the repo, and does not change
`RobotKinematics` behavior.

## Review Order

Run the source inventory first:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --root /absolute/path/to/model/source --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_external
```

Then run this asset preflight on the selected candidate when standalone mesh
evidence is useful. The
[SO-101 model contract checker](sim_so101_model_contract.md) also runs this
preflight as a child diagnostic under its own output directory. Only after the
model source and mesh assets are present should the model contract checker be
treated as a gate for `--ik-model-path`:

```bash
python scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

If the URDF/MJCF source and meshes live in separate reviewed locations, pass
the same roots through the contract checker:

```bash
python scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --model-asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

Do not treat `--ik-model-path` results as authoritative until the source
inventory, asset preflight, and contract checker have all produced reviewed
evidence. The known blocker class is a URDF that looks structurally compatible
with the simulator contract, but cannot enter model-backed IK because a
referenced mesh such as `assets/base_motor_holder_so101_v1.stl` is missing.

## Artifact Fields

High-signal JSON fields:

- `status`
- `model_request.status`
- `asset_roots`
- `model_asset_inspection.scan_mode`
- `mesh_reference_count`
- `present_asset_count`
- `missing_asset_count`
- `unresolved_reference_count`
- `missing_assets`
- `artifacts.summary_json`
- `artifacts.assets_csv`

The CSV is row-level evidence for each discovered mesh reference. A synthetic
URDF with one present mesh and one missing mesh should produce one
`resolution_status: "present"` row and one `resolution_status: "missing"` row.

## Full Suite Surface

The full simulator calibration regression suite does not rerun separate asset
preflight work. It surfaces the model contract checker's nested
`model_asset_preflight` block under
`calibration_regression_summary.json.so101_model_contract.model_asset_preflight`
and indexes the child summary/CSV/README in the
`so101_model_asset_preflight` artifact category. In
`artifact_index_report.md`, this category appears before IK reachability so
missing mesh/assets are visible before model-backed residual evidence.

Use the suite-level `--ik-model-asset-root` option to forward repeatable asset
roots into that nested preflight:

```bash
python scripts/smoke_sim_calibration_regression_suite.py --ik-model-path /absolute/path/to/so101.urdf --ik-model-asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_model
```

The suite records the exact roots in
`so101_model_contract_config.ik_model_asset_roots`,
`so101_model_contract.model_asset_root_configuration`, and
`so101_model_contract.model_asset_preflight.asset_roots`.
