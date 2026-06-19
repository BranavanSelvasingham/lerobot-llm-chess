# SO-101 Model Bundle Manifest Checker

Use this hardware-free checker when a reviewed SO-101 model bundle should drive
future model-backed IK calibration. It verifies that one JSON manifest declares
the kinematic model path, reviewed model-file SHA-256 digest, mesh asset roots,
source authority/provenance, target frame plus reviewed target-frame authority,
reviewed joint-limit authority, TCP/gripper-tip offset, mesh evidence, and
base-to-board alignment inputs before
the simulator treats Cartesian, delta, or radial reachability residuals as
trustworthy.

## Probe/Generator Flow

Use the hardware-free probe when you have a candidate model path and optional
separate mesh roots, but do not yet have a reviewed bundle manifest:

```bash
python scripts/smoke_sim_so101_model_bundle_probe.py --model-path /absolute/path/to/so101.urdf --asset-root /absolute/path/to/assets --output-dir /private/tmp/lerobot_sim/so101_model_bundle_probe
```

The probe accepts repeatable `--asset-root`, optional `--target-frame`, optional
`--python`, and deterministic metadata flags for authority/provenance review
strings. It never copies or imports model assets. It writes:

- `so101_model_bundle.candidate.json`
- `so101_model_bundle_probe_summary.json`
- `so101_model_bundle_probe_checklist.csv`
- `so101_model_bundle_review_packet.json`
- `so101_model_bundle_review_packet.csv`
- `README.md`
- `so101_model_contract/so101_model_contract_summary.json`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_summary.json`
- `so101_model_bundle_manifest_check/so101_model_bundle_manifest_summary.json`

The integrated calibration regression suite also runs this probe under
`so101_model_bundle_probe/` after the model-source inventory. Default CI leaves
the selected model path empty and preserves a no-model candidate manifest
template as review scaffolding; when the inventory recommends a candidate, the
suite forwards that candidate to the probe without upgrading it to reviewed
authority.

The saved probe summary repeats the review-critical fields at top level:
`model_authority`, `model_request_status`, `contract_status`,
`asset_preflight_status`, asset-preflight mesh/present/missing/unresolved
counts, `observed_joint_limits_status`,
`observed_joint_limits_complete`, `observed_joint_limits_deg`,
`observed_joint_limits_missing_joints`, `observed_source_hints_status`,
`observed_source_hints_onshape_urls`,
`observed_source_hints_export_tool_hints`,
`observed_source_hints_license_status`,
`observed_source_hints_license_path`, `observed_source_hints_sha256`,
`mesh_asset_review_status`,
`mesh_asset_review_unique_missing_reference_count`,
`mesh_asset_review_missing_references`,
`mesh_asset_review_unique_unresolved_reference_count`,
`mesh_asset_review_unresolved_references`, `manifest_status`,
`ready_for_model_backed_ik`, `missing_inputs`, `next_required_for_goal`, and
`next_required_action_ids`. These are shortcuts for artifact review only;
readiness is still decided by the nested manifest checker.
The probe also writes a review packet JSON/CSV that groups the same raw
source, joint-limit, mesh, TCP, and board-alignment evidence into ordered
operator review items. The packet always reports
`model_authority: "review_packet_not_authority"` and never copies observed
values into reviewed manifest fields.
Observed source hints, joint limits, and mesh references come from the candidate
model structure and nearby files. They are not copied into `provenance`,
`joint_limits_deg`, or `mesh_asset_authority` unless a reviewer makes them
authoritative.

With no `--model-path`, it still exits `0`, emits a candidate manifest template
with an empty `model_path`, and reports `candidate_model_missing`. With a
nonexistent model path, it exits `0`, preserves the requested path in the draft,
and reports `candidate_model_unavailable`. With a readable URDF/MJCF/Xacro/XML
candidate, it forwards the path and asset roots to the existing SO-101 model
contract checker, which in turn runs the nested asset preflight so mesh
diagnostics match the rest of the simulator gate.

By default the generated candidate manifest leaves `authority` and
`provenance` as empty objects and stores TODO details in
`authority_placeholder` and `provenance_placeholder`. It also writes
`target_frame_authority_placeholder`, `joint_limits_placeholder`,
`tcp_offset_placeholder`, and `base_to_board_alignment_placeholder` instead of
inventing reviewed target-frame authority, limits, calibrated TCP, or
board-alignment values. That means the generated manifest remains
diagnostic-only until an operator replaces those placeholders with reviewed
fields and this checker reports `ready_for_model_backed_ik: true`.
When `--authority-reviewed-by` and `--authority-review-id` or a valid HTTP(S)
`--authority-review-url` are supplied, the probe writes
`authority.source_authority_status: "operator_reviewed"`, which is one of the
manifest checker's accepted reviewed statuses; that still only covers
source-authority metadata and does not make observed model hints, joint limits,
mesh references, TCP offset, or board alignment reviewed truth. `authority`
must include an accepted reviewed status plus reviewer identity and a stable
review artifact handle, and `provenance` must include a source reference,
export tool, and license basis. The manifest must also declare `model_sha256` (or an accepted
alias such as `model_file_sha256`) matching the resolved `model_path` file. A
missing, malformed, or mismatched digest records `model_identity` as not ready
and lists `model_sha256` in `missing_inputs`; this prevents an already-reviewed
path from silently changing contents. The reviewed-authority source/bundle
consistency gate uses this declared digest for authority matching; the observed
file digest is diagnostic evidence only. Provenance values that explicitly name
synthetic, test-only, smoke, hardware-free, or regression-fixture origins are
classified as fixture-only automation evidence; they can keep hardware-free
regression fixtures runnable, but they add `provenance` to
`synthetic_fixture_authority_fields` and keep
`physical_so101_model_authority_ready: false`. A merely non-empty object is
recorded as `needs_review` and does not satisfy readiness. Joint-limit values also need
review evidence: numeric
limits without `joint_limit_authority` or an accepted review marker are recorded
as `needs_review`. Mesh references also need review evidence: resolved mesh
files without `mesh_asset_authority` or an accepted mesh/asset-root review
marker are recorded as `needs_review`. The target frame also needs review
evidence through `target_frame_authority` or an accepted TCP-frame review
marker; otherwise the frame name remains diagnostic only. The current simulator
contract requires `gripper_frame_link`; a reviewed-looking value such as
`not_gripper_frame_link` is invalid for this gate. The reviewed target frame
must also be visible in the actual URDF/MJCF/XML model structure; a manifest can
name `gripper_frame_link` and provide target-frame authority while still
remaining not ready if the model does not expose that link, joint, body, site,
or geom. Numeric TCP offsets and base-to-board transforms also need review
evidence through
`tcp_offset_authority` and `base_to_board_alignment_authority`; otherwise they
remain diagnostic inputs only.

To re-check a generated draft directly:

```bash
python scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path /private/tmp/lerobot_sim/so101_model_bundle_probe/so101_model_bundle.candidate.json --output-dir /private/tmp/lerobot_sim/so101_model_bundle_probe_manifest_review
```

```bash
python scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path /absolute/path/to/so101_model_bundle.json --output-dir /private/tmp/lerobot_sim/so101_model_bundle_manifest
```

The script writes:

- `so101_model_bundle_manifest_summary.json`
- `so101_model_bundle_manifest_checklist.csv`
- `so101_model_bundle_manifest_review_packet.json`
- `so101_model_bundle_manifest_review_packet.csv`
- `README.md`
- `so101_model_contract/so101_model_contract_summary.json`
- `so101_model_contract/so101_model_contract_checklist.csv`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_summary.json`
- `so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_assets.csv`

It exits `0` for actionable diagnostics. With no `--manifest-path`, the summary
reports `status: "model_bundle_manifest_not_supplied"` and lists the required
fields. A nonexistent manifest path reports
`status: "model_bundle_manifest_unavailable"`. Invalid JSON reports
`status: "model_bundle_manifest_parse_error"`. The parser rejects
non-standard JSON constants such as raw `NaN`, `Infinity`, and `-Infinity`;
use quoted diagnostic strings only when a negative fixture intentionally tests
field-level numeric validation.

Every summary also reports `model_authority`,
`physical_authority_gate_status`, `physical_authority_blockers`,
`physical_so101_model_authority_ready`,
`hardware_free_regression_fixture_ready`, and
`synthetic_fixture_authority_fields`. The `model_identity` section records the
declared digest field, observed `model_path` SHA-256, match status, and any
`model_sha256_missing`, `model_sha256_invalid`, or `model_sha256_mismatch`
diagnostics. It also reports
`next_required_for_goal`, an ordered action list derived from the current
`missing_inputs` so the reviewed-model-authority gate has an explicit priority
queue. A manifest can be ready for automation with only synthetic hardware-free
fixture authority, but that readiness is classified as
`hardware_free_regression_fixture_not_physical_so101_authority` and does not
close the reviewed physical SO-101 model-authority gate. When physical
authority is not ready, `physical_authority_blockers` contains the current
reviewed-authority action IDs plus any
`synthetic_fixture_authority_not_physical_so101:<field>` blockers that keep
fixture-ready manifests from being treated as reviewed physical SO-101 truth.

The manifest checker also writes
`so101_model_bundle_manifest_review_packet.json` and `.csv`. This packet is
derived from the current checklist rows and ordered `next_required_for_goal`
actions, so a missing or incomplete manifest has a deterministic operator review
queue. Its `review_action_ids` must match the ordered `next_required_action_ids`
shortcut instead of an alphabetic sort. It always reports
`model_authority: "review_packet_not_authority"`,
`observed_evidence_is_authority: false`, and
`development_fixture_evidence_not_physical_so101_truth: true`; it does not
upgrade diagnostic manifest fields to reviewed SO-101 truth.

Review evidence fields must be actual identifiers, dates, tickets, or URLs.
Placeholder strings such as `TODO`, `TBD`, `unknown`, `placeholder`, or
`review required` are reported as `review_evidence_placeholder` diagnostics and
do not satisfy authority readiness, even when the review status itself is an
accepted value.
The same placeholder rule applies to provenance source, export-tool, and
license-basis fields: a ready-shaped manifest with placeholder provenance stays
`model_bundle_manifest_needs_follow_up` and remains diagnostic-only.
Each authority section reports `review_evidence_required_groups`,
`review_evidence_satisfied_required_groups`, and
`review_evidence_missing_required_groups` in the JSON summary. The
machine-readable group names are `review_actor` for `reviewed_by` and
`review_trace` for `reviewed_at`, `review_id`, or `review_url`. The
`review_artifact` group also requires `review_id` or `review_url`, so a date
alone cannot make a reviewed SO-101 authority section ready. `review_url`
values must be HTTP(S) URLs; use `review_id` for ticket IDs, commit IDs, or
other non-URL artifact handles.

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
Digest mismatches keep readiness false, so a stale reviewed path is not forwarded
as model-backed IK authority.
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
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit"
  },
  "provenance": {
    "source_url": "https://cad.onshape.com/...",
    "source_commit": "optional-export-or-repo-commit",
    "export_tool": "onshape-to-robot",
    "license": "reviewed-license-or-notice"
  },
  "target_frame": "gripper_frame_link",
  "target_frame_authority": {
    "target_frame_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "source": "reviewed model target frame or TCP-frame record"
  },
  "joint_limits_deg": {
    "shoulder_pan": [-110.0, 110.0],
    "shoulder_lift": [-110.0, 110.0],
    "elbow_flex": [-120.0, 120.0],
    "wrist_flex": [-120.0, 120.0],
    "wrist_roll": [-180.0, 180.0],
    "gripper": [0.0, 100.0]
  },
  "joint_limit_authority": {
    "joint_limit_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "source": "reviewed model bundle or calibration record"
  },
  "mesh_asset_authority": {
    "mesh_asset_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "source": "reviewed mesh root or model export"
  },
  "tcp_offset_m": {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0
  },
  "tcp_offset_authority": {
    "tcp_offset_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "source": "reviewed TCP/gripper-tip calibration record"
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
  },
  "base_to_board_alignment_authority": {
    "base_to_board_alignment_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "source": "reviewed board registration or calibration record"
  }
}
```

Accepted TCP aliases are `tcp_offset_m`, `gripper_tip_offset_m`,
`target_frame_to_tcp_m`, and `tool_center_point_offset_m`. Diagnostic output
may use `gripper_frame_link` when `target_frame` is omitted, but readiness
requires an explicit `target_frame` plus accepted reviewed target-frame
authority.

`asset_roots` must be present. An explicit empty list is valid when the model
directory alone resolves mesh paths, but readiness still requires at least one
literal mesh reference visible to asset preflight and resolved with no missing
or unresolved assets, plus reviewed mesh/asset-root authority. Nonexistent roots
are reported as follow-up diagnostics.
Explicit placeholders such as
`base_to_board_alignment_placeholder` or `alignment_placeholders` are recorded,
but they do not make the bundle ready for model-backed IK.

Accepted authority review statuses are `reviewed`, `operator_reviewed`,
`source_reviewed`, `model_bundle_reviewed`, and
`reviewed_so101_model_bundle`. The checker also accepts
`synthetic_fixture_reviewed_for_automation_only` only when the manifest scope
is explicitly hardware-free; that path exists for regression fixtures and is
not physical SO-101 source authority. When any required authority field uses
that fixture-only status, `physical_so101_model_authority_ready` remains
`false` even if `ready_for_model_backed_ik` is `true`; the summary keeps
`physical_authority_gate_status` set to
`hardware_free_fixture_ready_not_physical_authority` and blocker entries for
the synthetic fixture fields. Fixture-only provenance gets the same physical
authority treatment even when the review-status fields themselves are
reviewed-looking. Every reviewed authority section must include reviewer
identity plus a stable artifact handle: `reviewed_by` and `review_id` or
`review_url`. Thin review metadata that supplies only a reviewer identity is
reported as missing `review_trace` and `review_artifact`, and does not satisfy
readiness.

When the integrated calibration regression suite evaluates the reviewed model
authority gate, this manifest is checked against the SO-101 model-source
inventory. The manifest `model_path` must match the selected authoritative
source candidate path before the aggregate reviewed model authority gate can
close. An authoritative source root can help the inventory discover and narrow
that selected candidate, but root containment alone does not authorize a
different bundle model file. This prevents a reviewed source inventory and a
reviewed bundle manifest from silently referring to different SO-101 models.

Provenance must include at least one source field (`source_url`, `source_uri`,
`cad_url`, `repository_url`, `source_path`, or `source_reference`), one export
field (`export_tool`, `exporter`, or `generated_by`), and one license field
(`license`, `license_url`, `license_file`, `license_review`, or
`license_basis`). The probe's observed Onshape/export/license hints are review
inputs only until copied into these reviewed manifest fields.

`joint_limits_deg`, `joint_limits`, or `joint_limit_authority` must be present
as an object covering every expected SO-101 joint with finite numeric bounds:
`shoulder_pan`,
`shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, and `gripper`.
Each entry may be a two-item `[lower, upper]` list or an object with
`lower`/`upper` or `min`/`max` numeric values. The checker also requires
accepted joint-limit review metadata in `joint_limit_authority`,
`joint_limits_review`, `joint_limit_review`, `joint_limits_metadata`, or inside
the joint-limit field itself. Accepted review statuses are `reviewed`,
`operator_reviewed`, `joint_limits_reviewed`, `source_reviewed`, and
`model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle: `review_id` or `review_url`.

Mesh/asset-root authority must be declared in `mesh_asset_authority`,
`mesh_assets_review`, `mesh_asset_review`, or `mesh_assets_metadata`. Accepted
mesh review statuses are `reviewed`, `operator_reviewed`,
`mesh_assets_reviewed`, `source_reviewed`, and `model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle: `review_id` or `review_url`.
Resolved mesh files
without this review metadata remain diagnostic evidence, not reviewed physical
SO-101 mesh truth.

Target-frame authority must be declared in `target_frame_authority`,
`target_frame_review`, `tcp_frame_authority`, or `target_frame_metadata`, and
the manifest `target_frame` must match the current simulator-contract value
`gripper_frame_link`.
Accepted target-frame review statuses are `reviewed`, `operator_reviewed`,
`target_frame_reviewed`, `tcp_frame_reviewed`, and `model_bundle_reviewed`,
plus `synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle: `review_id` or `review_url`. A frame name
without this metadata remains diagnostic evidence, not reviewed physical
SO-101 TCP-frame truth.

TCP/gripper-tip offset authority must be declared in `tcp_offset_authority`,
`tcp_offset_review`, `gripper_tip_offset_review`, or `tcp_calibration`.
Accepted TCP review statuses are `reviewed`, `operator_reviewed`,
`tcp_offset_reviewed`, `tcp_calibration_reviewed`, and
`model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle: `review_id` or `review_url`.
Numeric TCP offsets must be finite; values such as `NaN` or `Infinity`, or
offsets without this metadata, remain diagnostic evidence and are not reviewed
physical SO-101 TCP truth.

Base-to-board alignment authority must be declared in
`base_to_board_alignment_authority`, `base_to_board_authority`,
`base_to_board_alignment_review`, `base_to_board_review`, or
`alignment_calibration`. Accepted alignment review statuses are `reviewed`,
`operator_reviewed`, `base_to_board_reviewed`, `alignment_reviewed`,
`calibration_reviewed`, and `model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle: `review_id` or `review_url`.
The transform value must include finite x/y/z translation and roll/pitch/yaw
rotation fields; a non-empty object without that shape or without review
metadata does not make the bundle ready.

## Readiness Rule

The checker reports `ready_for_model_backed_ik: true` only when all of these are
true:

- the manifest is loaded as a JSON object
- `model_path` exists
- `asset_roots` is present and all supplied roots are directories
- `authority` declares an accepted reviewed status plus traceable review
  evidence (`reviewed_by` plus `review_id` or HTTP(S) `review_url`)
- `provenance` declares source reference, export tool, and license basis fields;
  fixture-only provenance is still non-physical automation evidence
- finite numeric joint limits cover every SO-101 joint and include accepted
  joint-limit review authority
- at least one mesh reference is visible to the asset preflight and all mesh
  references resolve
- mesh/asset-root authority includes an accepted review status plus traceable
  review evidence
- the target frame is explicitly declared and includes accepted target-frame
  review authority
- a valid finite x/y/z TCP offset in meters is present and includes accepted TCP
  review authority
- a real `base_to_board_transform` or `base_to_board_alignment` is populated
  with finite translation/rotation fields and includes accepted alignment
  review authority
- the child SO-101 model contract checker reports `model_contract_checked`, or
  the URDF has the expected static joint/frame contract and the only runtime
  follow-up is missing optional `placo`
- the nested asset preflight has no missing or unresolved mesh references

Any missing input appears in `missing_inputs`, in the CSV checklist, and in the
README. Missing authority, provenance, target-frame authority, TCP, or alignment
data is never treated as success.
Readiness here only proves that reviewed joint limits are declared with the
bundle. The downstream reviewed MuJoCo bundle gate must still load the model and
compare body-joint `joint_limits_deg` against MuJoCo `jnt_range` before motion
evidence is trusted.

## Relationship To Existing Checks

Run the
[SO-101 model-source inventory](sim_so101_model_source_inventory.md) first to
find candidate local model sources and decide which one is authoritative after
license/provenance review. The manifest checker does not scan roots or infer
authority from `--ik-model-path`; it consumes the reviewed result as a single
declared bundle.

Current local hardware-free evidence for the visible sibling SO-101 candidate is
recorded in the
[SO-101 real model probe report](sim_so101_real_model_probe_report.md).

The probe/generator sits between the inventory and the reviewed manifest. Use
the inventory to find likely local model files, use the probe to turn a selected
candidate plus separate mesh roots into a reviewed-manifest draft with contract
and asset-preflight diagnostics, then fill authority, provenance, target-frame
authority, TCP, and base-to-board values before relying on the manifest checker
for readiness.

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
