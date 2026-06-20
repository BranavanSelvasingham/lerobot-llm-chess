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
missing, malformed, mismatched, or contradictory digest aliases record
`model_identity` as not ready and list `model_sha256` in `missing_inputs`; this
prevents an already-reviewed path from silently changing contents. If multiple
digest aliases such as `model_sha256`, `model_file_sha256`, `model_digest`, or
`model_file_digest` are present, they must normalize to the same SHA-256 value.
The reviewed-authority source/bundle consistency gate uses this declared digest
for authority matching; the observed file digest is diagnostic evidence only.
Provenance values that explicitly name
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
or geom. The static model contract also rejects unexpected model joints: the
candidate model may expose the expected SO-101 body joints plus the simulator
gripper joint, but unrelated extra joint names keep the contract checker
blocking until the model structure is reviewed. Numeric TCP offsets and
base-to-board transforms must be finite and also need review evidence through
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
- `so101_model_bundle_manifest_review_requirements.json`
- `so101_model_bundle_manifest_review_requirements.csv`
- `so101_model_bundle_manifest_template.json`
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
field-level numeric validation. The focused manifest matrix keeps these as
separate boundaries: raw constants must fail at parse time, while quoted
non-finite calibration values must fail the TCP or base-to-board field checks.

Every summary also reports `model_authority`,
`physical_authority_gate_status`, `physical_authority_blockers`,
`physical_so101_model_authority_ready`,
`hardware_free_regression_fixture_ready`, and
`synthetic_fixture_authority_fields`. It also reports
`physical_authority_contract`, a compact contract object with `ok`, `status`,
`ready_for_model_backed_ik`, physical-ready, fixture-ready, blocker, and
synthetic-fixture fields. This object is the quickest machine-readable check
for whether the manifest is physically authoritative, fixture-ready only, or
still blocked. Ready synthetic fixture manifests must report
`status: "fixture_ready_not_physical_authority"` and
`fixture_ready_not_physical_so101_authority: true`; only a ready manifest with
no synthetic fixture fields may report `status: "physical_authority_ready"`.
The `model_identity` section records the
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

The checker also writes `so101_model_bundle_manifest_template.json`, a wrapper
with a copyable nested `manifest_template` object for the required reviewed
model path, SHA-256 digest, provenance, review scopes, mesh roots, joint
limits, target frame, TCP offset, and base-to-board alignment fields. It always
reports `model_authority: "reviewed_manifest_template_not_authority"`, false
observed-evidence and physical-truth flags, and placeholder caveats. Edit a
copy of the nested template, replace every placeholder with reviewed inputs,
then rerun this checker; the template artifact itself is never reviewed
physical SO-101 authority.

Each `so101_model_bundle_manifest_intake_checklist` action also carries
field-check context for the missing input that triggered it:
`related_requirement_ids`, `field_check_diagnostics`, and
`field_check_context`. These fields make the operator queue auditable by
linking an action such as `record_tcp_offset_authority` or
`clear_model_contract_and_asset_preflight` back to the failing manifest
requirement and exact diagnostics. They remain checklist context only and do
not make observed manifest data reviewed physical SO-101 truth.

The checker also writes `so101_model_bundle_manifest_review_requirements.json`
and `.csv`. These files are a machine-readable review map for the manifest
authority gate: required review sections, manifest fields, accepted review
statuses, review scopes, evidence groups, placeholder rejection policy, URL
field policy, and the handoff to child model contract and asset-preflight
checks. The URL policy is repeated on the provenance requirement: fields such
as `source_url`, `repository_url`, `cad_url`, and `license_url` must be
HTTP(S), while local paths, commit IDs, tickets, or other non-URL handles
belong in `source_path` or `source_reference`. They always report
`model_authority: "review_requirements_not_authority"` and are operator intake
guidance only; they do not make a manifest reviewed physical SO-101 truth.

Review evidence fields must be actual identifiers, dates, tickets, or URLs.
Placeholder strings such as `TODO`, `TBD`, `unknown`, `placeholder`,
`review required`, or unedited template tokens like `<reviewer-or-team>` are
reported as `review_evidence_placeholder` diagnostics and do not satisfy
authority readiness, even when the review status itself is an accepted value.
The same placeholder rule applies to provenance source, export-tool, and
license-basis fields: a ready-shaped manifest with placeholder provenance stays
`model_bundle_manifest_needs_follow_up` and remains diagnostic-only. Provenance
fields that are explicitly URL-shaped, such as `source_url`, `repository_url`,
`cad_url`, or `license_url`, must contain HTTP(S) URLs; use `source_path` or
`source_reference` for local/non-URL source handles.
Each authority section reports `review_evidence_required_groups`,
`review_evidence_satisfied_required_groups`, and
`review_evidence_missing_required_groups` in the JSON summary. It also reports
`review_evidence_open_work_fields` and
`review_evidence_ready_has_open_work` when a reviewed-looking authority object
still carries follow-up work. The
machine-readable group names are `review_actor` for `reviewed_by` and
`review_trace` for `reviewed_at`, `review_id`, or `review_url`. The
`review_artifact` group also requires `review_id` or `review_url`, so a date
alone cannot make a reviewed SO-101 authority section ready. `review_url`
values must be HTTP(S) URLs; use `review_id` for ticket IDs, commit IDs, or
other non-URL artifact handles. If supplied, `reviewed_at` must be an ISO
`YYYY-MM-DD` date or ISO datetime and must not be in the future; malformed or
future-dated review timestamps are invalid review evidence. Review authority
objects that still carry
non-empty `missing_inputs`, `next_required_for_goal`,
`next_required_action_ids`, `pending_action_ids`, blockers, or open findings
are also rejected. Those fields mean the review packet itself is still
incomplete, even if the status string says `reviewed`.

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
resolved from the manifest directory. `model_path` must resolve to an existing
file with a supported robot-model suffix (`.urdf`, `.xml`, `.mjcf`, or
`.xacro`). A matching SHA-256 digest on another file type is still rejected as
`model_path.status: "unsupported_suffix"` and cannot become model-backed IK
evidence.

```json
{
  "model_path": "so101.urdf",
  "asset_roots": ["assets"],
  "authority": {
    "source_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "review_scopes": ["model_identity", "provenance", "license"]
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
    "review_scope": "target_frame",
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
    "review_scope": "joint_limits",
    "source": "reviewed model bundle or calibration record"
  },
  "mesh_asset_authority": {
    "mesh_asset_authority_status": "reviewed",
    "reviewed_by": "operator-or-review-id",
    "reviewed_at": "2026-06-16",
    "review_id": "review-ticket-or-commit",
    "review_scope": "mesh_assets",
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
    "review_scope": "tcp_offset",
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
    "review_scope": "base_to_board_alignment",
    "source": "reviewed board registration or calibration record"
  }
}
```

Accepted base-to-board alignment aliases are `base_to_board_transform` and
`base_to_board_alignment`. If both are present, every non-empty alias must
resolve to the same finite translation and roll/pitch/yaw rotation. Within an
alignment transform, accepted translation aliases are `translation_m`,
`translation`, and `position_m`; accepted rotation aliases are
`rotation_rpy_rad`, `rotation_rpy`, and `rpy_rad`. Rotation values must be
finite roll/pitch/yaw radians with each absolute component at or below `2*pi`.
Conflicting top-level or nested alignment aliases are not readiness evidence.

Accepted TCP aliases are `tcp_offset_m`, `gripper_tip_offset_m`,
`target_frame_to_tcp_m`, and `tool_center_point_offset_m`. If more than one
alias is present, every non-empty alias must resolve to the same finite vector
in meters; conflicting aliases are not readiness evidence. Diagnostic output may
use `gripper_frame_link` when `target_frame` is omitted, but readiness requires
an explicit `target_frame` plus accepted reviewed target-frame authority.

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
`review_url`. It must also include explicit `review_scope` or `review_scopes`
values covering the field being authorized. The top-level `authority` block
requires `model_identity`, `provenance`, and `license`; section authorities
require `joint_limits`, `mesh_assets`, `target_frame`, `tcp_offset`, or
`base_to_board_alignment` as appropriate. Thin review metadata that supplies
only a reviewer identity is reported as missing `review_trace` and
`review_artifact`, and generic review scope metadata is reported through
`missing_review_scope_ids`; neither satisfies readiness.

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
Unexpected joint-limit entries are rejected; the reviewed limit map must match
the expected SO-101 joint set instead of carrying extra stale or non-SO-101
joint names.
Each entry may be a two-item `[lower, upper]` list or an object with
`lower`/`upper` or `min`/`max` numeric values. Bounds must be finite and the
lower value must be strictly below the upper value. If more than one joint-limit
alias is present, every non-empty alias must normalize to the same finite,
ordered per-joint bounds. If `joint_limit_authority` embeds nested limit values,
accepted nested aliases are `joint_limits_deg`, `joint_limits`, `limits_deg`,
and `limits`; those nested aliases must also agree. Conflicting joint-limit
aliases are not readiness evidence. The checker also requires
accepted joint-limit review metadata in `joint_limit_authority`,
`joint_limits_review`, `joint_limit_review`, `joint_limits_metadata`, or inside
the joint-limit field itself. Accepted review statuses are `reviewed`,
`operator_reviewed`, `joint_limits_reviewed`, `source_reviewed`, and
`model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle (`review_id` or `review_url`) and the
`joint_limits` review scope.

Mesh/asset-root authority must be declared in `mesh_asset_authority`,
`mesh_assets_review`, `mesh_asset_review`, or `mesh_assets_metadata`. Accepted
mesh review statuses are `reviewed`, `operator_reviewed`,
`mesh_assets_reviewed`, `source_reviewed`, and `model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle (`review_id` or `review_url`) and the
`mesh_assets` review scope. If more than one mesh/asset-root review alias is
present, every supplied alias must be independently ready; an ignored secondary
alias that still says follow-up is required keeps the manifest out of the
reviewed-ready path.
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
plus a stable artifact handle (`review_id` or `review_url`) and the
`target_frame` review scope. If more than one target-frame review alias is
present, every supplied alias must be independently ready. A frame name without
this metadata remains diagnostic evidence, not reviewed physical SO-101
TCP-frame truth.

TCP/gripper-tip offset authority must be declared in `tcp_offset_authority`,
`tcp_offset_review`, `gripper_tip_offset_review`, or `tcp_calibration`.
Accepted TCP review statuses are `reviewed`, `operator_reviewed`,
`tcp_offset_reviewed`, `tcp_calibration_reviewed`, and
`model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle (`review_id` or `review_url`) and the
`tcp_offset` review scope. If more than one TCP/gripper-tip review alias is
present, every supplied alias must be independently ready.
Numeric TCP offsets must be finite; values such as `NaN` or `Infinity`, or
offsets without this metadata, remain diagnostic evidence and are not reviewed
physical SO-101 TCP truth. The checker also applies a conservative automation
sanity bound: the TCP/gripper-tip offset vector norm must be no more than
`0.50 m`, otherwise the manifest remains not ready and reports
`tcp_offset_norm_exceeds_limit`.

Base-to-board alignment authority must be declared in
`base_to_board_alignment_authority`, `base_to_board_authority`,
`base_to_board_alignment_review`, `base_to_board_review`, or
`alignment_calibration`. Accepted alignment review statuses are `reviewed`,
`operator_reviewed`, `base_to_board_reviewed`, `alignment_reviewed`,
`calibration_reviewed`, and `model_bundle_reviewed`, plus
`synthetic_fixture_reviewed_for_automation_only` only for explicitly
hardware-free regression fixtures. Review evidence must include `reviewed_by`
plus a stable artifact handle (`review_id` or `review_url`) and the
`base_to_board_alignment` review scope. If more than one base-to-board review
alias is present, every supplied alias must be independently ready.
The transform value must include finite x/y/z translation and roll/pitch/yaw
rotation fields; the x/y/z translation norm must be no more than `2.00 m` under
the current tabletop chess automation sanity bound. A non-empty object without
that shape, outside that broad bound, or without review metadata does not make
the bundle ready.

## Readiness Rule

The checker reports `ready_for_model_backed_ik: true` only when all of these are
true:

- the manifest is loaded as a JSON object
- `model_path` exists
- `asset_roots` is present and all supplied roots are directories
- `authority` declares an accepted reviewed status plus traceable review
  evidence (`reviewed_by` plus `review_id` or HTTP(S) `review_url`) and no
  open review-work fields
- `provenance` declares source reference, export tool, and license basis fields;
  fixture-only provenance is still non-physical automation evidence
- finite numeric joint limits cover every SO-101 joint and include accepted
  joint-limit review authority with no open review work
- at least one mesh reference is visible to the asset preflight and all mesh
  references resolve
- mesh/asset-root authority includes an accepted review status plus traceable
  review evidence and no open review work
- the target frame is explicitly declared and includes accepted target-frame
  review authority with no open review work
- a valid finite x/y/z TCP offset in meters is present, stays within the broad
  automation sanity bound, and includes accepted TCP review authority with no
  open review work
- a real `base_to_board_transform` or `base_to_board_alignment` is populated
  with finite translation/rotation fields, stays within the broad automation
  sanity bound, and includes accepted alignment review authority with no open
  review work
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
only a bundle that is both model-backed-IK ready and
`physical_so101_model_authority_ready: true` can supply the reviewed model path
to the source inventory as a root/authoritative path when no explicit
source-inventory options were passed. Hardware-free fixture-ready bundles can
still feed contract/IK regression, but the source-inventory forwarding record
must stay diagnostic-only with `used_for_source_inventory: false`; otherwise
`--so101-model-source-root`,
`--so101-model-source-extra-root`, `--so101-authoritative-model-path`, and
`--so101-authoritative-model-root` keep precedence.
