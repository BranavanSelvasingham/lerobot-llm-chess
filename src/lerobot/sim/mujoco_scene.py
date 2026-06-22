#!/usr/bin/env python

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.dom import minidom
from xml.etree import ElementTree as ET

from lerobot.configs.chessboard import ChessBoardParams

from .robot import JOINT_LIMITS_DEG, SO101_BODY_JOINTS, SO101_JOINTS


SO101_DEV_MJCF_SCHEMA = "lerobot.sim.so101_development_mjcf.v1"
SO101_DEV_MJCF_AUTHORITY = "development_scaffold_not_reviewed"


def _attrs(values: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items() if value is not None}


def _vec(values: tuple[float, ...] | list[float]) -> str:
    return " ".join(f"{value:.6g}" for value in values)


def _rgba(values: tuple[float, float, float, float]) -> str:
    return " ".join(f"{value:.3f}" for value in values)


def _square_to_indices(square: str) -> tuple[int, int]:
    value = square.strip().lower()
    if len(value) != 2 or not ("a" <= value[0] <= "h") or not ("1" <= value[1] <= "8"):
        raise ValueError(f"Invalid chess square: {square!r}")
    return ord(value[0]) - ord("a"), int(value[1]) - 1


@dataclass(kw_only=True)
class SO101DevelopmentMJCFConfig:
    """Approximate SO-101 chess scene used only to exercise MuJoCo plumbing."""

    board_params: ChessBoardParams = field(default_factory=ChessBoardParams)
    board_origin_m: tuple[float, float, float] = (0.12, -0.20, 0.0)
    base_height_m: float = 0.10
    shoulder_to_elbow_m: float = 0.15
    elbow_to_wrist_m: float = 0.12
    wrist_to_gripper_m: float = 0.08
    link_radius_m: float = 0.018
    contact_condim: int = 3
    contact_friction: tuple[float, float, float] = (0.8, 0.02, 0.001)
    gripper_opening_m: float = 0.04
    gripper_min_closure_m: float = 0.0
    gripper_actuator_kp: float = 8.0
    body_actuator_kp: float = 4.0
    piece_square: str = "e4"
    target_square: str = "e5"
    piece_radius_m: float = 0.014
    piece_height_m: float = 0.038
    piece_mass_kg: float = 0.02
    model_name: str = "so101_chess_development"

    def __post_init__(self) -> None:
        _square_to_indices(self.piece_square)
        _square_to_indices(self.target_square)
        if self.piece_square.strip().lower() == self.target_square.strip().lower():
            raise ValueError("piece_square and target_square must differ.")
        if self.gripper_min_closure_m >= self.gripper_opening_m:
            raise ValueError("gripper_min_closure_m must be smaller than gripper_opening_m.")
        if self.contact_condim not in {1, 3, 4, 6}:
            raise ValueError("contact_condim must be one of MuJoCo's supported contact dimensions: 1, 3, 4, or 6.")
        if self.piece_mass_kg <= 0:
            raise ValueError("piece_mass_kg must be positive.")


def square_center_board_m(square: str, board_params: ChessBoardParams) -> tuple[float, float, float]:
    file_idx, rank_idx = _square_to_indices(square)
    sx = board_params.effective_square_size_x_mm / 1000.0
    sy = board_params.effective_square_size_y_mm / 1000.0
    return (
        (file_idx + 0.5) * sx,
        (rank_idx + 0.5) * sy,
        board_params.board_height_mm / 1000.0,
    )


def square_center_world_m(square: str, config: SO101DevelopmentMJCFConfig) -> tuple[float, float, float]:
    x, y, z = square_center_board_m(square, config.board_params)
    ox, oy, oz = config.board_origin_m
    return ox + x, oy + y, oz + z


def _add_materials(asset: ET.Element) -> None:
    materials = {
        "mat_floor": (0.20, 0.22, 0.24, 1.0),
        "mat_base": (0.15, 0.16, 0.18, 1.0),
        "mat_link": (0.08, 0.32, 0.56, 1.0),
        "mat_wrist": (0.34, 0.34, 0.36, 1.0),
        "mat_gripper": (0.10, 0.10, 0.11, 1.0),
        "mat_board": (0.13, 0.09, 0.05, 1.0),
        "mat_square_light": (0.78, 0.70, 0.56, 1.0),
        "mat_square_dark": (0.35, 0.23, 0.13, 1.0),
        "mat_piece": (0.92, 0.90, 0.84, 1.0),
        "mat_target": (0.15, 0.55, 0.32, 0.35),
    }
    for name, rgba in materials.items():
        ET.SubElement(asset, "material", _attrs({"name": name, "rgba": _rgba(rgba)}))


def _add_joint(body: ET.Element, name: str, axis: tuple[float, float, float]) -> None:
    lo, hi = JOINT_LIMITS_DEG[name]
    ET.SubElement(
        body,
        "joint",
        _attrs(
            {
                "name": name,
                "type": "hinge",
                "axis": _vec(axis),
                "range": f"{lo:.6g} {hi:.6g}",
                "limited": "true",
                "damping": 1.0,
                "armature": 0.01,
            }
        ),
    )


def _add_robot(worldbody: ET.Element, config: SO101DevelopmentMJCFConfig) -> None:
    base = ET.SubElement(worldbody, "body", _attrs({"name": "base_link", "pos": "0 0 0"}))
    ET.SubElement(
        base,
        "geom",
        _attrs({"name": "base_collision", "type": "cylinder", "size": "0.045 0.03", "material": "mat_base"}),
    )

    pan = ET.SubElement(
        base,
        "body",
        _attrs({"name": "shoulder_pan_link", "pos": f"0 0 {config.base_height_m:.6g}"}),
    )
    _add_joint(pan, "shoulder_pan", (0.0, 0.0, 1.0))
    ET.SubElement(
        pan,
        "geom",
        _attrs({"name": "shoulder_pan_collision", "type": "sphere", "size": "0.032", "material": "mat_link"}),
    )

    shoulder = ET.SubElement(pan, "body", _attrs({"name": "shoulder_lift_link", "pos": "0 0 0"}))
    _add_joint(shoulder, "shoulder_lift", (0.0, 1.0, 0.0))
    ET.SubElement(
        shoulder,
        "geom",
        _attrs(
            {
                "name": "upper_arm_collision",
                "type": "capsule",
                "fromto": f"0 0 0 {config.shoulder_to_elbow_m:.6g} 0 0",
                "size": f"{config.link_radius_m:.6g}",
                "material": "mat_link",
            }
        ),
    )

    elbow = ET.SubElement(
        shoulder,
        "body",
        _attrs({"name": "elbow_flex_link", "pos": f"{config.shoulder_to_elbow_m:.6g} 0 0"}),
    )
    _add_joint(elbow, "elbow_flex", (0.0, 1.0, 0.0))
    ET.SubElement(
        elbow,
        "geom",
        _attrs(
            {
                "name": "forearm_collision",
                "type": "capsule",
                "fromto": f"0 0 0 {config.elbow_to_wrist_m:.6g} 0 0",
                "size": f"{config.link_radius_m:.6g}",
                "material": "mat_link",
            }
        ),
    )

    wrist = ET.SubElement(
        elbow,
        "body",
        _attrs({"name": "wrist_flex_link", "pos": f"{config.elbow_to_wrist_m:.6g} 0 0"}),
    )
    _add_joint(wrist, "wrist_flex", (0.0, 1.0, 0.0))
    ET.SubElement(
        wrist,
        "geom",
        _attrs(
            {
                "name": "wrist_collision",
                "type": "capsule",
                "fromto": f"0 0 0 {config.wrist_to_gripper_m:.6g} 0 0",
                "size": f"{config.link_radius_m * 0.85:.6g}",
                "material": "mat_wrist",
            }
        ),
    )

    roll = ET.SubElement(
        wrist,
        "body",
        _attrs({"name": "wrist_roll_link", "pos": f"{config.wrist_to_gripper_m:.6g} 0 0"}),
    )
    _add_joint(roll, "wrist_roll", (1.0, 0.0, 0.0))
    ET.SubElement(
        roll,
        "geom",
        _attrs({"name": "gripper_palm_collision", "type": "box", "size": "0.018 0.024 0.012", "material": "mat_gripper"}),
    )
    ET.SubElement(roll, "site", _attrs({"name": "gripper_frame_link", "pos": "0 0 0", "size": "0.006", "rgba": "1 0 0 1"}))

    moving_finger = ET.SubElement(roll, "body", _attrs({"name": "gripper_moving_finger", "pos": "0 0 0"}))
    ET.SubElement(
        moving_finger,
        "joint",
        _attrs(
            {
                "name": "gripper",
                "type": "slide",
                "axis": "0 1 0",
                "range": f"{config.gripper_min_closure_m:.6g} {config.gripper_opening_m:.6g}",
                "limited": "true",
                "damping": 0.2,
            }
        ),
    )
    ET.SubElement(
        moving_finger,
        "geom",
        _attrs({"name": "gripper_moving_finger_collision", "type": "box", "pos": "0 0.018 -0.025", "size": "0.008 0.004 0.028", "material": "mat_gripper"}),
    )
    ET.SubElement(
        roll,
        "geom",
        _attrs({"name": "gripper_fixed_finger_collision", "type": "box", "pos": "0 -0.018 -0.025", "size": "0.008 0.004 0.028", "material": "mat_gripper"}),
    )


def _add_board(worldbody: ET.Element, config: SO101DevelopmentMJCFConfig) -> None:
    params = config.board_params
    sx = params.effective_square_size_x_mm / 1000.0
    sy = params.effective_square_size_y_mm / 1000.0
    board_w = sx * params.board_size[0]
    board_h = sy * params.board_size[1]
    board_z = params.board_height_mm / 1000.0
    board = ET.SubElement(worldbody, "body", _attrs({"name": "chess_board", "pos": _vec(config.board_origin_m)}))
    ET.SubElement(
        board,
        "geom",
        _attrs(
            {
                "name": "chess_board_collision",
                "type": "box",
                "pos": _vec((board_w / 2.0, board_h / 2.0, board_z / 2.0)),
                "size": _vec((board_w / 2.0, board_h / 2.0, board_z / 2.0)),
                "material": "mat_board",
            }
        ),
    )
    square_visual_z = board_z + 0.001
    for rank in range(params.board_size[1]):
        for file_idx in range(params.board_size[0]):
            name = f"square_{chr(ord('a') + file_idx)}{rank + 1}"
            material = "mat_square_light" if (file_idx + rank) % 2 == 0 else "mat_square_dark"
            ET.SubElement(
                board,
                "geom",
                _attrs(
                    {
                        "name": name,
                        "type": "box",
                        "pos": _vec(((file_idx + 0.5) * sx, (rank + 0.5) * sy, square_visual_z)),
                        "size": _vec((sx / 2.0, sy / 2.0, 0.0008)),
                        "material": material,
                        "contype": 0,
                        "conaffinity": 0,
                    }
                ),
            )

    x, y, z = square_center_board_m(config.target_square, params)
    ET.SubElement(
        board,
        "geom",
        _attrs(
            {
                "name": "target_square_marker",
                "type": "box",
                "pos": _vec((x, y, z + 0.002)),
                "size": _vec((sx * 0.35, sy * 0.35, 0.001)),
                "material": "mat_target",
                "contype": 0,
                "conaffinity": 0,
            }
        ),
    )


def _add_piece(worldbody: ET.Element, config: SO101DevelopmentMJCFConfig) -> None:
    x, y, z = square_center_world_m(config.piece_square, config)
    piece = ET.SubElement(
        worldbody,
        "body",
        _attrs({"name": "piece_source", "pos": _vec((x, y, z + config.piece_height_m / 2.0))}),
    )
    ET.SubElement(piece, "freejoint", _attrs({"name": "piece_source_freejoint"}))
    ET.SubElement(
        piece,
        "geom",
        _attrs(
            {
                "name": "piece_source_collision",
                "type": "cylinder",
                "size": _vec((config.piece_radius_m, config.piece_height_m / 2.0)),
                "material": "mat_piece",
                "mass": f"{config.piece_mass_kg:.6g}",
            }
        ),
    )


def build_so101_development_mjcf(config: SO101DevelopmentMJCFConfig | None = None) -> str:
    cfg = config or SO101DevelopmentMJCFConfig()
    root = ET.Element("mujoco", _attrs({"model": cfg.model_name}))
    ET.SubElement(root, "compiler", _attrs({"angle": "degree", "coordinate": "local"}))
    ET.SubElement(root, "option", _attrs({"timestep": 0.002, "gravity": "0 0 -9.81"}))

    custom = ET.SubElement(root, "custom")
    ET.SubElement(custom, "text", _attrs({"name": "schema", "data": SO101_DEV_MJCF_SCHEMA}))
    ET.SubElement(custom, "text", _attrs({"name": "authority", "data": SO101_DEV_MJCF_AUTHORITY}))
    ET.SubElement(
        custom,
        "text",
        _attrs(
            {
                "name": "limitations",
                "data": "Approximate generated robot geometry; not reviewed source authority, not calibrated IK truth.",
            }
        ),
    )

    asset = ET.SubElement(root, "asset")
    _add_materials(asset)

    default = ET.SubElement(root, "default")
    ET.SubElement(
        default,
        "geom",
        _attrs(
            {
                "condim": cfg.contact_condim,
                "friction": _vec(cfg.contact_friction),
                "density": 700,
            }
        ),
    )

    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(
        worldbody,
        "geom",
        _attrs({"name": "floor", "type": "plane", "size": "1.0 1.0 0.02", "material": "mat_floor"}),
    )
    _add_robot(worldbody, cfg)
    _add_board(worldbody, cfg)
    _add_piece(worldbody, cfg)

    actuator = ET.SubElement(root, "actuator")
    for joint in SO101_BODY_JOINTS:
        ET.SubElement(
            actuator,
            "position",
            _attrs({"name": f"{joint}_actuator", "joint": joint, "kp": cfg.body_actuator_kp}),
        )
    ET.SubElement(
        actuator,
        "position",
        _attrs({"name": "gripper_actuator", "joint": "gripper", "kp": cfg.gripper_actuator_kp}),
    )

    rough = ET.tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def development_mjcf_manifest(config: SO101DevelopmentMJCFConfig, *, model_path: str | Path) -> dict[str, Any]:
    return {
        "schema": SO101_DEV_MJCF_SCHEMA,
        "authority": SO101_DEV_MJCF_AUTHORITY,
        "ready_for_model_backed_ik": False,
        "model_path": str(model_path),
        "joint_names": list(SO101_JOINTS),
        "body_joint_names": list(SO101_BODY_JOINTS),
        "target_frame": "gripper_frame_link",
        "piece_freejoint": "piece_source_freejoint",
        "piece_body": "piece_source",
        "piece_collision_geom": "piece_source_collision",
        "config": asdict(config),
        "limitations": [
            "Generated from approximate repo-local dimensions, not reviewed CAD, URDF, or MJCF source.",
            "Mesh assets, calibrated TCP offset, and measured base-to-board alignment are not provided.",
            "Use only for MuJoCo plumbing, joint synchronization, chess-board collision, and Gymnasium smoke tests.",
        ],
    }


def write_so101_development_mjcf(
    output_path: str | Path,
    config: SO101DevelopmentMJCFConfig | None = None,
    *,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = config or SO101DevelopmentMJCFConfig()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_so101_development_mjcf(cfg))
    manifest = development_mjcf_manifest(cfg, model_path=path)
    if manifest_path is not None:
        manifest_file = Path(manifest_path)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
        manifest["manifest_path"] = str(manifest_file)
    return manifest


__all__ = [
    "SO101_DEV_MJCF_AUTHORITY",
    "SO101_DEV_MJCF_SCHEMA",
    "SO101DevelopmentMJCFConfig",
    "build_so101_development_mjcf",
    "development_mjcf_manifest",
    "square_center_board_m",
    "square_center_world_m",
    "write_so101_development_mjcf",
]
