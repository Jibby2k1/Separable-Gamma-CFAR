"""Active review batch selection for candidate discovery workflows."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import statistics
from typing import Any

from neurobench.annotations import migrate_annotations_v3


REVIEWED_STATES = {"accepted", "rejected", "unsure", "accept", "reject", "artifact", "missed", "promoted"}


def build_active_review_batch(
    ranked_candidates: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    clusters: Mapping[str, Any] | None = None,
    annotations: Mapping[str, Any] | None = None,
    target_size: int = 20,
    include_reviewed: bool = False,
) -> dict[str, Any]:
    """Select the next high-value active-review tasks.

    This is a deterministic heuristic batcher. It favors candidates that are
    informative for parameter tuning: high-priority unlabeled candidates,
    ambiguous evidence near decision boundaries, artifact/neuron conflicts, and
    split/merge clusters.
    """
    target_size = int(target_size)
    if target_size < 1:
        raise ValueError("target_size must be positive.")
    ann = migrate_annotations_v3(annotations)
    ranked = _ranked_items(ranked_candidates)
    priority_values = [float(item.get("priority_score", 0.0)) for item in ranked]
    median_priority = statistics.median(priority_values) if priority_values else 0.0

    tasks: list[dict[str, Any]] = []
    for item in ranked:
        candidate_id = str(item.get("candidate_id", ""))
        if not candidate_id:
            continue
        state = _candidate_state(ann, candidate_id)
        if not include_reviewed and _is_reviewed(state):
            continue
        tasks.append(_candidate_task(item, state=state or "unlabeled", median_priority=median_priority))

    for cluster in list((clusters or {}).get("clusters", []) or []):
        candidate_ids = [str(value) for value in cluster.get("candidate_ids", []) or []]
        if not candidate_ids:
            continue
        if not include_reviewed and all(_is_reviewed(_candidate_state(ann, candidate_id)) for candidate_id in candidate_ids):
            continue
        tasks.append(_cluster_task(cluster, ranked))

    tasks = _dedupe_tasks(tasks)
    tasks.sort(key=lambda task: (-float(task["active_score"]), task["task_id"]))
    selected = tasks[:target_size]
    return {
        "schema_version": 1,
        "target_size": target_size,
        "candidate_count": len(ranked),
        "cluster_count": len(list((clusters or {}).get("clusters", []) or [])),
        "eligible_task_count": len(tasks),
        "selected_task_count": len(selected),
        "strategies": [
            "high_priority_unlabeled",
            "decision_boundary_uncertainty",
            "artifact_neuron_conflict",
            "split_merge_cluster",
        ],
        "tasks": selected,
        "summary": _batch_summary(selected),
    }


def _ranked_items(ranked_candidates: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(ranked_candidates, Mapping):
        items = ranked_candidates.get("ranked_candidates", ranked_candidates.get("candidates", []))
    else:
        items = ranked_candidates
    rows = [dict(item) for item in list(items or [])]
    rows.sort(key=lambda item: (int(item.get("rank", 10**9)), -float(item.get("priority_score", 0.0)), str(item.get("candidate_id", ""))))
    return rows


def _candidate_task(item: Mapping[str, Any], *, state: str, median_priority: float) -> dict[str, Any]:
    candidate_id = str(item["candidate_id"])
    features = dict(item.get("features") or {})
    reasons = list(item.get("reasons") or [])
    reason_codes = set(item.get("reason_codes") or [])
    priority = float(item.get("priority_score", 0.0))
    uncertainty_score, uncertainty_reasons, uncertainty_codes = _uncertainty(features, priority, median_priority)
    conflict_score, conflict_reasons = _conflict_score(features)
    active_score = priority + uncertainty_score + conflict_score
    if state in {"", "unlabeled"}:
        active_score += 0.75
        reasons.append("unlabeled candidate")
        reason_codes.add("unlabeled_candidate")
    reasons.extend(uncertainty_reasons)
    reasons.extend(conflict_reasons)
    reason_codes.update(uncertainty_codes)
    if conflict_reasons:
        reason_codes.add("artifact_neuron_conflict")
    return {
        "task_id": f"candidate:{candidate_id}",
        "task_type": "candidate",
        "subject_id": candidate_id,
        "candidate_id": candidate_id,
        "active_score": round(active_score, 6),
        "priority_score": round(priority, 6),
        "uncertainty_score": round(uncertainty_score, 6),
        "state": state or "unlabeled",
        "selected_by": _selected_by(reason_codes),
        "reason_codes": sorted(reason_codes),
        "reasons": _unique_strings(reasons),
        "recommended_context": ["video", "roi_overlay", "trace", "events", "nearby_candidates"],
    }


def _cluster_task(cluster: Mapping[str, Any], ranked: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidate_ids = [str(value) for value in cluster.get("candidate_ids", []) or []]
    ranked_by_id = {str(item.get("candidate_id")): item for item in ranked}
    top_priority = max((float(ranked_by_id.get(candidate_id, {}).get("priority_score", 0.0)) for candidate_id in candidate_ids), default=0.0)
    issue_codes = list(cluster.get("issue_codes", []) or [])
    reasons = [str(code).replace("_", " ") for code in issue_codes] or ["spatially related candidates"]
    action = str(cluster.get("suggested_action") or "review_cluster_context")
    active_score = top_priority + 1.25 + 0.25 * len(candidate_ids)
    if "possible_duplicate" in issue_codes or "split_merge_review" in issue_codes:
        active_score += 0.75
    return {
        "task_id": f"cluster:{cluster.get('cluster_id', ':'.join(candidate_ids))}",
        "task_type": "cluster",
        "subject_id": str(cluster.get("cluster_id", ":".join(candidate_ids))),
        "candidate_ids": candidate_ids,
        "active_score": round(active_score, 6),
        "priority_score": round(top_priority, 6),
        "uncertainty_score": 0.0,
        "selected_by": ["split_merge_cluster"],
        "reason_codes": sorted(set(issue_codes + ["split_merge_cluster"])),
        "reasons": reasons,
        "suggested_action": action,
        "recommended_context": ["video", "roi_overlay", "cluster_context", "candidate_table"],
    }


def _uncertainty(features: Mapping[str, Any], priority: float, median_priority: float) -> tuple[float, list[str], list[str]]:
    score = 0.0
    reasons: list[str] = []
    codes: list[str] = []
    if abs(priority - median_priority) <= max(0.25, abs(median_priority) * 0.15):
        score += 0.35
        reasons.append("near priority decision boundary")
        codes.append("decision_boundary")
    trace_snr = _as_float(features.get("trace_snr"))
    if 0.5 < trace_snr < 1.8:
        score += 0.35
        reasons.append("borderline trace SNR")
        codes.append("trace_snr_uncertainty")
    local_correlation = _as_float(features.get("local_correlation"))
    if 0.2 < local_correlation < 0.45:
        score += 0.25
        reasons.append("borderline local coherence")
        codes.append("local_coherence_uncertainty")
    event_support = _as_float(features.get("event_support"))
    if 0.2 < event_support < 0.45:
        score += 0.25
        reasons.append("borderline event support")
        codes.append("event_support_uncertainty")
    artifact_score = _as_float(features.get("artifact_score"))
    if 0.3 < artifact_score < 0.65:
        score += 0.35
        reasons.append("borderline artifact risk")
        codes.append("artifact_uncertainty")
    return score, reasons, codes


def _conflict_score(features: Mapping[str, Any]) -> tuple[float, list[str]]:
    artifact_score = _as_float(features.get("artifact_score"))
    event_count = _as_float(features.get("event_count"))
    trace_snr = _as_float(features.get("trace_snr"))
    event_support = _as_float(features.get("event_support"))
    if artifact_score >= 0.4 and (event_count > 0 or trace_snr >= 1.5 or event_support >= 0.35):
        return 0.75, ["artifact risk with neuron-like evidence"]
    return 0.0, []


def _candidate_state(annotations: Mapping[str, Any], candidate_id: str) -> str:
    roi = dict((annotations.get("rois") or {}).get(str(candidate_id), {}))
    value = roi.get("cell_state") or roi.get("state") or ""
    return str(value).strip().lower()


def _is_reviewed(state: str) -> bool:
    return str(state).strip().lower() in REVIEWED_STATES


def _selected_by(reason_codes: set[Any]) -> list[str]:
    strategies = []
    if "unlabeled_candidate" in reason_codes:
        strategies.append("high_priority_unlabeled")
    if any(str(code).endswith("_uncertainty") or code == "decision_boundary" for code in reason_codes):
        strategies.append("decision_boundary_uncertainty")
    if "artifact_neuron_conflict" in reason_codes:
        strategies.append("artifact_neuron_conflict")
    return strategies or ["high_priority_unlabeled"]


def _dedupe_tasks(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = str(task.get("task_id", ""))
        if not task_id:
            continue
        current = by_id.get(task_id)
        if current is None or float(task.get("active_score", 0.0)) > float(current.get("active_score", 0.0)):
            by_id[task_id] = dict(task)
    return list(by_id.values())


def _batch_summary(tasks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts_by_type: dict[str, int] = {}
    counts_by_strategy: dict[str, int] = {}
    for task in tasks:
        counts_by_type[str(task.get("task_type", "unknown"))] = counts_by_type.get(str(task.get("task_type", "unknown")), 0) + 1
        for strategy in task.get("selected_by", []) or []:
            name = str(strategy)
            counts_by_strategy[name] = counts_by_strategy.get(name, 0) + 1
    return {
        "counts_by_type": dict(sorted(counts_by_type.items())),
        "counts_by_strategy": dict(sorted(counts_by_strategy.items())),
    }


def _unique_strings(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
