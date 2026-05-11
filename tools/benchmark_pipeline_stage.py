#!/usr/bin/env python3
"""Benchmark online-capable Neurobench stages on a synthetic video snippet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.online import AdaptiveEwmaZStage, synthetic_event_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark a streaming pipeline stage.")
    parser.add_argument("--stage", choices=["adaptive_ewma_z"], default="adaptive_ewma_z")
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--frame-rate-hz", type=float, default=100.0)
    parser.add_argument("--alpha", type=float, default=0.02)
    parser.add_argument("--threshold-z", type=float, default=3.0)
    parser.add_argument("--epsilon", type=float, default=1.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    video = synthetic_event_video(frames=args.frames, height=args.height, width=args.width)
    stage = AdaptiveEwmaZStage(alpha=args.alpha, threshold_z=args.threshold_z, epsilon=args.epsilon)
    for index, frame in enumerate(video):
        stage.process_frame(frame, index, index / args.frame_rate_hz)

    latency = stage.latency_summary()
    frame_budget_ms = 1000.0 / args.frame_rate_hz
    result = {
        "schema_version": 1,
        "stage": args.stage,
        "frame_rate_hz": args.frame_rate_hz,
        "frame_budget_ms": frame_budget_ms,
        "frame_shape": [args.height, args.width],
        "frames": args.frames,
        "params": {"alpha": args.alpha, "threshold_z": args.threshold_z, "epsilon": args.epsilon},
        "latency": latency,
        "closed_loop_feasible_on_this_machine": (
            latency["p99_ms"] is not None and float(latency["p99_ms"]) <= frame_budget_ms
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote benchmark summary to {args.out}")


if __name__ == "__main__":
    main()

