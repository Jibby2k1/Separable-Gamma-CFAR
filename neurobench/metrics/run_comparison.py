"""Run-level comparison metrics for candidate consensus and uniqueness."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def candidate_consensus_metrics(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare accepted candidate IDs across runs.

    Each run may be a compact record with ``run_id`` and ``candidate_ids`` or a
    MetricsReport-like payload where accepted IDs live under
    ``metrics.object_level.accepted_candidate_ids``.
    """
    normalized = [_normalized_candidate_run(run, index) for index, run in enumerate(runs)]
    normalized = [run for run in normalized if run["run_id"]]
    id_sets = [set(run["candidate_ids"]) for run in normalized]
    all_ids = sorted(set().union(*id_sets)) if id_sets else []
    consensus_ids = sorted(set.intersection(*id_sets)) if id_sets else []
    pairwise = _pairwise_overlaps(normalized)
    unique_by_run = []
    for index, run in enumerate(normalized):
        other_sets = [candidate_ids for other_index, candidate_ids in enumerate(id_sets) if other_index != index]
        other_ids = set().union(*other_sets) if other_sets else set()
        unique_by_run.append({"run_id": run["run_id"], "candidate_ids": sorted(id_sets[index] - other_ids)})
    unique_ids = sorted(candidate_id for row in unique_by_run for candidate_id in row["candidate_ids"])
    candidate_support = [
        {
            "candidate_id": candidate_id,
            "support_count": sum(1 for candidate_ids in id_sets if candidate_id in candidate_ids),
            "run_ids": [run["run_id"] for run, candidate_ids in zip(normalized, id_sets) if candidate_id in candidate_ids],
        }
        for candidate_id in all_ids
    ]
    return {
        "run_count": len(normalized),
        "candidate_count_union": len(all_ids),
        "candidate_count_consensus": len(consensus_ids),
        "consensus_rate": len(consensus_ids) / len(all_ids) if all_ids else 0.0,
        "consensus_accepted_candidate_ids": consensus_ids,
        "unique_accepted_candidate_ids": unique_ids,
        "unique_by_run": unique_by_run,
        "pairwise_overlap": pairwise,
        "candidate_support": candidate_support,
    }


def metric_winner_table(
    runs: Sequence[Mapping[str, Any]],
    metric_specs: Sequence[tuple[str, str, str]],
) -> dict[str, Any]:
    """Return best run per metric for MetricsReport-like payloads."""
    rows = []
    for index, run in enumerate(runs):
        run_id = _primary_run_id(run, index)
        rows.append(
            {
                "run_id": run_id,
                "metrics_report_id": str(run.get("metrics_report_id", run_id)),
                "values": {
                    f"{section}.{metric}": _metric_value(run, section, metric)
                    for section, metric, _direction in metric_specs
                },
            }
        )
    winners = {}
    for section, metric, direction in metric_specs:
        key = f"{section}.{metric}"
        winners[key] = _best_run(rows, key, direction)
    return {"runs": rows, "best_by_metric": winners}


def _normalized_candidate_run(run: Mapping[str, Any], index: int) -> dict[str, Any]:
    run_id = _primary_run_id(run, index)
    if "candidate_ids" in run:
        raw_ids = run.get("candidate_ids")
    else:
        object_metrics = ((run.get("metrics") or {}).get("object_level") or {})
        raw_ids = object_metrics.get("accepted_candidate_ids") or object_metrics.get("unique_accepted_candidates") or []
    return {"run_id": run_id, "candidate_ids": _candidate_ids(raw_ids)}


def _pairwise_overlaps(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for left_index, left in enumerate(runs):
        left_ids = set(left["candidate_ids"])
        for right in runs[left_index + 1 :]:
            right_ids = set(right["candidate_ids"])
            intersection = sorted(left_ids & right_ids)
            union = sorted(left_ids | right_ids)
            rows.append(
                {
                    "run_a": left["run_id"],
                    "run_b": right["run_id"],
                    "shared_count": len(intersection),
                    "union_count": len(union),
                    "jaccard": len(intersection) / len(union) if union else 0.0,
                    "shared_candidate_ids": intersection,
                    "unique_to_a": sorted(left_ids - right_ids),
                    "unique_to_b": sorted(right_ids - left_ids),
                }
            )
    return rows


def _primary_run_id(payload: Mapping[str, Any], fallback_index: int = 0) -> str:
    run_ids = list(payload.get("run_ids") or [])
    if run_ids:
        return str(run_ids[0])
    return str(payload.get("run_id") or payload.get("metrics_report_id") or f"run_{fallback_index + 1}")


def _metric_value(payload: Mapping[str, Any], section: str, metric: str) -> float | int | None:
    value = ((payload.get("metrics") or {}).get(section) or {}).get(metric)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _best_run(rows: Sequence[Mapping[str, Any]], key: str, direction: str) -> dict[str, Any] | None:
    numeric = [
        {"run_id": row["run_id"], "metrics_report_id": row["metrics_report_id"], "value": row.get("values", {}).get(key)}
        for row in rows
        if isinstance(row.get("values", {}).get(key), (int, float)) and not isinstance(row.get("values", {}).get(key), bool)
    ]
    if not numeric:
        return None
    reverse = direction != "lower"
    return sorted(numeric, key=lambda item: item["value"], reverse=reverse)[0]


def _candidate_ids(raw: Any) -> list[str]:
    ids: list[str] = []
    for item in raw or []:
        if isinstance(item, Mapping):
            value = item.get("candidate_id", item.get("id", item.get("roi_id")))
        else:
            value = item
        if value is not None:
            ids.append(str(value))
    return sorted(set(ids))
