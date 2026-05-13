"""Candidate clustering for duplicate and split/merge review triage."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from neurobench.discovery.ranking import build_candidate_feature_table, validate_candidate_feature_table


def cluster_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    video_shape: Sequence[int] | Mapping[str, Any] | None = None,
    centroid_distance_px: float = 5.0,
    bbox_iou_threshold: float = 0.10,
) -> dict[str, Any]:
    """Build feature rows and cluster nearby or overlapping candidates."""
    features = build_candidate_feature_table(candidates, video_shape=video_shape)
    clusters = cluster_candidate_features(
        features,
        centroid_distance_px=centroid_distance_px,
        bbox_iou_threshold=bbox_iou_threshold,
    )
    clusters["features"] = features
    return clusters


def cluster_candidate_features(
    feature_rows: Sequence[Mapping[str, Any]],
    *,
    centroid_distance_px: float = 5.0,
    bbox_iou_threshold: float = 0.10,
) -> dict[str, Any]:
    """Cluster candidate feature rows by centroid proximity or bbox overlap."""
    rows = [dict(row) for row in feature_rows]
    validate_candidate_feature_table(rows)
    centroid_distance_px = float(centroid_distance_px)
    bbox_iou_threshold = float(bbox_iou_threshold)
    if centroid_distance_px < 0:
        raise ValueError("centroid_distance_px must be non-negative.")
    if bbox_iou_threshold < 0 or bbox_iou_threshold > 1:
        raise ValueError("bbox_iou_threshold must be between 0 and 1.")

    links = _candidate_links(
        rows,
        centroid_distance_px=centroid_distance_px,
        bbox_iou_threshold=bbox_iou_threshold,
    )
    groups = _connected_components(rows, links)
    clusters = [_cluster_summary(index, group, links) for index, group in enumerate(groups, start=1) if len(group) > 1]
    singletons = [str(group[0]["candidate_id"]) for group in groups if len(group) == 1]
    return {
        "schema_version": 1,
        "candidate_count": len(rows),
        "cluster_count": len(clusters),
        "singleton_count": len(singletons),
        "parameters": {
            "centroid_distance_px": centroid_distance_px,
            "bbox_iou_threshold": bbox_iou_threshold,
        },
        "clusters": clusters,
        "singletons": sorted(singletons),
    }


def _candidate_links(
    rows: Sequence[Mapping[str, Any]],
    *,
    centroid_distance_px: float,
    bbox_iou_threshold: float,
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1 :]:
            distance = _centroid_distance(left, right)
            iou = _bbox_iou(left, right)
            reasons: list[str] = []
            if distance <= centroid_distance_px:
                reasons.append("nearby_centroids")
            if iou >= bbox_iou_threshold and iou > 0:
                reasons.append("overlapping_bboxes")
            if reasons:
                links.append(
                    {
                        "candidate_a": str(left["candidate_id"]),
                        "candidate_b": str(right["candidate_id"]),
                        "centroid_distance_px": round(distance, 6),
                        "bbox_iou": round(iou, 6),
                        "reasons": reasons,
                    }
                )
    links.sort(key=lambda item: (item["candidate_a"], item["candidate_b"]))
    return links


def _connected_components(rows: Sequence[Mapping[str, Any]], links: Sequence[Mapping[str, Any]]) -> list[list[dict[str, Any]]]:
    by_id = {str(row["candidate_id"]): dict(row) for row in rows}
    parent = {candidate_id: candidate_id for candidate_id in by_id}

    def find(candidate_id: str) -> str:
        while parent[candidate_id] != candidate_id:
            parent[candidate_id] = parent[parent[candidate_id]]
            candidate_id = parent[candidate_id]
        return candidate_id

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    for link in links:
        union(str(link["candidate_a"]), str(link["candidate_b"]))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate_id, row in by_id.items():
        grouped.setdefault(find(candidate_id), []).append(row)
    groups = []
    for group in grouped.values():
        groups.append(sorted(group, key=lambda row: str(row["candidate_id"])))
    groups.sort(key=lambda group: str(group[0]["candidate_id"]))
    return groups


def _cluster_summary(index: int, rows: Sequence[Mapping[str, Any]], links: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidate_ids = [str(row["candidate_id"]) for row in rows]
    id_set = set(candidate_ids)
    cluster_links = [
        dict(link)
        for link in links
        if str(link["candidate_a"]) in id_set and str(link["candidate_b"]) in id_set
    ]
    x0 = min(float(row["bbox_x"]) for row in rows)
    y0 = min(float(row["bbox_y"]) for row in rows)
    x1 = max(float(row["bbox_x"]) + float(row["bbox_width_px"]) for row in rows)
    y1 = max(float(row["bbox_y"]) + float(row["bbox_height_px"]) for row in rows)
    max_iou = max((float(link["bbox_iou"]) for link in cluster_links), default=0.0)
    min_distance = min((float(link["centroid_distance_px"]) for link in cluster_links), default=0.0)
    issue_codes = _issue_codes(rows, cluster_links, max_iou=max_iou)
    return {
        "cluster_id": f"cluster_{index:03d}",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "centroid_x": round(sum(float(row["centroid_x"]) for row in rows) / len(rows), 6),
        "centroid_y": round(sum(float(row["centroid_y"]) for row in rows) / len(rows), 6),
        "bbox": {
            "x": round(x0, 6),
            "y": round(y0, 6),
            "width": round(x1 - x0, 6),
            "height": round(y1 - y0, 6),
        },
        "area_px_sum": round(sum(float(row["area_px"]) for row in rows), 6),
        "max_pairwise_bbox_iou": round(max_iou, 6),
        "min_pairwise_centroid_distance_px": round(min_distance, 6),
        "issue_codes": issue_codes,
        "suggested_action": _suggested_action(issue_codes),
        "links": cluster_links,
    }


def _issue_codes(rows: Sequence[Mapping[str, Any]], links: Sequence[Mapping[str, Any]], *, max_iou: float) -> list[str]:
    codes: set[str] = set()
    if max_iou >= 0.25:
        codes.add("possible_duplicate")
    if len(rows) >= 3:
        codes.add("clustered_candidates")
    if any(float(link["centroid_distance_px"]) <= 3.0 for link in links):
        codes.add("close_centroids")
    area_values = [float(row["area_px"]) for row in rows]
    if area_values and max(area_values) >= 1.8 * max(1.0, min(area_values)):
        codes.add("split_merge_review")
    if not codes:
        codes.add("spatially_related")
    return sorted(codes)


def _suggested_action(issue_codes: Sequence[str]) -> str:
    codes = set(issue_codes)
    if "possible_duplicate" in codes:
        return "review_duplicate_or_merge"
    if "split_merge_review" in codes:
        return "review_split_merge"
    return "review_cluster_context"


def _centroid_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    return math.hypot(float(left["centroid_x"]) - float(right["centroid_x"]), float(left["centroid_y"]) - float(right["centroid_y"]))


def _bbox_iou(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    left_x0 = float(left["bbox_x"])
    left_y0 = float(left["bbox_y"])
    left_x1 = left_x0 + float(left["bbox_width_px"])
    left_y1 = left_y0 + float(left["bbox_height_px"])
    right_x0 = float(right["bbox_x"])
    right_y0 = float(right["bbox_y"])
    right_x1 = right_x0 + float(right["bbox_width_px"])
    right_y1 = right_y0 + float(right["bbox_height_px"])
    intersection_width = max(0.0, min(left_x1, right_x1) - max(left_x0, right_x0))
    intersection_height = max(0.0, min(left_y1, right_y1) - max(left_y0, right_y0))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left_x1 - left_x0) * max(0.0, left_y1 - left_y0)
    right_area = max(0.0, right_x1 - right_x0) * max(0.0, right_y1 - right_y0)
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0
