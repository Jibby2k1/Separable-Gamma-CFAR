#!/usr/bin/env python3
"""Build a shareable review report from review data and annotations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_json, write_json
from neurobench.review_reports import build_review_report, render_review_report_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Markdown and JSON review report.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    report = build_review_report(load_json(args.review_data), load_json(args.annotations))
    write_json(args.out_json, report)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_review_report_markdown(report), encoding="utf-8")
    print(f"Wrote {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()
