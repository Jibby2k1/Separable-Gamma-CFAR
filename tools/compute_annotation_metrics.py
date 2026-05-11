#!/usr/bin/env python3
"""Compute annotation-driven review metrics from review_data.json and annotations.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.annotation_metrics import compute_annotation_summary
from neurobench.manifests import load_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute annotation review metrics.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    summary = compute_annotation_summary(load_json(args.review_data), load_json(args.annotations))
    write_json(args.out, summary)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
