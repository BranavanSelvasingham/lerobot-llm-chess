# SO-101 Chess Env Reset Smoke

Use this smoke to validate per-episode source/target resets in strict MuJoCo
mode:

```bash
python scripts/smoke_sim_so101_env_resets.py --output-dir /private/tmp/lerobot_sim/so101_env_resets
```

The script writes:

- `so101_env_resets_summary.json`
- `so101_env_resets.csv`
- `so101_env_reset_invalid_cases.csv`
- `so101_chess_development.xml`
- `so101_chess_development_manifest.json`
- `README.md`

The smoke checks both explicit reset tasks and sampled reset tasks. Each reset
must start at phase zero, place the symbolic piece on the reset source square,
clear the holding flag, keep MuJoCo active with no fallback, and accept a first
expert action after reset.

The smoke also rejects invalid reset requests for malformed tasks, invalid
source squares, invalid target squares, identical source/target squares, and
sampled resets without a task pool. Each rejected case must record the
`ValueError` and then prove the environment can recover with a valid reset.

The generated MJCF remains `development_scaffold_not_reviewed` and
`ready_for_model_backed_ik: false`. The summary must also keep
`observed_evidence_is_physical_so101_authority: false`,
`observed_evidence_is_policy_training_authority: false`,
`development_fixture_evidence_not_physical_so101_truth: true`,
`development_fixture_evidence_not_policy_training_truth: true`, and
`ready_for_policy_training: false`. This smoke proves training-style reset
plumbing, not reviewed robot geometry or contact-validated manipulation.
