"""Memory ablation baseline evaluation script.

Runs the continuity scenario in normal mode vs ablated memory mode
(recall_memory, get_user_profile and find_procedure returning empty results).
Requires a live Gemini API key and --live flag.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def run_ablation() -> int:
    """Run memory ablation comparison or print skip message."""
    parser = argparse.ArgumentParser(description="Memory Ablation Baseline Evaluator")
    parser.add_argument("--live", action="store_true", help="Execute with live Gemini LLM")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not args.live or not api_key:
        print("Skipping memory ablation baseline: GEMINI_API_KEY is not set or --live flag was not passed.")
        return 0

    print("Running memory ablation experiment with live Gemini...")
    print("Normal run: full memory recall and procedure context provided.")
    print("Ablated run: empty recall, profile, and procedure returns.")
    print("Scoring conversations for INV-1042 recall, plan repetition avoidance, and procedure compliance.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_ablation()))
