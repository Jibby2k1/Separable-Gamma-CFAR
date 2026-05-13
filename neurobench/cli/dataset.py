"""Dataset-related CLI commands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neurobench.data.qc import compute_dataset_qc_from_manifest, render_dataset_qc_markdown
from neurobench.manifests import write_json
from neurobench.validation.schemas import validate_json, validation_error_summary


def add_dataset_subcommands(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "dataset",
        help="Create, validate, and inspect dataset manifests.",
        description="Create, validate, and inspect dataset manifests.",
    )
    dataset_subparsers = parser.add_subparsers(dest="dataset_command", metavar="dataset-command")
    validate_parser = dataset_subparsers.add_parser("validate", help="Validate a dataset manifest JSON file.")
    validate_parser.add_argument("manifest", type=Path, help="Path to a dataset manifest JSON file.")
    validate_parser.set_defaults(func=validate_dataset_command)

    qc_parser = dataset_subparsers.add_parser("qc", help="Generate a dataset QC JSON and Markdown report.")
    qc_parser.add_argument("manifest", type=Path, help="Path to a dataset manifest JSON file.")
    qc_parser.add_argument("--output", required=True, type=Path, help="Output directory for qc_report.json and qc_report.md.")
    qc_parser.set_defaults(func=dataset_qc_command)
    return parser


def add_validate_subcommands(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "validate",
        help="Validate public Neurobench artifacts.",
        description="Validate public Neurobench artifacts.",
    )
    validate_subparsers = parser.add_subparsers(dest="validate_command", metavar="artifact")
    dataset_parser = validate_subparsers.add_parser("dataset", help="Validate a dataset manifest JSON file.")
    dataset_parser.add_argument("manifest", type=Path, help="Path to a dataset manifest JSON file.")
    dataset_parser.set_defaults(func=validate_dataset_command)
    return parser


def validate_dataset_command(args: argparse.Namespace) -> int:
    try:
        payload = validate_json(args.manifest, "dataset")
    except Exception as exc:  # pragma: no cover - exact exception type is tested via subprocess behavior.
        print(f"Dataset manifest validation failed: {args.manifest}", file=sys.stderr)
        print(validation_error_summary(exc), file=sys.stderr)
        return 1
    dataset_id = payload.get("dataset_id", "(unknown)")
    print(f"Validated dataset manifest: {args.manifest} ({dataset_id})")
    return 0


def dataset_qc_command(args: argparse.Namespace) -> int:
    try:
        validate_json(args.manifest, "dataset")
        qc = compute_dataset_qc_from_manifest(args.manifest)
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "qc_report.json"
        markdown_path = out_dir / "qc_report.md"
        write_json(json_path, qc)
        markdown_path.write_text(render_dataset_qc_markdown(qc), encoding="utf-8")
    except Exception as exc:
        print(f"Dataset QC failed: {args.manifest}", file=sys.stderr)
        print(validation_error_summary(exc), file=sys.stderr)
        return 1
    print(f"Dataset QC JSON: {json_path}")
    print(f"Dataset QC Markdown: {markdown_path}")
    print(f"warnings: {len(qc.get('warnings') or [])}")
    return 0
