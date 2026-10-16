"""Scenario runner executing headless scenarios in mock or live mode."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agent_mock import run_mock_scenario
from backend.events import EventBus
from backend.scenarios import SCENARIOS


async def main() -> int:
    """CLI entrypoint for running customer support scenarios."""
    parser = argparse.ArgumentParser(description="Run Memory Fabric scenarios")
    parser.add_argument("scenario", choices=list(SCENARIOS.keys()), help="Scenario identifier")
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="Agent mode (mock or live)",
    )
    args = parser.parse_args()

    print(f"Running scenario '{args.scenario}' in {args.mode} mode...")
    bus = EventBus()

    if args.mode == "mock":
        await run_mock_scenario(args.scenario, bus=bus)
    else:
        # Live mode will be linked in T12
        print("Live agent mode not yet configured, falling back to mock")
        await run_mock_scenario(args.scenario, bus=bus)

    # Write events to replays directory
    replays_dir = Path("replays")
    replays_dir.mkdir(parents=True, exist_ok=True)
    replay_file = replays_dir / f"{args.scenario}.jsonl"

    with open(replay_file, "w", encoding="utf-8") as f:
        for evt in bus.events:
            f.write(json.dumps(asdict(evt), ensure_ascii=False) + "\n")

    print(f"Scenario '{args.scenario}' ended with {len(bus.events)} events.")
    print(f"Replay written to {replay_file}")
    last_event = bus.events[-1] if bus.events else None
    if last_event and last_event.type == "final":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
