from .config import RobotConfig

__all__ = ["RobotConfig", "Robot", "make_robot_from_config"]


def __getattr__(name: str):
    if name == "Robot":
        from .robot import Robot

        return Robot
    if name == "make_robot_from_config":
        from .utils import make_robot_from_config

        return make_robot_from_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
