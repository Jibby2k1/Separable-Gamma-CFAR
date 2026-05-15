"""Reviewer provenance helpers for annotation files."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from neurobench.annotations import migrate_annotations_v3


STAMP_GROUPS = ("rois", "events", "suggestions", "virtualRois", "splitMergeDecisions", "promotedRois")


def backfill_reviewer_ids(
    annotations: Mapping[str, Any],
    reviewer_id: str,
    *,
    run_id: str | None = None,
    all_runs: bool = False,
    overwrite: bool = False,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Return annotations with reviewed items stamped with a reviewer ID."""

    reviewer = str(reviewer_id or "").strip()
    if not reviewer:
        raise ValueError("reviewer_id is required.")
    stamp_time = updated_at or datetime.now(timezone.utc).isoformat()
    payload = migrate_annotations_v3(annotations)
    summary = {
        "reviewer_id": reviewer,
        "updatedAt": stamp_time,
        "overwrite": bool(overwrite),
        "scopes": {},
        "stamped_total": 0,
        "skipped_total": 0,
    }

    if run_id and all_runs:
        raise ValueError("Use either run_id or all_runs, not both.")
    if run_id:
        runs = payload.setdefault("runs", {})
        if run_id not in runs:
            raise KeyError(f"Run '{run_id}' was not found.")
        _stamp_scope(runs[run_id], reviewer, stamp_time, overwrite, summary, f"runs.{run_id}")
    elif all_runs:
        for rid, bucket in sorted((payload.get("runs") or {}).items()):
            _stamp_scope(bucket, reviewer, stamp_time, overwrite, summary, f"runs.{rid}")
    else:
        _stamp_scope(payload, reviewer, stamp_time, overwrite, summary, "top_level")

    payload["updatedAt"] = stamp_time
    payload["reviewer_provenance_backfill"] = summary
    return payload


def reviewer_provenance_summary(
    annotations: Mapping[str, Any],
    *,
    run_id: str | None = None,
    all_runs: bool = False,
) -> dict[str, Any]:
    """Return reviewer provenance coverage for reviewed annotation items."""

    payload = migrate_annotations_v3(annotations)
    summary = {"scopes": {}, "reviewed_total": 0, "with_reviewer_total": 0, "missing_reviewer_total": 0, "reviewers": {}}
    if run_id and all_runs:
        raise ValueError("Use either run_id or all_runs, not both.")
    if run_id:
        bucket = (payload.get("runs") or {}).get(run_id)
        if bucket is None:
            raise KeyError(f"Run '{run_id}' was not found.")
        _summarize_scope(bucket, summary, f"runs.{run_id}")
    elif all_runs:
        for rid, bucket in sorted((payload.get("runs") or {}).items()):
            _summarize_scope(bucket, summary, f"runs.{rid}")
    else:
        _summarize_scope(payload, summary, "top_level")
    return summary


def _stamp_scope(
    scope: Mapping[str, Any],
    reviewer_id: str,
    updated_at: str,
    overwrite: bool,
    summary: dict[str, Any],
    scope_name: str,
) -> None:
    mutable = scope  # scope is a nested dict in the deep-copied payload.
    scope_counts = {"stamped": 0, "skipped": 0, "by_group": {}}
    for group in STAMP_GROUPS:
        bucket = mutable.setdefault(group, {}) if isinstance(mutable, dict) else {}
        if not isinstance(bucket, dict):
            continue
        group_counts = {"stamped": 0, "skipped": 0}
        for item_id, value in list(bucket.items()):
            item = dict(value or {})
            if not _is_reviewed(group, item, item_id, mutable):
                group_counts["skipped"] += 1
                continue
            if item.get("reviewer_id") and not overwrite:
                group_counts["skipped"] += 1
                continue
            item["reviewer_id"] = reviewer_id
            item["updatedAt"] = updated_at
            bucket[item_id] = item
            group_counts["stamped"] += 1
        scope_counts["stamped"] += group_counts["stamped"]
        scope_counts["skipped"] += group_counts["skipped"]
        scope_counts["by_group"][group] = group_counts
    summary["stamped_total"] += scope_counts["stamped"]
    summary["skipped_total"] += scope_counts["skipped"]
    summary["scopes"][scope_name] = scope_counts


def _summarize_scope(scope: Mapping[str, Any], summary: dict[str, Any], scope_name: str) -> None:
    scope_counts = {"reviewed": 0, "with_reviewer": 0, "missing_reviewer": 0, "by_group": {}, "reviewers": {}}
    for group in STAMP_GROUPS:
        bucket = scope.get(group) or {}
        if not isinstance(bucket, dict):
            continue
        group_counts = {"reviewed": 0, "with_reviewer": 0, "missing_reviewer": 0}
        for item_id, value in bucket.items():
            item = dict(value or {})
            if not _is_reviewed(group, item, item_id, scope):
                continue
            reviewer = str(item.get("reviewer_id") or "").strip()
            group_counts["reviewed"] += 1
            scope_counts["reviewed"] += 1
            summary["reviewed_total"] += 1
            if reviewer:
                group_counts["with_reviewer"] += 1
                scope_counts["with_reviewer"] += 1
                summary["with_reviewer_total"] += 1
                scope_counts["reviewers"][reviewer] = scope_counts["reviewers"].get(reviewer, 0) + 1
                summary["reviewers"][reviewer] = summary["reviewers"].get(reviewer, 0) + 1
            else:
                group_counts["missing_reviewer"] += 1
                scope_counts["missing_reviewer"] += 1
                summary["missing_reviewer_total"] += 1
        scope_counts["by_group"][group] = group_counts
    summary["scopes"][scope_name] = scope_counts


def _is_reviewed(group: str, item: Mapping[str, Any], item_id: str, scope: Mapping[str, Any]) -> bool:
    if group in {"rois", "virtualRois"}:
        return bool(item.get("cell_state") or item.get("state"))
    if group == "events":
        return bool(item.get("event_state") or item.get("state"))
    if group == "suggestions":
        return bool(item.get("state") or (scope.get("promotedRois") or {}).get(item_id))
    if group == "splitMergeDecisions":
        return bool(item.get("decision_state"))
    if group == "promotedRois":
        return True
    return False
