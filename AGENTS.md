# Project Automation Instructions

Always try to validate work and results. If output cannot be seen or evaluated
directly, state that gap clearly so access can be improved.

Keep responses concise whenever possible without losing signal.

## Current Objective And Goal

Prioritize the MuJoCo-based SO-101 chess robot simulation path before serious
policy training. Treat Unity, Unreal, and Blender as optional asset,
visualization, or review tools; they should not replace the MuJoCo/Gymnasium
training path unless the project explicitly changes direction.

The active goal is to complete and refine the missing simulation gates in order:
reviewed SO-101 model authority, MuJoCo scene validity, Gymnasium task wiring,
scripted contact/grasp/pick/place evidence, and only then focused training
rollouts. Missing items should be treated as priority work until they have
repeatable validation artifacts.

## Priority Order

1. Make the MuJoCo and Gymnasium simulation stack runnable and repeatably
   testable.
2. Validate a reviewed SO-101 URDF/MJCF model bundle with mesh roots, joint
   limits, target frame, TCP/gripper offset, and base-to-board alignment.
3. Load the reviewed robot model in MuJoCo and prove SO-101 joint motion without
   fallback behavior.
4. Build and validate the chess board and piece scene with collisions, resets,
   and artifact evidence.
5. Expose the SO-101 chess task as a Gymnasium training environment.
6. Prove scripted pick/place behavior in simulation, including contact,
   grasp/lift/place, and release evidence before trusting policy rollouts.
7. Begin focused training tasks only after the model, scene, resets, and
   contact/grasp evidence are explicit and repeatable.

Development scaffolds are allowed to keep progress moving, but they must remain
clearly marked as not reviewed physical SO-101 truth.
