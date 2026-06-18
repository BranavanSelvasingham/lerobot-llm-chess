# SO-101 Model Source Inventory

Use this hardware-free inventory before trusting model-backed SO-101 simulator IK residuals. It scans configurable local roots for `.urdf`, `.xacro`, `.xml`, and `.mjcf` files, classifies likely SO-101 relevance, records whether a candidate is directly usable by the current `RobotKinematics`/placo URDF path, and separates provenance/license evidence from explicit source authority.

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory
```

The script writes:

- `so101_model_source_inventory_summary.json`
- `so101_model_source_candidates.csv`
- `so101_model_source_inventory_review_packet.json`
- `so101_model_source_inventory_review_packet.csv`
- `so101_model_source_intake_checklist.json`
- `so101_model_source_intake_checklist.csv`
- `README.md`

It exits `0` even when no candidates exist. In that state the JSON reports `ok: true`, `status: "missing_authoritative_model"`, `candidate_count: 0`, `authoritative_candidate_count: 0`, `source_authority_gate_status: "source_authority_blocked_missing_authoritative_model"`, a `source_authority_blockers` list for the missing source-authority work, a `missing_authoritative_model` diagnostic listing the source inputs still required, and `next_required_for_goal`/`next_required_action_ids` entries that keep the operator sequence explicit.
The review packet mirrors that operator sequence with `review_packet_status`,
`review_packet_model_authority: "review_packet_not_authority"`,
`review_packet_item_count`, `review_packet_action_ids`, and false
`review_packet_observed_evidence_is_authority` /
`review_packet_physical_so101_model_authority_ready` flags. It is intake for
human review; it does not make candidate filenames, joint names, provenance
hints, or local fixture evidence reviewed physical SO-101 truth.
The source-intake checklist is narrower: it records the scanned roots, missing
source-authority review fields/scopes, `source_intake_status`,
`source_intake_action_ids`, and command templates for the current
`next_required_action_ids`. It reports
`source_intake_model_authority: "source_intake_not_authority"` plus false
observed-evidence and physical-authority flags, so it remains operator guidance
rather than reviewed SO-101 model authority.

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
dependencies, and authority have been reviewed. When an authoritative path/root
is declared, also pass `--so101-source-authority-license-basis`, every required
`--so101-source-authority-review-scope` value (`model_identity`, `provenance`,
and `license`), `--so101-source-authority-reviewed-by`, plus at least one
trace field: `--so101-source-authority-reviewed-at`,
`--so101-source-authority-review-id`, or
`--so101-source-authority-review-url`. Without those metadata fields the
inventory can report an authoritative candidate, but it also reports
`source_authority_review_status: "review_metadata_missing"` and queues
`record_source_authority_review_metadata`. The summary keeps
`source_authority_gate_status` as one of
`source_authority_blocked_missing_authoritative_model`,
`source_authority_blocked_ambiguous_authoritative_model`,
`source_authority_blocked_review_metadata`, or `source_authority_ready`, and
keeps `source_authority_blockers` empty only when exactly one authoritative
candidate and non-placeholder source-authority review metadata are both present.
If an authoritative root matches multiple model files, the inventory reports
`status: "ambiguous_authoritative_model"`,
`authoritative_source_selection_status: "multiple_authoritative_candidates"`,
and queues `select_single_authoritative_so101_model_source` rather than
implicitly choosing one.

Review evidence must be non-placeholder metadata. Values such as `TODO`, `TBD`,
`unknown`, `placeholder`, or `review required` are preserved in the summary as
`review_evidence_placeholder_fields`, but they keep
`source_authority_review_ready: false` and do not satisfy source-authority
readiness. A non-placeholder reviewer identity alone is also insufficient; the
inventory reports `review_evidence_required_groups`,
`review_evidence_satisfied_required_groups`, and
`review_evidence_missing_required_groups`, and blocks thin metadata as
`authority_review_evidence:review_trace` until `reviewed_at`, `review_id`, or
`review_url` is supplied. The inventory also reports
`source_authority_review_scope_ready`,
`source_authority_required_review_scope_ids`,
`source_authority_supplied_review_scope_ids`, and
`source_authority_missing_review_scope_ids` so a generic reviewer token cannot
close source authority without explicit review scope coverage.

Supplying an empty reviewed root or authority root is still a non-failing
diagnostic: the suite should report `missing_authoritative_model`,
`candidate_count: 0`, and `authoritative_candidate_count: 0` rather than
inventing a model. The suite preserves the configured values under
`calibration_regression_summary.json.so101_model_source_inventory.source_configuration`,
mirrors them in `so101_model_source_inventory_config`, writes the exact forwarded
child command under `child_commands.so101_model_source_inventory.command`, and
surfaces them in the generated artifact index/report, including the source
authority gate status and blocker list.

After selecting a candidate model source, run the focused
[SO-101 model asset preflight](sim_so101_model_asset_preflight.md) before the
[SO-101 model contract checker](sim_so101_model_contract.md). The contract
checker also runs asset preflight as a child diagnostic, so its JSON and README
carry the same missing-mesh counts and child artifact paths. The asset preflight
records missing URDF mesh dependencies such as
`assets/base_motor_holder_so101_v1.stl` without importing or copying external
assets, and keeps `package://` / `model://` diagnostics explicitly
filesystem-only rather than pretending ROS package resolution exists.

When a candidate has been reviewed, record the reviewed model path, asset roots,
authority/provenance, TCP offset, and base-to-board alignment together in a
[SO-101 model bundle manifest](sim_so101_model_bundle_manifest.md). The bundle
manifest checker consumes that reviewed declaration and reruns the contract
checker with forwarded asset roots before any later `--ik-model-path` result is
treated as model-backed IK readiness evidence.

## Scope

By default the inventory scans repo-local roots: `models/`, `assets/`, `SO101/`, `src/`, `docs/`, `archive/`, `data/`, and the repo root. Missing roots are reported as roots with `exists: false`; they are not errors.

To inspect an external or installed model location without importing assets:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --root /absolute/path/to/model/root --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_external
```

Use `--authoritative-path` or `--authoritative-root` only after the model source,
license, and authority have been reviewed. Pair them with
`--authority-license-basis`, all three required `--authority-review-scope`
values (`model_identity`, `provenance`, and `license`),
`--authority-reviewed-by`, and at least one trace field:
`--authority-reviewed-at`, `--authority-review-id`, or
`--authority-review-url` so the artifact distinguishes a bare
authoritative-path declaration from a reviewed source-authority declaration.
Without authoritative flags, a SO-101-looking file remains
`source_authority_status: "unverified"` and does not count as authoritative.
Without complete review metadata and scope coverage, an authoritative candidate
remains explicit but reports `source_authority_review_ready: false`.

## Source Authority Matrix Smoke

Use the matrix smoke when changing source-authority logic or workflow checks:

```bash
python scripts/smoke_sim_so101_source_authority_matrix.py --output-dir /private/tmp/lerobot_sim/so101_source_authority_matrix --python python
```

The smoke generates synthetic URDF fixtures under the output directory and runs
the inventory through eight non-hardware cases: missing source root, unverified
candidate, authoritative path without review metadata, authoritative path with
placeholder review metadata, authoritative path with reviewer-only thin review
metadata, authoritative path with complete source-review metadata, single
authoritative root with complete source-review metadata, and ambiguous
authoritative root. It writes:

- `so101_source_authority_matrix_summary.json`
- `so101_source_authority_matrix_cases.csv`
- `README.md`

The complete-source-review fixture must reach
`source_authority_gate_status: "source_authority_ready"` and
`source_intake_status: "source_authority_ready_waiting_for_bundle_manifest"`.
The single-root ready fixture must resolve to the same
`selected_authoritative_candidate_path` as the explicit authoritative-path
fixture and expose the selected candidate SHA-256; those model identity fields
are later compared against the reviewed bundle manifest.
The ambiguous-root fixture must remain
`source_authority_blocked_ambiguous_authoritative_model` and queue
`select_single_authoritative_so101_model_source`. Every matrix case keeps
`source_intake_model_authority: "source_intake_not_authority"`,
`review_packet_model_authority: "review_packet_not_authority"`, and false
physical SO-101 authority flags; the smoke proves the inventory state machine,
not a reviewed robot model.

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
- `source_authority_gate_status: "source_authority_blocked_missing_authoritative_model"`
- `source_authority_blockers: ["scan_or_supply_so101_model_source_root", "review_and_declare_authoritative_so101_model_source"]`
- `source_authority_review_scope_ready: false`
- `source_authority_missing_review_scope_ids: ["model_identity", "provenance", "license"]`
- `artifacts.summary_json: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_inventory_summary.json`
- `artifacts.candidates_csv: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_candidates.csv`
- `artifacts.review_packet_json: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_inventory_review_packet.json`
- `artifacts.review_packet_csv: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_inventory_review_packet.csv`
- `artifacts.source_intake_checklist_json: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_intake_checklist.json`
- `artifacts.source_intake_checklist_csv: /private/tmp/lerobot_sim/so101_model_source_inventory_owner_check/so101_model_source_intake_checklist.csv`

Empty-root validation:

```bash
python scripts/smoke_sim_so101_model_source_inventory.py --root /private/tmp/lerobot_sim/empty_model_inventory_root --output-dir /private/tmp/lerobot_sim/so101_model_source_inventory_empty_root_check
```

Key fields are also `ok: true`, `status: "missing_authoritative_model"`, `candidate_count: 0`, and `authoritative_candidate_count: 0`, proving the no-candidate diagnostic is non-failing.

A separate local probe of `/Users/branavan/GitHub/lerobot-chess` found four URDF-path candidates, including three likely SO-101 URDFs. They remain untrusted for this repo because `authoritative_candidate_count: 0`: the files are outside this repo, that sibling checkout ignores `*.urdf`, and no explicit source-authority marker was supplied. One full URDF has an `onshape-to-robot`/Onshape export header and a nearest license file, but that is provenance context, not enough to trust it as the simulator's authoritative model source.

## Contract Checker Handoff

Only forward a candidate to `--ik-model-path` after the inventory reports an
authoritative candidate, asset preflight has no missing or unresolved mesh
references, and the focused contract checker has been run:

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
- `single_authoritative_model_asset`: exactly one reviewed model file selected with `--authoritative-path`, or an authoritative root narrowed so it resolves to a single reviewed model file.
- `model_generation_provenance`: CAD/export source URL or commit, export tool/version, and any local edits.
- `license_and_redistribution_basis`: clear license file or SPDX/header evidence permitting use in this repo.
- `joint_and_frame_alignment`: confirmation that model joints match `shoulder_pan` through `wrist_roll` and target frame `gripper_frame_link` matches simulator expectations.
- `tcp_and_board_alignment`: calibrated gripper-frame/TCP offset plus base-to-board alignment for chess residuals.
- `contract_checker_result`: successful `scripts/smoke_sim_so101_model_contract.py --model-path <candidate>` evidence before `--ik-model-path` is used as more than an explicit fallback diagnostic.
