#!/usr/bin/env python3
"""Build missed-neuron proposal and artifact-risk artifacts for Process Lab."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.manifests import load_json, write_json
from neurobench.proposal_analysis import build_proposal_analysis


def rel_to_app(path: Path, app_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(app_dir.resolve()))
    except ValueError:
        try:
            return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            return str(path.resolve())


def flatten_row(row: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        flat[key] = ", ".join(str(item) for item in value) if isinstance(value, list) else value
    return flat


def write_tsv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = [flatten_row(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not materialized:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(materialized[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(materialized)


def attach_to_architecture_runs(
    path: Path,
    *,
    run_id: str,
    app_dir: Path,
    analysis_json: Path,
    artifact_tsv: Path,
    proposals_tsv: Path,
    analysis: Mapping[str, Any],
) -> None:
    manifest = load_json(path) if path.exists() else {"schema_version": 1, "runs": []}
    runs = list(manifest.get("runs") or [])
    run = next((item for item in runs if item.get("run_id") == run_id), None)
    if run is None:
        run = {"schema_version": 1, "run_id": run_id, "label": run_id.replace("_", " "), "pipeline": []}
        runs.append(run)
    artifacts = dict(run.get("artifacts") or {})
    artifacts.update(
        {
            "proposal_analysis": rel_to_app(analysis_json, app_dir),
            "artifact_classifier_tsv": rel_to_app(artifact_tsv, app_dir),
            "missed_neuron_proposals_tsv": rel_to_app(proposals_tsv, app_dir),
        }
    )
    run["artifacts"] = artifacts
    run["proposal_summary"] = {
        "artifact_high_risk_count": analysis.get("artifact_classifier", {}).get("high_risk_count", 0),
        "artifact_roi_count": analysis.get("artifact_classifier", {}).get("roi_count", 0),
        "missed_neuron_proposal_count": analysis.get("missed_neuron_proposals", {}).get("summary", {}).get("proposal_count", 0),
        "high_confidence_missed_neuron_count": analysis.get("missed_neuron_proposals", {}).get("summary", {}).get("high_confidence_count", 0),
    }
    manifest["runs"] = runs
    write_json(path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build proposal-analysis artifacts for a neuron review app.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, default=None)
    parser.add_argument("--architecture-runs", type=Path, default=None)
    parser.add_argument("--run-id", default="current_review_pipeline")
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-artifact-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    review_data = load_json(args.review_data)
    annotations = load_json(args.annotations) if args.annotations and args.annotations.exists() else None
    app_dir = args.review_data.resolve().parent
    artifact_dir = args.out_artifact_dir or (app_dir / "analysis")
    out_json = args.out_json or (artifact_dir / "proposal_analysis.json")
    artifact_tsv = artifact_dir / "artifact_classifier.tsv"
    proposals_tsv = artifact_dir / "missed_neuron_proposals.tsv"

    analysis = build_proposal_analysis(review_data, annotations, limit=args.limit)
    write_json(out_json, analysis)
    write_tsv(artifact_tsv, analysis.get("artifact_classifier", {}).get("rows", []))
    write_tsv(proposals_tsv, analysis.get("missed_neuron_proposals", {}).get("rows", []))

    if args.architecture_runs:
        attach_to_architecture_runs(
            args.architecture_runs,
            run_id=args.run_id,
            app_dir=app_dir,
            analysis_json=out_json,
            artifact_tsv=artifact_tsv,
            proposals_tsv=proposals_tsv,
            analysis=analysis,
        )
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()
