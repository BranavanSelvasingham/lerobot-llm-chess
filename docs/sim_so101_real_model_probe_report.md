# Hardware-Free SO-101 Real Model Probe Report

Date: 2026-06-16

Current checker recheck: 2026-06-18. The candidate remains diagnostic-only and
not ready for model-backed IK.

This report records a hardware-free owner check of the visible local SO-101
model candidates around `/Users/branavan/GitHub/lerobot-chess`. It does not copy
or vendor any URDF, MJCF, or mesh assets into this repository.

## Bottom Line

The readable candidate
`/Users/branavan/GitHub/lerobot-chess/so101_new_calib.urdf` can be turned into a
draft bundle manifest for review. The generated draft is:

`/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_bundle.candidate.json`

It is not a reviewed or model-backed-IK-ready bundle. The standalone manifest
checker reports:

- `status`: `model_bundle_manifest_needs_follow_up`
- `ready_for_model_backed_ik`: `false`
- `missing_inputs`: `authority`, `base_to_board_transform`,
  `joint_limits_deg`, `mesh_assets`, `non_blocking_contract_checker_result`,
  `provenance`, `tcp_offset_m`

No real model-backed IK readiness is claimed here. Do not trust
Cartesian/delta/radial model-backed residuals unless
`scripts/smoke_sim_so101_model_bundle_manifest.py` reports
`ready_for_model_backed_ik: true`.

## Orientation

Initial orientation was from a clean `feat/telemetry-recording` checkout:

```bash
git status --short --branch
```

The work then moved to `codex/so101-real-model-probe-report` for this report.
Branch creation completed, but the local post-checkout hook returned nonzero
because `git-lfs` is not on `PATH`.

The candidate URDF was readable:

```bash
test -r /Users/branavan/GitHub/lerobot-chess/so101_new_calib.urdf && ls -l /Users/branavan/GitHub/lerobot-chess/so101_new_calib.urdf
```

Observed:

- `/Users/branavan/GitHub/lerobot-chess/so101_new_calib.urdf`
- size: `16231` bytes

The local mesh search found no `.stl`, `.dae`, `.obj`, `.glb`, or `.gltf` files
under `/Users/branavan/GitHub/lerobot-chess` to depth 4:

```bash
find /Users/branavan/GitHub/lerobot-chess -maxdepth 4 \( -iname '*.stl' -o -iname '*.dae' -o -iname '*.obj' -o -iname '*.glb' -o -iname '*.gltf' \) -print
```

The URDF itself references `assets/*.stl`, so the sibling checkout root was used
as the only plausible local `--asset-root` for the bundle probe:
`/Users/branavan/GitHub/lerobot-chess`. That root exists, but the expected
`assets/` files were not present.

If this sibling path is not available on another machine, rerun the same checks
with the operator's local model root:

```bash
python3 scripts/smoke_sim_so101_model_source_inventory.py --root /absolute/path/to/lerobot-chess --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_sibling
python3 scripts/smoke_sim_so101_model_bundle_probe.py --model-path /absolute/path/to/lerobot-chess/so101_new_calib.urdf --asset-root /absolute/path/to/lerobot-chess --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_check
python3 scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path /private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_bundle.candidate.json --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_manifest_check
```

## Source Inventory Evidence

Repo-local/default inventory:

```bash
python3 scripts/smoke_sim_so101_model_source_inventory.py --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_default
```

Result:

- `status`: `missing_authoritative_model`
- `candidate_count`: `0`
- `likely_candidate_count`: `0`
- `direct_contract_candidate_count`: `0`
- `authoritative_candidate_count`: `0`
- `summary_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_default/so101_model_source_inventory_summary.json`
- `candidates_csv`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_default/so101_model_source_candidates.csv`

Sibling inventory:

```bash
python3 scripts/smoke_sim_so101_model_source_inventory.py --root /Users/branavan/GitHub/lerobot-chess --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_sibling
```

Result:

- `status`: `missing_authoritative_model`
- `candidate_count`: `4`
- `likely_candidate_count`: `3`
- `direct_contract_candidate_count`: `3`
- `authoritative_candidate_count`: `0`
- `summary_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_sibling/so101_model_source_inventory_summary.json`
- `candidates_csv`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_source_inventory_sibling/so101_model_source_candidates.csv`

Visible sibling candidates:

| Candidate | Relevance | Direct URDF | Authority | Provenance | Notes |
| --- | --- | --- | --- | --- | --- |
| `/Users/branavan/GitHub/lerobot-chess/so101_new_calib.urdf` | `high`, score `180` | `true` | `unverified` | `source_reference_detected`, nearest license file detected | Expected body joints present, `gripper_frame_link` present, Onshape URL detected |
| `/Users/branavan/GitHub/lerobot-chess/archive/so101_kinematics.urdf` | `high`, score `180` | `true` | `unverified` | license context detected | Expected body joints present, `gripper_frame_link` present |
| `/Users/branavan/GitHub/lerobot-chess/so101_new_calib.nomesh.urdf` | `high`, score `180` | `true` | `unverified` | license context detected | Expected body joints present, `gripper_frame_link` present |
| `/Users/branavan/GitHub/lerobot-chess/archive/SO101/so101_new_calib.urdf` | `low`, score `35` | `true` | `unverified` | license context detected | XML parse error in inventory sample |

The top-level `so101_new_calib.urdf` has useful provenance context, including an
Onshape URL and a nearest license file at
`/Users/branavan/GitHub/lerobot-chess/LICENSE`, but it remains untrusted for this
repo because no source authority was declared and no reviewed manifest exists.

## Bundle Probe Evidence

Command:

```bash
python3 scripts/smoke_sim_so101_model_bundle_probe.py --model-path /Users/branavan/GitHub/lerobot-chess/so101_new_calib.urdf --asset-root /Users/branavan/GitHub/lerobot-chess --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_check
```

Result:

- `ok`: `true`
- `status`: `candidate_manifest_needs_review`
- `model_request_status`: `model_supplied`
- `contract_status`: `model_asset_preflight_needs_follow_up`
- `asset_preflight_status`: `asset_preflight_needs_follow_up`
- `manifest_status`: `model_bundle_manifest_needs_follow_up`
- `ready_for_model_backed_ik`: `false`
- `observed_joint_limits_status`: `observed_unreviewed_limits_complete`
- `observed_joint_limits_complete`: `true`
- `mesh_asset_review_status`: `missing_mesh_assets_detected`
- `mesh_asset_review_unique_missing_reference_count`: `13`
- `mesh_asset_review_unique_unresolved_reference_count`: `0`
- `missing_inputs`: `authority`, `base_to_board_transform`,
  `joint_limits_deg`, `mesh_assets`, `non_blocking_contract_checker_result`,
  `provenance`, `tcp_offset_m`
- `summary_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_bundle_probe_summary.json`
- `candidate_manifest_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_bundle.candidate.json`
- `checklist_csv`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_bundle_probe_checklist.csv`

Nested contract/asset artifacts:

- `contract_summary_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_contract/so101_model_contract_summary.json`
- `contract_checklist_csv`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_contract/so101_model_contract_checklist.csv`
- `asset_preflight_summary_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_summary.json`
- `asset_preflight_assets_csv`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_contract/so101_model_asset_preflight/so101_model_asset_preflight_assets.csv`

Structural checks from the contract summary:

- `model_request.status`: `model_supplied`
- `model_structure_inspection.status`: `urdf_contract_visible`
- `model_structure_inspection.root_tag`: `robot`
- expected body joints present: `shoulder_pan`, `shoulder_lift`,
  `elbow_flex`, `wrist_flex`, `wrist_roll`
- expected body joints missing: none
- `target_frame_present`: `true`
- visible links include `base_link`, `gripper_frame_link`, `gripper_link`,
  `lower_arm_link`, `moving_jaw_so101_v1_link`, `shoulder_link`,
  `upper_arm_link`, `wrist_link`

RobotKinematics/placo status from this environment:

- `robot_kinematics_path.status`: `urdf_requires_placo`
- `robot_kinematics_path.placo_available`: `false`
- `robot_kinematics_initialization.status`: `not_attempted`
- initialization reason: asset preflight found a blocker before
  `RobotKinematics` initialization

Mesh asset preflight:

- `mesh_reference_count`: `34`
- `present_asset_count`: `0`
- `missing_asset_count`: `34`
- `unresolved_reference_count`: `0`
- `asset_roots`: `/Users/branavan/GitHub/lerobot-chess`

Unique missing mesh references:

- `assets/base_motor_holder_so101_v1.stl`
- `assets/base_so101_v2.stl`
- `assets/motor_holder_so101_base_v1.stl`
- `assets/motor_holder_so101_wrist_v1.stl`
- `assets/moving_jaw_so101_v1.stl`
- `assets/rotation_pitch_so101_v1.stl`
- `assets/sts3215_03a_no_horn_v1.stl`
- `assets/sts3215_03a_v1.stl`
- `assets/under_arm_so101_v1.stl`
- `assets/upper_arm_so101_v1.stl`
- `assets/waveshare_mounting_plate_so101_v2.stl`
- `assets/wrist_roll_follower_so101_v1.stl`
- `assets/wrist_roll_pitch_so101_v2.stl`

The probe now carries that de-duplicated list under
`mesh_asset_review_missing_references` and keeps it separate from manifest
readiness. These references are review evidence for selecting asset roots; they
do not prove reviewed geometry, collision policy, or model authority.

Observed unreviewed joint limits from the candidate model structure:

| Joint | Observed Lower Deg | Observed Upper Deg |
| --- | ---: | ---: |
| `shoulder_pan` | `-109.99987525598623` | `109.99987525598623` |
| `shoulder_lift` | `-100.00004285756798` | `100.00004285756798` |
| `elbow_flex` | `-96.82986737710912` | `96.82986737710912` |
| `wrist_flex` | `-94.99984017946129` | `94.99984017946129` |
| `wrist_roll` | `-157.21102461697095` | `162.78934171036462` |
| `gripper` | `-10.000004285756797` | `100.00004285756798` |

These values are review evidence only. They are not copied into
`joint_limits_deg`, and they do not create reviewed joint-limit authority.

## Manifest Recheck Evidence

Command:

```bash
python3 scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path /private/tmp/lerobot_sim/so101_real_model_probe_owner_check/so101_model_bundle.candidate.json --output-dir /private/tmp/lerobot_sim/so101_real_model_probe_owner_manifest_check
```

Result:

- `ok`: `true`
- `status`: `model_bundle_manifest_needs_follow_up`
- `ready_for_model_backed_ik`: `false`
- `model_path.status`: `present`
- `asset_roots.status`: `present`
- `authority.status`: `missing`
- `provenance.status`: `missing`
- `joint_limits.status`: `missing`
- `joint_limits.missing_joints`: `shoulder_pan`, `shoulder_lift`,
  `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`
- `target_frame.status`: `present`
- `target_frame.value`: `gripper_frame_link`
- `tcp_offset.status`: `missing`
- `base_to_board_alignment.status`: `placeholder_only`
- `contract_checker.status`: `model_asset_preflight_needs_follow_up`
- `mesh_assets.status`: `needs_follow_up`
- `mesh_assets.mesh_reference_count`: `34`
- `model_asset_preflight.status`: `asset_preflight_needs_follow_up`
- `model_asset_preflight.missing_asset_count`: `34`
- `model_asset_preflight.unresolved_reference_count`: `0`
- `summary_json`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_manifest_check/so101_model_bundle_manifest_summary.json`
- `checklist_csv`:
  `/private/tmp/lerobot_sim/so101_real_model_probe_owner_manifest_check/so101_model_bundle_manifest_checklist.csv`

## Readiness Fields Still Needed

Before this local candidate can become a reviewed bundle manifest, an operator
must supply or review:

- `authority`: source authority status, reviewer, and review date/id.
- `provenance`: source URL/commit/export tool/license basis. The detected
  Onshape URL and sibling `LICENSE` are context, not sufficient authority.
- `joint_limits_deg` or accepted alias: reviewed lower/upper limits for
  `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`,
  and `gripper`.
- Mesh assets/root: a reviewed root that resolves all 34 URDF mesh references,
  or a reviewed no-mesh model with an explicit rationale.
- `tcp_offset_m` or accepted alias: calibrated target-frame to TCP/gripper-tip
  offset as x/y/z meters.
- `base_to_board_transform` or `base_to_board_alignment`: calibrated transform
  from robot base to chess board frame.
- Joint/order and limits review: confirm model joint names, order, axes, and
  limits against simulator expectations.
- Collision and margin policy: define how model-backed low residuals relate to
  execution safety.

After those inputs are filled, rerun:

```bash
python3 scripts/smoke_sim_so101_model_bundle_manifest.py --manifest-path /absolute/path/to/reviewed_so101_model_bundle.json --output-dir /private/tmp/lerobot_sim/so101_reviewed_model_bundle_manifest_check
```

Only if that reports `ready_for_model_backed_ik: true` should the simulator
suite begin treating manifest-mode model-backed IK residuals as readiness
evidence.
