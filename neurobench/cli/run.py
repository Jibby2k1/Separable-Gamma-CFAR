"""Pipeline-run CLI commands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from neurobench.manifests import load_json
from neurobench.pipelines.batch import execute_batch
from neurobench.pipelines.executor import dry_run_pipeline, execute_pipeline
from neurobench.pipelines.sweeps import execute_parameter_sweep
from neurobench.validation.schemas import validate_json, validation_error_summary


def add_run_subcommands(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "run",
        help="Validate, dry-run, and execute pipeline specs.",
        description="Validate, dry-run, and execute pipeline specs.",
    )
    run_subparsers = parser.add_subparsers(dest="run_command", metavar="run-command")

    validate_parser = run_subparsers.add_parser("validate", help="Validate a pipeline spec JSON file.")
    validate_parser.add_argument("spec", type=Path, help="Path to a pipeline spec JSON file.")
    validate_parser.set_defaults(func=validate_run_command)

    dry_run_parser = run_subparsers.add_parser("dry-run", help="Validate and print an execution plan.")
    dry_run_parser.add_argument("spec", type=Path, help="Path to a pipeline spec JSON file.")
    dry_run_parser.add_argument("--allow-planned", action="store_true", help="Allow planned/import-only stages in the dry run.")
    dry_run_parser.add_argument("--validate-artifacts", action="store_true", help="Validate artifact flow between stages.")
    dry_run_parser.add_argument("--json", action="store_true", help="Print the full dry-run plan as JSON.")
    dry_run_parser.set_defaults(func=dry_run_command)

    execute_parser = run_subparsers.add_parser("execute", help="Execute the locally wired CPU-safe pipeline subset.")
    execute_parser.add_argument("spec", type=Path, help="Path to a pipeline spec JSON file.")
    execute_parser.add_argument("--run-root", required=True, type=Path, help="Directory where run outputs should be written.")
    execute_parser.add_argument("--device", choices=["auto", "cpu", "cuda", "gpu"], help="Execution device override. auto falls back to CPU when CUDA is unavailable.")
    execute_parser.set_defaults(func=execute_run_command)

    batch_parser = run_subparsers.add_parser("batch", help="Execute multiple pipeline specs and write a batch summary.")
    batch_parser.add_argument("specs", nargs="+", type=Path, help="Pipeline spec JSON files to execute.")
    batch_parser.add_argument("--run-root", required=True, type=Path, help="Directory where batch outputs should be written.")
    batch_parser.add_argument("--json", action="store_true", help="Print the full batch summary as JSON.")
    batch_parser.set_defaults(func=batch_run_command)

    sweep_parser = run_subparsers.add_parser("sweep", help="Expand and execute a pipeline parameter sweep.")
    sweep_parser.add_argument("spec", type=Path, help="Pipeline spec JSON file with a sweep block.")
    sweep_parser.add_argument("--run-root", required=True, type=Path, help="Directory where sweep outputs should be written.")
    sweep_parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first failed sweep run.")
    sweep_parser.add_argument("--json", action="store_true", help="Print the full sweep summary as JSON.")
    sweep_parser.set_defaults(func=sweep_run_command)
    return parser


def validate_run_command(args: argparse.Namespace) -> int:
    try:
        payload = validate_json(args.spec, "pipeline_spec")
        dry_run_pipeline(payload, require_executable=False)
    except Exception as exc:
        print(f"Pipeline spec validation failed: {args.spec}", file=sys.stderr)
        print(validation_error_summary(exc), file=sys.stderr)
        return 1
    run_id = payload.get("run_id", "(unknown)")
    print(f"Validated pipeline spec: {args.spec} ({run_id})")
    return 0


def dry_run_command(args: argparse.Namespace) -> int:
    try:
        spec = load_json(args.spec)
        plan = dry_run_pipeline(
            spec,
            require_executable=not args.allow_planned,
            validate_artifacts=args.validate_artifacts,
        )
    except Exception as exc:
        print(f"Pipeline dry-run failed: {args.spec}", file=sys.stderr)
        print(validation_error_summary(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(f"Dry-run OK: {args.spec}")
        print(f"run_id: {plan.get('run_id') or '(none)'}")
        print(f"parameter_hash: {plan['parameter_hash']}")
        print(f"steps: {len(plan['steps'])}")
    return 0


def execute_run_command(args: argparse.Namespace) -> int:
    try:
        spec = load_json(args.spec)
        result = execute_pipeline(spec, run_root=args.run_root, device=args.device)
    except Exception as exc:
        print(f"Pipeline execution failed: {args.spec}", file=sys.stderr)
        print(validation_error_summary(exc), file=sys.stderr)
        return 1
    manifest_path = Path(result["run_root"]) / "pipeline_run.json"
    print(f"Pipeline execution completed: {manifest_path}")
    print(f"status: {result['status']}")
    print(f"artifacts: {len(result['pipeline_run'].get('artifacts', []))}")
    return 0


def batch_run_command(args: argparse.Namespace) -> int:
    summary = execute_batch(args.specs, run_root=args.run_root)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Batch execution summary: {Path(args.run_root) / 'batch_summary.json'}")
        print(f"status: {summary['status']}")
        print(f"succeeded: {summary['succeeded']}")
        print(f"failed: {summary['failed']}")
    return 0 if summary["failed"] == 0 else 1


def sweep_run_command(args: argparse.Namespace) -> int:
    try:
        spec = load_json(args.spec)
        summary = execute_parameter_sweep(
            spec,
            run_root=args.run_root,
            continue_on_error=not args.stop_on_error,
        )
    except Exception as exc:
        print(f"Sweep execution failed: {args.spec}", file=sys.stderr)
        print(validation_error_summary(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Sweep execution summary: {Path(args.run_root) / 'sweep_summary.json'}")
        print(f"status: {summary['status']}")
        print(f"succeeded: {summary['succeeded']}")
        print(f"failed: {summary['failed']}")
    return 0 if summary["failed"] == 0 else 1
