#!/usr/bin/env python3
"""Demo CLI for Skill API.

Runs a simple pick-and-place sequence:
    home -> reach_square("e2") -> grasp -> place_square("e4") -> home

Usage:
    python -m skills.demo --port /dev/tty.usbmodem...
    
Or with dry-run (no robot connection):
    python -m skills.demo --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skill API Demo: home -> reach_square(e2) -> grasp -> place_square(e4) -> home"
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Robot serial port (e.g., /dev/tty.usbmodem...)",
    )
    parser.add_argument(
        "--robot-id",
        type=str,
        default="so101_chess",
        help="Robot calibration ID (default: so101_chess)",
    )
    parser.add_argument(
        "--urdf",
        type=str,
        default=None,
        help="Path to URDF file (or set SO101_URDF env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without connecting to robot",
    )
    parser.add_argument(
        "--from-square",
        type=str,
        default="e2",
        help="Source square (default: e2)",
    )
    parser.add_argument(
        "--to-square",
        type=str,
        default="e4",
        help="Destination square (default: e4)",
    )
    
    args = parser.parse_args()
    
    # Add paths
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    llm_tools_dir = repo_root / "llm-tools"
    
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if llm_tools_dir.exists() and str(llm_tools_dir) not in sys.path:
        sys.path.insert(0, str(llm_tools_dir))
    
    from_sq = args.from_square.strip().lower()
    to_sq = args.to_square.strip().lower()
    
    print("=" * 60)
    print("Skill API Demo")
    print("=" * 60)
    print(f"Sequence: home -> reach_square({from_sq!r}) -> grasp -> place_square({to_sq!r}) -> home")
    print()
    
    if args.dry_run:
        print("[DRY RUN] No robot connection - printing planned sequence:")
        print()
        steps = [
            ("home", {}),
            ("reach_square", {"square": from_sq, "approach_height_mm": 80}),
            ("grasp", {"profile": "default"}),
            ("place_square", {"square": to_sq, "retreat_height_mm": 80}),
            ("home", {}),
        ]
        for i, (skill, params) in enumerate(steps, 1):
            print(f"  Step {i}: {skill}({json.dumps(params)})")
        print()
        print("[DRY RUN] Complete - no robot actions taken")
        return 0
    
    if args.port is None:
        print("ERROR: --port is required (or use --dry-run)")
        print("  Example: python -m skills.demo --port /dev/tty.usbmodem...")
        return 1
    
    # Import and run
    from skills import SkillContext
    
    print(f"Connecting to robot on {args.port}...")
    print()
    
    with SkillContext(port=args.port, robot_id=args.robot_id, urdf_path=args.urdf) as ctx:
        
        def run_step(name: str, func, **kwargs):
            print(f"[{name}] Starting...")
            result = func(**kwargs)
            print(f"[{name}] Result:")
            print(json.dumps(result, indent=2))
            print()
            if not result.get("ok", False):
                print(f"[{name}] WARNING: Step returned ok=False")
            return result
        
        # Execute sequence
        results = []
        
        # Step 1: Home
        results.append(run_step("home", ctx.home))
        
        # Step 2: Reach source square
        results.append(run_step(f"reach_square({from_sq})", ctx.reach_square, square=from_sq, approach_height_mm=80))
        
        # Step 3: Grasp
        results.append(run_step("grasp", ctx.grasp, profile="default"))
        
        # Step 4: Place at destination
        results.append(run_step(f"place_square({to_sq})", ctx.place_square, square=to_sq, retreat_height_mm=80))
        
        # Step 5: Home
        results.append(run_step("home", ctx.home))
        
        # Summary
        print("=" * 60)
        print("Summary")
        print("=" * 60)
        
        all_ok = all(r.get("ok", False) for r in results)
        step_names = ["home", f"reach_square({from_sq})", "grasp", f"place_square({to_sq})", "home"]
        
        for name, result in zip(step_names, results):
            status = "✓" if result.get("ok", False) else "✗"
            print(f"  {status} {name}")
        
        print()
        if all_ok:
            print("All steps completed successfully!")
        else:
            print("Some steps failed. Check output above for details.")
        
        return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
