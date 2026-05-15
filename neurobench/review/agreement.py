"""Reviewer agreement metrics and disagreement queues."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from neurobench.annotations import migrate_annotations_v3
from neurobench.review.provenance import reviewer_provenance_summary


SUBJECT_GROUPS = ("rois", "events", "suggestions")
POSITIVE_LABELS = {"accepted", "accept", "promoted", "missed"}
NEGATIVE_LABELS = {"rejected", "reject", "artifact", "deleted"}


def binary_cohen_kappa(labels_a: Sequence[bool], labels_b: Sequence[bool]) -> dict[str, Any]:
    """Compute binary Cohen's kappa for two equally sized label sequences."""

    if len(labels_a) != len(labels_b):
        raise ValueError("Cohen kappa requires label sequences with the same length.")
    total = len(labels_a)
    if total == 0:
        return {"n": 0, "observed_agreement": 0.0, "expected_agreement": 0.0, "kappa": 0.0}

    observed = sum(1 for a, b in zip(labels_a, labels_b) if bool(a) == bool(b)) / total
    true_a = sum(1 for value in labels_a if bool(value)) / total
    true_b = sum(1 for value in labels_b if bool(value)) / total
    false_a = 1.0 - true_a
    false_b = 1.0 - true_b
    expected = true_a * true_b + false_a * false_b
    if expected == 1.0:
        kappa = 1.0 if observed == 1.0 else 0.0
    else:
        kappa = (observed - expected) / (1.0 - expected)
    return {
        "n": total,
        "observed_agreement": observed,
        "expected_agreement": expected,
        "kappa": kappa,
    }


def annotation_agreement_report(
    reviewer_a: Mapping[str, Any],
    reviewer_b: Mapping[str, Any],
    *,
    reviewer_a_id: str = "reviewer_a",
    reviewer_b_id: str = "reviewer_b",
    subject_groups: Iterable[str] = SUBJECT_GROUPS,
) -> dict[str, Any]:
    """Compare two annotation sets and return agreement plus adjudication items."""

    ann_a = migrate_annotations_v3(reviewer_a)
    ann_b = migrate_annotations_v3(reviewer_b)
    groups = tuple(subject_groups)
    rows: list[dict[str, Any]] = []
    group_summaries: dict[str, Any] = {}
    all_binary_a: list[bool] = []
    all_binary_b: list[bool] = []

    for group in groups:
        group_rows = _comparison_rows_for_group(group, ann_a, ann_b, reviewer_a_id, reviewer_b_id)
        rows.extend(group_rows)
        binary_a, binary_b = _binary_pairs(group_rows)
        all_binary_a.extend(binary_a)
        all_binary_b.extend(binary_b)
        group_summaries[group] = {
            "subject_count": len(group_rows),
            "both_labeled_count": sum(1 for row in group_rows if row["both_labeled"]),
            "exact_agreement_count": sum(1 for row in group_rows if row["exact_agreement"]),
            "exact_agreement_fraction": _fraction(sum(1 for row in group_rows if row["exact_agreement"]), len(group_rows)),
            "binary": binary_cohen_kappa(binary_a, binary_b),
            "label_pairs": _label_pair_counts(group_rows),
        }

    disagreements = [row for row in rows if _needs_adjudication(row)]
    return {
        "schema_version": 1,
        "reviewers": [reviewer_a_id, reviewer_b_id],
        "subject_groups": list(groups),
        "overall": {
            "subject_count": len(rows),
            "both_labeled_count": sum(1 for row in rows if row["both_labeled"]),
            "exact_agreement_count": sum(1 for row in rows if row["exact_agreement"]),
            "exact_agreement_fraction": _fraction(sum(1 for row in rows if row["exact_agreement"]), len(rows)),
            "binary": binary_cohen_kappa(all_binary_a, all_binary_b),
        },
        "by_group": group_summaries,
        "by_confidence_pair": _breakdown(rows, "confidence_pair"),
        "by_artifact_pair": _breakdown(rows, "artifact_pair"),
        "reviewer_provenance": {
            reviewer_a_id: reviewer_provenance_summary(ann_a),
            reviewer_b_id: reviewer_provenance_summary(ann_b),
        },
        "disagreement_queue": disagreements,
    }


def disagreement_queue(
    reviewer_a: Mapping[str, Any],
    reviewer_b: Mapping[str, Any],
    *,
    reviewer_a_id: str = "reviewer_a",
    reviewer_b_id: str = "reviewer_b",
    subject_groups: Iterable[str] = SUBJECT_GROUPS,
) -> list[dict[str, Any]]:
    """Return only the adjudication-ready disagreement items."""

    return annotation_agreement_report(
        reviewer_a,
        reviewer_b,
        reviewer_a_id=reviewer_a_id,
        reviewer_b_id=reviewer_b_id,
        subject_groups=subject_groups,
    )["disagreement_queue"]


def disagreement_tsv_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return flat TSV-friendly rows for the report disagreement queue."""

    rows = []
    for item in report.get("disagreement_queue", []) or []:
        rows.append(
            {
                "subject_group": item.get("subject_group", ""),
                "subject_id": item.get("subject_id", ""),
                "label_a": item.get("label_a", ""),
                "label_b": item.get("label_b", ""),
                "reviewer_a": item.get("reviewer_a", ""),
                "reviewer_b": item.get("reviewer_b", ""),
                "both_labeled": int(bool(item.get("both_labeled"))),
                "exact_agreement": int(bool(item.get("exact_agreement"))),
                "confidence_a": (item.get("confidence_pair") or ["", ""])[0],
                "confidence_b": (item.get("confidence_pair") or ["", ""])[1],
                "artifact_a": (item.get("artifact_pair") or ["", ""])[0],
                "artifact_b": (item.get("artifact_pair") or ["", ""])[1],
                "source_reviewer_id_a": (item.get("reviewer_id_pair") or ["", ""])[0],
                "source_reviewer_id_b": (item.get("reviewer_id_pair") or ["", ""])[1],
                "updated_at_a": (item.get("updated_at_pair") or ["", ""])[0],
                "updated_at_b": (item.get("updated_at_pair") or ["", ""])[1],
                "reason_tags_a": ",".join(item.get("reason_tags_a") or []),
                "reason_tags_b": ",".join(item.get("reason_tags_b") or []),
            }
        )
    return rows


def agreement_report_markdown(report: Mapping[str, Any], *, max_disagreements: int = 25) -> str:
    """Render a concise human-readable agreement report."""

    overall = report.get("overall", {}) or {}
    binary = overall.get("binary", {}) or {}
    lines = [
        "# Annotation Agreement Report",
        "",
        f"- Reviewers: {', '.join(str(item) for item in report.get('reviewers', []))}",
        f"- Compared subjects: {overall.get('subject_count', 0)}",
        f"- Both labeled: {overall.get('both_labeled_count', 0)}",
        f"- Exact agreement: {_pct(overall.get('exact_agreement_fraction', 0.0))}",
        f"- Binary kappa: {float(binary.get('kappa', 0.0)):.3f} (n={binary.get('n', 0)})",
        f"- Disagreement queue: {len(report.get('disagreement_queue', []) or [])}",
        "",
        "## By Group",
        "",
        "| Group | Subjects | Both labeled | Exact agreement | Kappa |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for group, summary in (report.get("by_group", {}) or {}).items():
        kappa = ((summary or {}).get("binary") or {}).get("kappa", 0.0)
        lines.append(
            f"| {group} | {summary.get('subject_count', 0)} | {summary.get('both_labeled_count', 0)} | "
            f"{_pct(summary.get('exact_agreement_fraction', 0.0))} | {float(kappa):.3f} |"
        )
    provenance = report.get("reviewer_provenance", {}) or {}
    lines.extend(["", "## Reviewer Provenance", "", "| File | Reviewed labels | With reviewer | Missing reviewer |", "| --- | ---: | ---: | ---: |"])
    for reviewer, summary in provenance.items():
        lines.append(
            f"| {reviewer} | {summary.get('reviewed_total', 0)} | "
            f"{summary.get('with_reviewer_total', 0)} | {summary.get('missing_reviewer_total', 0)} |"
        )
    rows = disagreement_tsv_rows(report)[:max_disagreements]
    lines.extend(["", "## Disagreement Queue", ""])
    if not rows:
        lines.append("No disagreements found.")
    else:
        lines.extend(["| Subject | A | B | Confidence | Notes |", "| --- | --- | --- | --- | --- |"])
        for row in rows:
            notes = []
            if not row["both_labeled"]:
                notes.append("missing label")
            if row["artifact_a"] != row["artifact_b"]:
                notes.append(f"artifact {row['artifact_a']} / {row['artifact_b']}")
            lines.append(
                f"| {row['subject_group']}:{row['subject_id']} | {row['label_a'] or 'unlabeled'} | "
                f"{row['label_b'] or 'unlabeled'} | {row['confidence_a']} / {row['confidence_b']} | "
                f"{'; '.join(notes) or 'label conflict'} |"
            )
        if len(report.get("disagreement_queue", []) or []) > len(rows):
            lines.append(f"\nShowing first {len(rows)} disagreements.")
    return "\n".join(lines) + "\n"


def _comparison_rows_for_group(
    group: str,
    ann_a: Mapping[str, Any],
    ann_b: Mapping[str, Any],
    reviewer_a_id: str,
    reviewer_b_id: str,
) -> list[dict[str, Any]]:
    items_a = dict(ann_a.get(group, {}) or {})
    items_b = dict(ann_b.get(group, {}) or {})
    rows = []
    for subject_id in sorted(set(items_a) | set(items_b), key=_sort_key):
        item_a = dict(items_a.get(subject_id, {}) or {})
        item_b = dict(items_b.get(subject_id, {}) or {})
        label_a = _label_for_group(group, item_a)
        label_b = _label_for_group(group, item_b)
        both_labeled = _is_labeled(label_a) and _is_labeled(label_b)
        exact_agreement = both_labeled and label_a == label_b
        rows.append(
            {
                "subject_type": group[:-1] if group.endswith("s") else group,
                "subject_group": group,
                "subject_id": str(subject_id),
                "reviewer_a": reviewer_a_id,
                "reviewer_b": reviewer_b_id,
                "label_a": label_a,
                "label_b": label_b,
                "binary_label_a": _binary_label(label_a),
                "binary_label_b": _binary_label(label_b),
                "both_labeled": both_labeled,
                "exact_agreement": exact_agreement,
                "confidence_pair": (_confidence(item_a), _confidence(item_b)),
                "artifact_pair": (_artifact_label(item_a), _artifact_label(item_b)),
                "reviewer_id_pair": (_reviewer_id(item_a), _reviewer_id(item_b)),
                "updated_at_pair": (_updated_at(item_a), _updated_at(item_b)),
                "reason_tags_a": list(item_a.get("reason_tags") or []),
                "reason_tags_b": list(item_b.get("reason_tags") or []),
            }
        )
    return rows


def _label_for_group(group: str, item: Mapping[str, Any]) -> str:
    if group == "rois":
        return _normalized_label(item.get("cell_state") or item.get("state"))
    if group == "events":
        return _normalized_label(item.get("event_state") or item.get("state"))
    if group == "suggestions":
        return _normalized_label(item.get("state"))
    return _normalized_label(item.get("state"))


def _normalized_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "accept": "accepted",
        "reject": "rejected",
        "artifact_like": "artifact",
        "possible_missed": "missed",
    }
    return aliases.get(raw, raw)


def _is_labeled(label: str) -> bool:
    return label not in {"", "unlabeled", "none", "na", "n/a"}


def _binary_label(label: str) -> bool | None:
    if label in POSITIVE_LABELS:
        return True
    if label in NEGATIVE_LABELS:
        return False
    return None


def _binary_pairs(rows: Sequence[Mapping[str, Any]]) -> tuple[list[bool], list[bool]]:
    labels_a: list[bool] = []
    labels_b: list[bool] = []
    for row in rows:
        label_a = row.get("binary_label_a")
        label_b = row.get("binary_label_b")
        if label_a is None or label_b is None:
            continue
        labels_a.append(bool(label_a))
        labels_b.append(bool(label_b))
    return labels_a, labels_b


def _needs_adjudication(row: Mapping[str, Any]) -> bool:
    if not row.get("both_labeled"):
        return True
    if not row.get("exact_agreement"):
        return True
    label_a = row.get("binary_label_a")
    label_b = row.get("binary_label_b")
    return label_a is not None and label_b is not None and label_a != label_b


def _confidence(item: Mapping[str, Any]) -> str:
    return str(item.get("confidence") or "").strip().lower() or "unlabeled"


def _artifact_label(item: Mapping[str, Any]) -> str:
    for key in ("artifact_class", "artifactClass"):
        if item.get(key):
            return str(item[key]).strip().lower()
    return "none"


def _reviewer_id(item: Mapping[str, Any]) -> str:
    return str(item.get("reviewer_id") or "").strip()


def _updated_at(item: Mapping[str, Any]) -> str:
    return str(item.get("updatedAt") or item.get("updated_at") or "").strip()


def _breakdown(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        value = row.get(key)
        if isinstance(value, tuple):
            bucket = " / ".join(str(part or "unlabeled") for part in value)
        else:
            bucket = str(value or "unlabeled")
        counts[bucket] += 1
    return dict(sorted(counts.items()))


def _label_pair_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(
        (
            str(row.get("label_a") or "unlabeled"),
            str(row.get("label_b") or "unlabeled"),
        )
        for row in rows
        if row.get("both_labeled")
    )
    return {" / ".join(pair): count for pair, count in sorted(counts.items())}


def _fraction(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _pct(value: Any) -> str:
    return f"{100.0 * float(value or 0.0):.1f}%"


def _sort_key(value: Any) -> tuple[int, Any]:
    raw = str(value)
    try:
        return (0, int(raw))
    except ValueError:
        return (1, raw)
