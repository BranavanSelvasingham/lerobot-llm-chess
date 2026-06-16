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
- `robot_kinematics_path.status: "urdf_requires_placo"`
- `model_structure_inspection.status: "urdf_contract_visible"`
- `model_structure_inspection.target_frame_present: true`
- `model_structure_inspection.expected_joint_names_missing: []`

That means the XML names line up with the current simulator contract, but the runtime `RobotKinematics` path was not initialized in this environment because `placo` is unavailable. It also does not resolve model-to-sim frame alignment, TCP/gripper-tip offset, base-to-board alignment, collision policy, or source authority.

## Missing Inputs

Before model-backed residuals are trusted, capture these inputs:

- `authoritative_model_asset`: repo-local or explicitly declared SO-101 URDF/MJCF/Xacro source with stable provenance, license, and source authority.
- `model_generation_provenance`: CAD/export source URL or commit, export tool/version, and any local edits.
- `license_and_redistribution_basis`: clear license file or SPDX/header evidence permitting use in this repo.
- `joint_and_frame_alignment`: confirmation that model joints match `shoulder_pan` through `wrist_roll` and target frame `gripper_frame_link` matches simulator expectations.
- `tcp_and_board_alignment`: calibrated gripper-frame/TCP offset plus base-to-board alignment for chess residuals.
- `contract_checker_result`: successful `scripts/smoke_sim_so101_model_contract.py --model-path <candidate>` evidence before `--ik-model-path` is used as more than an explicit fallback diagnostic.
