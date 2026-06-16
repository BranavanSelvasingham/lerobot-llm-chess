# SO-101 Model Bundle Manifest Checker

Use this hardware-free checker when a reviewed SO-101 model bundle should drive
future model-backed IK calibration. It verifies that one JSON manifest declares
the kinematic model path, mesh asset roots, source authority/provenance, target
frame, TCP/gripper-tip offset, and base-to-board alignment inputs before the
simulator treats Cartesian, delta, or radial reachability residuals as
trustworthy.

```bash
python scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path /absolute/path/to/so101_model_bundle.json --output-dir /private/tmp/lerobot_sim/so101_model_bundle_manifest
```

The script writes:

- `so101_model_bundle_manifest_summary.json`
- `so101_model_bundle_manifest_checklist.csv`
- `README.md`
- `so101_model_contract/so101_model_contract_summary.json`
- `so101_model_contract/so101_model_contract_checklist.csv`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_summary.json`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_assets.csv`

It exits `0` for actionable diagnostics. With no `--manifest-path`, the summary
reports `status: "model_bundle_manifest_not_supplied"` and lists the required
fields. A nonexistent manifest path reports
`status: "model_bundle_manifest_unavailable"`. Invalid JSON reports
`status: "model_bundle_manifest_parse_error"`.

## Integrated Suite Mode

The hardware-free simulator calibration regression suite runs this checker on
every invocation. With no suite manifest option, it records no-manifest evidence
under `so101_model_bundle_manifest/` without changing the existing fallback IK
behavior:

```bash
python scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite --python "$(python -c 'import sys; print(sys.executable)')"
```

To supply a reviewed bundle to the suite, pass:

```bash
python scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_bundle --python "$(python -c 'import sys; print(sys.executable)')" --so101-model-bundle-manifest /absolute/path/to/so101_model_bundle.json
```

The suite exposes the checker output under
`calibration_regression_summary.json.so101_model_bundle_manifest`,
indexes it in `artifact_index.json` as the
`so101_model_bundle_manifest` category, and renders it in
`artifact_index_report.md`. If `ready_for_model_backed_ik` is false, the
manifest stays diagnostic-only. If readiness is true and no explicit
`--ik-model-path` was supplied, the suite may derive the downstream model path
for the contract checker and IK reachability drill from `manifest.model_path`.
If no explicit `--ik-model-asset-root` values were supplied, the suite also
forwards manifest `asset_roots` to the contract checker's nested asset
preflight. Explicit suite CLI values take precedence and the forwarding reason
is recorded in `so101_model_bundle_manifest.forwarding`.

## Manifest Shape

The manifest is JSON only. Relative `model_path` and `asset_roots` values are
resolved from the manifest directory.

```json
{
  "model_path": "so101.urdf",
  "asset_roots": ["assets"],
  "authority": {
    "source_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16"
  },
  "provenance": {
    "source_url": "https://cad.onshape.com/...",
    "source_commit": "optional-export-or-repo-commit",
    "export_tool": "onshape-to-robot",
    "license": "reviewed-license-or-notice"
  },
  "target_frame": "gripper_frame_link",
  "tcp_offset_m": {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0
  },
  "base_to_board_transform": {
    "translation_m": {
      "x": 0.0,
      "y": 0.0,
      "z": 0.0
    },
    "rotation_rpy_rad": {
      "roll": 0.0,
      "pitch": 0.0,
      "yaw": 0.0
    }
  }
}
```

Accepted TCP aliases are `tcp_offset_m`, `gripper_tip_offset_m`,
`target_frame_to_tcp_m`, and `tool_center_point_offset_m`. Omitted
`target_frame` defaults to `gripper_frame_link`.

`asset_roots` must be present. An explicit empty list is valid when the model
directory alone resolves mesh paths, but nonexistent roots are reported as
follow-up diagnostics. Explicit placeholders such as
`base_to_board_alignment_placeholder` or `alignment_placeholders` are recorded,
but they do not make the bundle ready for model-backed IK.

## Readiness Rule

The checker reports `ready_for_model_backed_ik: true` only when all of these are
true:

- the manifest is loaded as a JSON object
- `model_path` exists
- `asset_roots` is present and all supplied roots are directories
- non-empty `authority` and `provenance` objects are present
- the target frame is present or defaulted
- a valid x/y/z TCP offset in meters is present
- a real `base_to_board_transform` or `base_to_board_alignment` is populated
- the child SO-101 model contract checker reports `model_contract_checked`
- the nested asset preflight has no missing or unresolved mesh references

Any missing input appears in `missing_inputs`, in the CSV checklist, and in the
README. Missing authority, provenance, TCP, or alignment data is never treated
as success.

## Relationship To Existing Checks

Run the
[SO-101 model-source inventory](sim_so101_model_source_inventory.md) first to
find candidate local model sources and decide which one is authoritative after
license/provenance review. The manifest checker does not scan roots or infer
authority from `--ik-model-path`; it consumes the reviewed result as a single
declared bundle.

The manifest checker invokes the
[SO-101 model contract checker](sim_so101_model_contract.md) as a child whenever
`model_path` is supplied. It forwards every manifest `asset_roots` entry as a
repeatable `--model-asset-root`, so the contract checker's nested
[asset preflight](sim_so101_model_asset_preflight.md) records mesh reference
diagnostics in the same output tree.

Only after the bundle manifest is ready should the same reviewed model path be
treated as more than diagnostic evidence. The manifest does not change
`RobotKinematics`, the IK solver, robot execution, camera/UI flows, or
LLM/OpenAI paths; it is evidence that the inputs required to interpret future
model-backed IK residuals have been declared together. In integrated suite mode,
a ready bundle can also supply the reviewed model path to the source inventory
as a root/authoritative path when no explicit source-inventory options were
passed; otherwise `--so101-model-source-root`,
`--so101-model-source-extra-root`, `--so101-authoritative-model-path`, and
`--so101-authoritative-model-root` keep precedence.
