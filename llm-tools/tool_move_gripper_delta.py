from __future__ import annotations

import math
import time
from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from llm_toolkit import KinematicsTools


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "move_gripper_delta",
        "description": (
            "Move end-effector using a base-centric POLAR interface:\n"
            "- dx_mm = delta radius (mm): +dx moves farther from base\n"
            "- dtheta_deg (optional) = delta angle around base (degrees, CCW)\n"
            "- dy_mm (legacy) = tangential arc length (mm) if dtheta_deg not provided\n"
            "- dz_mm = vertical delta (mm): +dz means UP\n"
            "- z_m / z_mm (optional) = absolute Z target (base frame). If provided, dz_mm is ignored."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "dx_mm": {"type": "number"},
                "dy_mm": {"type": "number"},
                "dz_mm": {"type": "number"},
                "dtheta_deg": {"type": "number"},
                "z_m": {"type": "number"},
                "z_mm": {"type": "number"},
                "use_commanded_base": {"type": "boolean"},
            },
            "required": ["dx_mm", "dy_mm", "dz_mm"],
            "additionalProperties": False,
        },
    }


def execute(tools: "KinematicsTools", args: dict[str, Any]) -> dict[str, Any]:
    """Polar-ish delta tool (dr, dtheta, dz or z_abs) around robot base."""

    with tools._lock:
        tools._require_kin()
        _SO101_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]

        # Measured EE pose (for orientation + sanity checks)
        T_meas = tools.get_ee_pose()
        p_meas = T_meas[:3, 3].astype(float)  # meters

        use_commanded_base = bool(args.get("use_commanded_base", True))
        p_cmd = getattr(tools, "_ee_cmd_xyz_m", None)
        cmd_meas_gap = float("inf")
        if isinstance(p_cmd, np.ndarray) and p_cmd.shape == (3,) and np.all(np.isfinite(p_cmd)):
            cmd_meas_gap = float(np.linalg.norm(p_cmd - p_meas))

        # Use commanded base only if it's close to measured (robot actually reached it).
        # 20mm tolerance - if gap is larger, the robot didn't reach the target.
        if use_commanded_base and cmd_meas_gap < 0.020:
            p_base = p_cmd.astype(float)
            base_source = "commanded"
        else:
            # Reset to measured - either no commanded reference or robot didn't reach it.
            p_base = p_meas.astype(float)
            base_source = "measured"
            if cmd_meas_gap < float("inf"):
                base_source = f"measured (gap={cmd_meas_gap*1000:.1f}mm)"
            try:
                tools._ee_cmd_xyz_m = None  # type: ignore[attr-defined]
            except Exception:
                pass

        x0, y0, z0 = float(p_base[0]), float(p_base[1]), float(p_base[2])
        r0 = float(math.hypot(x0, y0))
        theta0 = float(math.atan2(y0, x0))

        dr_mm = float(np.clip(float(args.get("dx_mm", 0.0)), -200.0, 200.0))
        dy_mm = float(np.clip(float(args.get("dy_mm", 0.0)), -200.0, 200.0))
        dz_sem_mm = float(np.clip(float(args.get("dz_mm", 0.0)), -200.0, 200.0))

        dtheta_deg = args.get("dtheta_deg", None)
        if dtheta_deg is not None:
            dtheta_rad = float(math.radians(float(dtheta_deg)))
            tangential_mm = float((r0 * 1000.0) * dtheta_rad)
        else:
            # Legacy: dy_mm is arc length along the current circle.
            dtheta_rad = float((dy_mm / 1000.0) / r0) if r0 > 1e-6 else 0.0
            tangential_mm = float(dy_mm)

        r1 = max(0.0, r0 + (dr_mm / 1000.0))
        theta1 = theta0 + dtheta_rad
        x1 = float(r1 * math.cos(theta1))
        y1 = float(r1 * math.sin(theta1))

        z_abs_m = args.get("z_m", None)
        if z_abs_m is None and args.get("z_mm", None) is not None:
            z_abs_m = float(args.get("z_mm")) / 1000.0

        if z_abs_m is not None:
            z1 = float(z_abs_m)
            z_requested = True
            dz_kin_mm = 0.0
        else:
            dz_kin_mm = dz_sem_mm * float(tools.dz_to_kinematics_sign)
            z1 = float(z0 + (dz_kin_mm / 1000.0))
            z_requested = abs(dz_sem_mm) > 1e-9

        xyz_target = np.array([x1, y1, z1], dtype=float)
        xyz_target_requested = xyz_target.copy()

        # Clamp only the axes we actually asked to change.
        clamp_mask = np.array(
            [
                abs(dr_mm) > 1e-9 or abs(dtheta_rad) > 1e-12,
                abs(dr_mm) > 1e-9 or abs(dtheta_rad) > 1e-12,
                bool(z_requested),
            ],
            dtype=bool,
        )

        # Keep orientation fixed to current measured orientation.
        R_fixed = T_meas[:3, :3].astype(float)

        # -----------------------------
        # Lift planning (IK-friendly)
        # -----------------------------
        # Pure "lift straight up" at a large reach can be IK/torque-unfriendly.
        # If the user asks for an upward lift without planar motion, we try a small
        # retract-toward-base (while still lifting) to find an IK-feasible target.
        lift_plan: dict[str, Any] = {"used": False}
        planar_requested = bool(abs(dr_mm) > 1e-9 or abs(dtheta_rad) > 1e-12)
        lift_up_requested = bool(
            z_requested
            and (
                (z_abs_m is not None and z1 > z0)
                or (z_abs_m is None and dz_sem_mm > 1e-9)
            )
        )
        if lift_up_requested and not planar_requested:
            try:
                q_seed_dict = tools._read_joints_deg(_SO101_JOINTS)
                q_seed = np.array([q_seed_dict[j] for j in _SO101_JOINTS], dtype=float)

                candidates: list[dict[str, Any]] = []
                r_xy = float(math.hypot(float(x1), float(y1)))
                for retract_mm in (0.0, 20.0, 40.0, 60.0):
                    if r_xy > 1e-6:
                        r_new = max(0.0, r_xy - (float(retract_mm) / 1000.0))
                        scale = r_new / r_xy
                        x_c = float(x1 * scale)
                        y_c = float(y1 * scale)
                    else:
                        x_c, y_c = float(x1), float(y1)

                    xyz_c = np.array([x_c, y_c, float(z1)], dtype=float)
                    T_c = np.eye(4, dtype=float)
                    T_c[:3, :3] = R_fixed
                    T_c[:3, 3] = xyz_c

                    _q_sol, xyz_ach = tools._ik_to_targets(
                        T_target=T_c, q_seed_deg=q_seed, position_only=True
                    )
                    err_m = float(np.linalg.norm(xyz_ach - xyz_c))
                    candidates.append(
                        {
                            "retract_mm": float(retract_mm),
                            "ik_err_mm": float(err_m * 1000.0),
                            "xyz_m": xyz_c,
                        }
                    )

                # Choose the smallest retract that is IK-feasible, else the best available.
                tol_mm = 10.0
                chosen: dict[str, Any] | None = None
                for c in candidates:
                    if float(c["ik_err_mm"]) <= tol_mm:
                        chosen = c
                        break
                if chosen is None:
                    chosen = min(candidates, key=lambda c: float(c["ik_err_mm"]))

                lift_plan = {
                    "used": bool(float(chosen["retract_mm"]) > 0.0),
                    "retract_mm": float(chosen["retract_mm"]),
                    "tol_mm": float(tol_mm),
                    "candidates": [
                        {"retract_mm": float(c["retract_mm"]), "ik_err_mm": float(c["ik_err_mm"])}
                        for c in candidates
                    ],
                }
                xyz_target = np.array(chosen["xyz_m"], dtype=float).reshape(3)
            except Exception as e:
                lift_plan = {"used": False, "error": str(e)}

        # IMPORTANT: Do not include gripper in delta EE moves.
        # Otherwise a move can "hold" the gripper at a stale readback value,
        # fighting a prior set_gripper_percent command that hasn't settled yet.
        g = None

        # No clamping - workspace bounds were causing Z drift
        no_clamp = np.array([False, False, False], dtype=bool)

        # Direct move with full IK
        result = tools._move_ee_to(
            xyz_m=xyz_target,
            R_fixed=R_fixed,
            gripper_pos=g,
            position_only=True,
            clamp_mask=no_clamp,
        )

        # --- Drift correction loop ---
        # After main move, check position error and correct if needed
        max_corrections = 3
        correction_threshold_mm = 5.0  # Only correct if error > 5mm
        corrections_done = 0
        correction_results: list[dict[str, Any]] = []

        for _ in range(max_corrections):
            # Read current position
            kin = tools._require_kin()
            q_now = tools._read_joints_deg(_SO101_JOINTS)
            q_arr = np.array([q_now[j] for j in _SO101_JOINTS], dtype=float)
            T_now = kin.forward_kinematics(q_arr)
            xyz_now = T_now[:3, 3].astype(float)

            # Compute error from target
            error_vec = xyz_target - xyz_now
            error_mm = float(np.linalg.norm(error_vec) * 1000.0)

            if error_mm < correction_threshold_mm:
                break  # Close enough, no correction needed

            # Do a correction move toward the target
            correction_result = tools._move_ee_to(
                xyz_m=xyz_target,
                R_fixed=R_fixed,
                gripper_pos=g,
                position_only=True,
                clamp_mask=no_clamp,
            )
            correction_result["correction_num"] = corrections_done + 1
            correction_result["error_before_mm"] = error_mm
            try:
                xyz_after = np.array(correction_result.get("ee_after_m", xyz_now.tolist()), dtype=float).reshape(3)
                correction_result["error_after_mm"] = float(
                    np.linalg.norm(xyz_target - xyz_after) * 1000.0
                )
            except Exception:
                correction_result["error_after_mm"] = None
            correction_results.append(correction_result)
            corrections_done += 1
            # Stop if we didn't meaningfully improve (prevents oscillation/thrashing).
            try:
                error_after_mm = correction_result.get("error_after_mm")
                if isinstance(error_after_mm, (int, float)) and float(error_after_mm) > (error_mm - 1.0):
                    break
            except Exception:
                pass
            time.sleep(0.05)

        # Update result with final position and correction info
        if corrections_done > 0:
            # Re-read final position
            q_final = tools._read_joints_deg(_SO101_JOINTS)
            q_final_arr = np.array([q_final[j] for j in _SO101_JOINTS], dtype=float)
            T_final = kin.forward_kinematics(q_final_arr)
            xyz_final = T_final[:3, 3].astype(float)
            final_error_mm = float(np.linalg.norm(xyz_target - xyz_final) * 1000.0)

            result["ee_after_m"] = xyz_final.tolist()
            result["ee_delta_m"] = (xyz_final - p_meas).tolist()
            result["corrections_done"] = corrections_done
            result["corrections"] = correction_results
            result["final_error_mm"] = final_error_mm
        else:
            result["corrections_done"] = 0
            try:
                result["final_error_mm"] = float(
                    np.linalg.norm(xyz_target - np.array(result.get("ee_after_m", [0, 0, 0]), dtype=float))
                    * 1000.0
                )
            except Exception:
                result["final_error_mm"] = None

        result.update(
            {
                "base_source": base_source,
                "base_pose_m": p_base.tolist(),
                "measured_pose_m": p_meas.tolist(),
                "xyz_target_requested_m": xyz_target_requested.tolist(),
                "lift_plan": lift_plan,
                "polar_before": {"r_m": float(r0), "theta_deg": float(math.degrees(theta0))},
                "polar_target": {"r_m": float(r1), "theta_deg": float(math.degrees(theta1))},
                "requested": {
                    "dr_mm": dr_mm,
                    "dtheta_deg": float(dtheta_deg) if dtheta_deg is not None else None,
                    "dy_mm_legacy": dy_mm,
                    "dz_mm": dz_sem_mm,
                    "z_m": float(z_abs_m) if z_abs_m is not None else None,
                },
                "interpreted": {
                    "dtheta_rad": float(dtheta_rad),
                    "tangential_mm": tangential_mm,
                    "dz_kin_mm": float(dz_kin_mm),
                },
                "dz_to_kinematics_sign": float(tools.dz_to_kinematics_sign),
            }
        )

        # Normalize success semantics: "ok" indicates whether we reached the target within tolerance.
        try:
            final_error_mm = float(result.get("final_error_mm", 1e9))
            requested_delta_mm = float(np.linalg.norm((xyz_target_requested - p_base) * 1000.0))
            ok_threshold_mm = float(np.clip(0.30 * requested_delta_mm + 5.0, 10.0, 16.0))
            result["ok_threshold_mm"] = ok_threshold_mm
            final_ok = final_error_mm <= ok_threshold_mm
            result["ok"] = bool(final_ok)
            result["ik_ok"] = bool(final_ok)
            result["achieved_position_err_mm"] = float(final_error_mm)
        except Exception:
            pass

        return result
