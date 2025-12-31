"""Tool: move_gripper_delta - move EE using polar interface via Skill API.

This tool provides a base-centric POLAR interface for delta moves:
- dx_mm = delta radius (mm): +dx moves farther from base
- dtheta_deg = delta angle around base (degrees, CCW)
- dy_mm (legacy) = tangential arc length (mm) if dtheta_deg not provided
- dz_mm = vertical delta (mm): +dz means UP

The polar-to-Cartesian conversion is done in this tool, then the actual
motion is delegated to the Skill API.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np

# Make skills importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _REPO_ROOT / "skills"
if _SKILLS_DIR.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.skill_api import reach_pose as skill_reach_pose

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
    """Execute move_gripper_delta with polar-to-Cartesian conversion."""
    with tools._lock:
        tools._require_kin()
        
        # Get current EE pose
        T_meas = tools.get_ee_pose()
        p_meas = T_meas[:3, 3].astype(float)  # meters
        
        # Determine base position (commanded or measured)
        use_commanded_base = bool(args.get("use_commanded_base", True))
        p_cmd = getattr(tools, "_ee_cmd_xyz_m", None)
        cmd_meas_gap = float("inf")
        if isinstance(p_cmd, np.ndarray) and p_cmd.shape == (3,) and np.all(np.isfinite(p_cmd)):
            cmd_meas_gap = float(np.linalg.norm(p_cmd - p_meas))
        
        # Use commanded base only if close to measured (robot actually reached it)
        if use_commanded_base and cmd_meas_gap < 0.020:
            p_base = p_cmd.astype(float)
            base_source = "commanded"
        else:
            p_base = p_meas.astype(float)
            base_source = "measured"
            if cmd_meas_gap < float("inf"):
                base_source = f"measured (gap={cmd_meas_gap*1000:.1f}mm)"
            try:
                tools._ee_cmd_xyz_m = None
            except Exception:
                pass
        
        x0, y0, z0 = float(p_base[0]), float(p_base[1]), float(p_base[2])
        r0 = float(math.hypot(x0, y0))
        theta0 = float(math.atan2(y0, x0))
        
        # Parse input deltas
        dr_mm = float(np.clip(float(args.get("dx_mm", 0.0)), -200.0, 200.0))
        dy_mm = float(np.clip(float(args.get("dy_mm", 0.0)), -200.0, 200.0))
        dz_sem_mm = float(np.clip(float(args.get("dz_mm", 0.0)), -200.0, 200.0))
        
        # Handle dtheta vs legacy dy_mm
        dtheta_deg = args.get("dtheta_deg", None)
        if dtheta_deg is not None:
            dtheta_rad = float(math.radians(float(dtheta_deg)))
            tangential_mm = float((r0 * 1000.0) * dtheta_rad)
        else:
            # Legacy: dy_mm is arc length along the current circle
            dtheta_rad = float((dy_mm / 1000.0) / r0) if r0 > 1e-6 else 0.0
            tangential_mm = float(dy_mm)
        
        # Compute new polar coordinates
        r1 = max(0.0, r0 + (dr_mm / 1000.0))
        theta1 = theta0 + dtheta_rad
        x1 = float(r1 * math.cos(theta1))
        y1 = float(r1 * math.sin(theta1))
        
        # Handle Z coordinate
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
        
        # Execute move via Skill API
        result = skill_reach_pose(tools, {"xyz_m": xyz_target.tolist()}, frame="base")
        
        # Update commanded position reference if move succeeded
        if result.get("ok", False):
            try:
                tools._ee_cmd_xyz_m = xyz_target.copy()
            except Exception:
                pass
        
        # Enrich result with polar-specific info
        result.update({
            "base_source": base_source,
            "base_pose_m": p_base.tolist(),
            "measured_pose_m": p_meas.tolist(),
            "xyz_target_requested_m": xyz_target_requested.tolist(),
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
        })
        
        # Add backward-compatible fields
        result["ee_before_m"] = p_base.tolist()
        achieved = result.get("achieved_xyz_mm", [0, 0, 0])
        result["ee_after_m"] = [float(x / 1000) for x in achieved]
        result["ee_delta_m"] = [float((a - b) / 1000) for a, b in zip(achieved, [x * 1000 for x in p_base])]
        result["ik_ok"] = result.get("ok", False)
        result["achieved_position_err_mm"] = result.get("position_err_mm", 0)
        
        return result
