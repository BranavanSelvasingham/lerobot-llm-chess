# SO-101 Chess Gymnasium Environment

Use this hardware-free smoke as the first training-facing gate for the MuJoCo
SO-101 chess path:

```bash
python scripts/smoke_sim_so101_chess_env.py --output-dir /private/tmp/lerobot_sim/so101_chess_env
```

The script writes:

- `so101_chess_env_summary.json`
- `so101_chess_env_steps.csv`
- `README.md`

The summary exposes `gymnasium_task_wiring_status`,
`mujoco_backend_required`, `mujoco_backend_loaded`,
`joint_state_fallback_active`, `gymnasium_api_contract`,
`ready_for_policy_training`, and
`training_authority_status` so fallback, development-MuJoCo, and failed required
backend modes are distinguishable in CI. The smoke fails closed when the
environment configuration is invalid or when the scripted pick/place episode
does not complete inside the configured step budget.
Runnable cases also record the Gymnasium-facing action and observation contract:
a six-value `float32` action space for the SO-101 controlled joints,
observation-space keys, reset/final observation keys, shapes, dtypes, and any
missing or mismatched fields.

By default the smoke accepts the existing joint-state fallback and records
whether Gymnasium and MuJoCo are importable. To require a real MuJoCo backend,
pass a reviewed model path and require MuJoCo:

```bash
python scripts/smoke_sim_so101_chess_env.py \
  --mujoco-model-path /absolute/path/to/so101.xml \
  --require-gymnasium \
  --require-mujoco \
  --output-dir /private/tmp/lerobot_sim/so101_chess_env_mujoco
```

The environment entrypoint is `lerobot.sim.chess_env.SO101ChessEnv`. It exposes
Gymnasium-style `reset()` and `step()` methods, a normalized six-joint action
space when Gymnasium is installed, and observations containing joint positions,
source/target square coordinates, piece state, phase index, and whether MuJoCo
actually loaded.

Current limitations are explicit in the summary:

- The default mode is joint-state fallback when no reviewed MuJoCo model is supplied.
- The chess board and piece contact model is symbolic until the reviewed MuJoCo
  robot/world scene is added.
- The scripted pick/place policy is a deterministic joint-space scaffold, not
  calibrated IK or contact-validated manipulation.
- `ready_for_policy_training` remains `false` until reviewed model authority,
  reviewed model-backed board-source pick/place, and reviewed rollouts are all
  available.

For focused contract coverage, run:

```bash
python scripts/smoke_sim_so101_chess_env_matrix.py --output-dir /private/tmp/lerobot_sim/so101_chess_env_matrix
```

The matrix writes `so101_chess_env_matrix_summary.json`,
`so101_chess_env_matrix_cases.csv`, and `README.md`. It proves joint-state
fallback can remain explicit and non-training, `--require-mujoco` fails closed
without a model path or with an invalid model path, invalid max-step
configuration writes fail-closed artifacts, too-short scripted episodes fail
instead of reporting a green env smoke, and a generated development MJCF can
drive the Gymnasium task without becoming reviewed SO-101 truth. The matrix also
checks the development scene fixture contract: no reviewed MuJoCo handoff is
requested or consumed, physical SO-101 authority stays false, and policy/model
readiness stays false. All runnable matrix cases must keep the six-action
Gymnasium API contract valid, while invalid task configuration remains
fail-closed before an environment contract is created.

This is the bridge between the existing calibration/model-readiness evidence
and later policy training. It should become a hard MuJoCo gate after the SO-101
model bundle manifest reports `ready_for_model_backed_ik: true` and the robot,
board, piece, TCP, and base-to-board alignment are loaded into the same scene.

Before that reviewed bundle exists, use
[docs/sim_so101_mujoco_scene.md](sim_so101_mujoco_scene.md) to generate and
validate the explicit development-only MJCF scene. That gate proves MuJoCo model
loading, six-joint synchronization, board/piece collision geometry, and this
environment's scripted pick/place loop without claiming physical SO-101 model
authority.
