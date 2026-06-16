# SO-101 Model Source Inventory

Use this hardware-free inventory before trusting model-backed SO-101 simulator IK residuals. It scans configurable local roots for `.urdf`, `.xacro`, `.xml`, and `.mjcf` files, classifies likely SO-101 relevance, records whether a candidate is directly usable by the current `RobotKinematics`/placo URDF path, and separates provenance/license evidence from explicit source authority.

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory
```

The script writes:

- `so101_model_source_inventory_summary.json`
- `so101_model_source_candidates.csv`
- `README.md`

It exits `0` even when no candidates exist. In that state the JSON reports `ok: true`, `status: "missing_authoritative_model"`, `candidate_count: 0`, `authoritative_candidate_count: 0`, and a `missing_authoritative_model` diagnostic listing the source inputs still required.

The full hardware-free simulator calibration regression suite now runs this
inventory automatically under `so101_model_source_inventory/` before
`smoke_sim_so101_model_contract.py` and `smoke_sim_ik_reachability_drill.py`.
That integrated default scan is repo-local. A suite `--ik-model-path` value is
forwarded only to the contract checker and IK drill; it is not treated as an
authoritative inventory source.

The integrated suite exposes the same reviewed-source concepts with explicit
suite-level names:

- `--so101-model-source-root` maps to inventory `--root` and replaces default
  inventory roots. Repeat it for multiple reviewed scan roots.
- `--so101-model-source-extra-root` maps to inventory `--extra-root` and keeps
  the default repo-local scan roots. Repeat it for multiple appended roots.
- `--so101-authoritative-model-path` maps to inventory `--authoritative-path`.
- `--so101-authoritative-model-root` maps to inventory `--authoritative-root`.

Use the authoritative flags only after source provenance, license, mesh
dependencies, and authority have been reviewed. Supplying an empty reviewed root
or authority root is still a non-failing diagnostic: the suite should report
`missing_authoritative_model`, `candidate_count: 0`, and
`authoritative_candidate_count: 0` rather than inventing a model. The suite
preserves the configured values under
`calibration_regression_summary.json.so101_model_source_inventory.source_configuration`,
mirrors them in `so101_model_source_inventory_config`, writes the exact forwarded
child command under `child_commands.so101_model_source_inventory.command`, and
surfaces them in the generated artifact index/report.

After selecting a candidate model source, run the focused
[SO-101 model asset preflight](sim_so101_model_asset_preflight.md) before the
model contract checker. The asset preflight records missing URDF mesh
dependencies such as `assets/base_motor_holder_so101_v1.stl` without importing
or copying external assets, and keeps `package://` / `model://` diagnostics
explicitly filesystem-only rather than pretending ROS package resolution exists.

## Scope

By default the inventory scans repo-local roots: `models/`, `assets/`, `SO101/`, `src/`, `docs/`, `archive/`, `data/`, and the repo root. Missing roots are reported as roots with `exists: false`; they are not errors.

To inspect an external or installed model location without importing assets:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --root /absolute/path/to/model/root --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_external
```

Use `--authoritative-path` or `--authoritative-root` only after the model source, license, and authority have been reviewed. Without those flags, a SO-101-looking file remains `source_authority_status: "unverified"` and does not count as authoritative.

## Owner Check Evidence

Default repo-root validation for this PR:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check
```

Key fields:

- `ok: true`
- `status: "missing_authoritative_model"`
- `candidate_count: 0`
- `authoritative_candidate_count: 0`
- `artifacts.summary_json: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_inventory_summary.json`
- `artifacts.candidates_csv: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_candidates.csv`

Empty-root validation:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --root /private/tmp/lerobot_sim/empty_model_inventory_root --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_empty_root_check
```

Key fields are also `ok: true`, `status: "missing_authoritative_model"`, `candidate_count: 0`, and `authoritative_candidate_count: 0`, proving the no-candidate diagnostic is non-failing.

A separate local probe of `/Users/branavan/GitHub/lerobot-chess` found four URDF-path candidates, including three likely SO-101 URDFs. They remain untrusted for this repo because `authoritative_candidate_count: 0`: the files are outside this repo, that sibling checkout ignores `*.urdf`, and no explicit source-authority marker was supplied. One full URDF has an `onshape-to-robot`/Onshape export header and a nearest license file, but that is provenance context, not enough to trust it as the simulator's authoritative model source.

## Contract Checker Handoff

Only forward a candidate to `--ik-model-path` after the inventory reports an authoritative candidate and the focused contract checker has been run:

```bash
python scripts/smoke_sim_so101_model_contract.py --model-path /absolute/path/to/so101.urdf --output-dir /private/tmp/lerobot_sim/so101_model_contract_preflight_model
```

Then pass the same reviewed path through the calibration regression suite:

```bash
python scripts/smoke_sim_calibration_regression_suite.py --output-dir /private/tmp/lerobot_sim/calibration_regression_suite_model --include-negative-check --ik-model-path /absolute/path/to/so101.urdf
```

For the local sibling URDF probe, the existing contract checker reported:

- `ok: true`
- `status: "model_contract_needs_follow_up"`
- `model_request.status: "model_supplied"`
- `robot_kinematics_path.status: "directly_usable"`
- `robot_kinematics_path.placo_available: true`
- `robot_kinematics_initialization.status: "initialization_failed"`
- `robot_kinematics_initialization.reason: "ValueError: Mesh assets/base_motor_holder_so101_v1.stl could not be found."`
- `model_structure_inspection.status: "urdf_contract_visible"`
- `model_structure_inspection.target_frame_present: true`
- `model_structure_inspection.expected_joint_names_missing: []`

That means the URDF path is directly compatible with the current `RobotKinematics`/placo code path in this environment, and the XML names line up with the current simulator contract. Runtime initialization still fails because referenced mesh assets are missing from the candidate root, so the candidate remains untrusted and model-backed IK residuals still cannot be treated as authoritative. It also does not resolve model-to-sim frame alignment, TCP/gripper-tip offset, base-to-board alignment, collision policy, or source authority.

## Missing Inputs

Before model-backed residuals are trusted, capture these inputs:

- `authoritative_model_asset`: repo-local or explicitly declared SO-101 URDF/MJCF/Xacro source with stable provenance, license, and source authority.
- `model_generation_provenance`: CAD/export source URL or commit, export tool/version, and any local edits.
- `license_and_redistribution_basis`: clear license file or SPDX/header evidence permitting use in this repo.
- `joint_and_frame_alignment`: confirmation that model joints match `shoulder_pan` through `wrist_roll` and target frame `gripper_frame_link` matches simulator expectations.
- `tcp_and_board_alignment`: calibrated gripper-frame/TCP offset plus base-to-board alignment for chess residuals.
- `contract_checker_result`: successful `scripts/smoke_sim_so101_model_contract.py --model-path <candidate>` evidence before `--ik-model-path` is used as more than an explicit fallback diagnostic.
