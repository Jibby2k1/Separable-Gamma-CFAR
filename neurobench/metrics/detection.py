"""Object-level candidate matching metrics.

These metrics evaluate candidate neuron footprints as objects rather than as
individual pixels. They are intentionally small and dependency-light so they can
run in CPU-only test and reporting workflows.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


Point = tuple[int, int]


def spatial_iou(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Return footprint IoU for two object records.

    Supported footprint encodings:
    - ``pixels``: sequence of ``(x, y)`` pairs or mappings with ``x``/``y``.
    - ``mask``: 2D boolean/integer nested sequence where nonzero values belong
      to the object.
    - ``bbox``: ``[x, y, width, height]``.
    - ``x_min/y_min/x_max/y_max`` or ``xmin/ymin/xmax/ymax``.
    """

    pixels_a = object_pixels(a)
    pixels_b = object_pixels(b)
    if not pixels_a and not pixels_b:
        return 0.0
    intersection = len(pixels_a & pixels_b)
    union = len(pixels_a | pixels_b)
    return intersection / union if union else 0.0


def centroid_distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Return Euclidean centroid distance in pixels."""

    ax, ay = object_centroid(a)
    bx, by = object_centroid(b)
    return math.hypot(ax - bx, ay - by)


def match_candidate_objects(
    ground_truth: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    *,
    iou_threshold: float = 0.25,
    centroid_tolerance_px: float | None = None,
) -> dict[str, Any]:
    """Greedily match candidate objects to ground truth objects.

    A pair is eligible when it meets the IoU threshold, or when
    ``centroid_tolerance_px`` is supplied and the centroids are close enough.
    Matching is one-to-one, preferring highest IoU and then shortest centroid
    distance. Extra eligible candidates become duplicate evidence rather than
    additional true positives.
    """

    gt = [dict(item) for item in ground_truth]
    pred = [dict(item) for item in candidates]
    pair_scores: list[dict[str, Any]] = []
    eligible_by_gt = {idx: [] for idx in range(len(gt))}
    eligible_by_candidate = {idx: [] for idx in range(len(pred))}

    for gt_idx, gt_obj in enumerate(gt):
        for candidate_idx, candidate in enumerate(pred):
            iou = spatial_iou(gt_obj, candidate)
            distance = centroid_distance(gt_obj, candidate)
            eligible = iou >= iou_threshold
            if centroid_tolerance_px is not None and distance <= centroid_tolerance_px:
                eligible = True
            pair = {
                "gt_index": gt_idx,
                "candidate_index": candidate_idx,
                "gt_id": object_id(gt_obj, gt_idx),
                "candidate_id": object_id(candidate, candidate_idx),
                "iou": iou,
                "centroid_distance_px": distance,
                "eligible": eligible,
            }
            if eligible:
                pair_scores.append(pair)
                eligible_by_gt[gt_idx].append(candidate_idx)
                eligible_by_candidate[candidate_idx].append(gt_idx)

    pair_scores.sort(key=lambda item: (-float(item["iou"]), float(item["centroid_distance_px"])))
    matched_gt: set[int] = set()
    matched_candidates: set[int] = set()
    matches: list[dict[str, Any]] = []
    for pair in pair_scores:
        gt_idx = int(pair["gt_index"])
        candidate_idx = int(pair["candidate_index"])
        if gt_idx in matched_gt or candidate_idx in matched_candidates:
            continue
        matched_gt.add(gt_idx)
        matched_candidates.add(candidate_idx)
        matches.append(pair)

    false_negatives = [
        {"gt_index": idx, "gt_id": object_id(obj, idx)}
        for idx, obj in enumerate(gt)
        if idx not in matched_gt
    ]
    false_positives = [
        {"candidate_index": idx, "candidate_id": object_id(obj, idx)}
        for idx, obj in enumerate(pred)
        if idx not in matched_candidates
    ]
    duplicate_candidates = sorted(
        idx for idx, gt_indices in eligible_by_candidate.items() if idx not in matched_candidates and gt_indices
    )
    split_ground_truth = sorted(idx for idx, candidate_indices in eligible_by_gt.items() if len(candidate_indices) > 1)
    merged_candidates = sorted(idx for idx, gt_indices in eligible_by_candidate.items() if len(gt_indices) > 1)

    return {
        "matches": matches,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "duplicate_candidate_indices": duplicate_candidates,
        "split_ground_truth_indices": split_ground_truth,
        "merged_candidate_indices": merged_candidates,
        "eligible_pair_count": len(pair_scores),
    }


def object_matching_metrics(
    ground_truth: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    *,
    iou_threshold: float = 0.25,
    centroid_tolerance_px: float | None = None,
) -> dict[str, Any]:
    """Return object-level precision/recall and matching diagnostics."""

    result = match_candidate_objects(
        ground_truth,
        candidates,
        iou_threshold=iou_threshold,
        centroid_tolerance_px=centroid_tolerance_px,
    )
    tp = len(result["matches"])
    fp = len(result["false_positives"])
    fn = len(result["false_negatives"])
    candidate_count = len(candidates)
    gt_count = len(ground_truth)
    mean_iou = _mean(match["iou"] for match in result["matches"])
    mean_distance = _mean(match["centroid_distance_px"] for match in result["matches"])
    metrics = {
        "object_count_gt": gt_count,
        "object_count_candidate": candidate_count,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "object_precision": tp / candidate_count if candidate_count else 0.0,
        "object_recall": tp / gt_count if gt_count else 0.0,
        "mean_matched_iou": mean_iou,
        "mean_matched_centroid_distance_px": mean_distance,
        "duplicate_candidate_count": len(result["duplicate_candidate_indices"]),
        "duplicate_rate": len(result["duplicate_candidate_indices"]) / candidate_count if candidate_count else 0.0,
        "split_ground_truth_count": len(result["split_ground_truth_indices"]),
        "split_rate": len(result["split_ground_truth_indices"]) / gt_count if gt_count else 0.0,
        "merged_candidate_count": len(result["merged_candidate_indices"]),
        "merge_rate": len(result["merged_candidate_indices"]) / candidate_count if candidate_count else 0.0,
        "matches": result["matches"],
        "false_positives": result["false_positives"],
        "false_negatives": result["false_negatives"],
    }
    return metrics


def object_pixels(obj: Mapping[str, Any]) -> set[Point]:
    if "pixels" in obj:
        return _pixels_from_sequence(obj["pixels"])
    if "mask" in obj:
        return _pixels_from_mask(obj["mask"])
    bbox = _bbox_from_object(obj)
    if bbox is not None:
        x, y, width, height = bbox
        return {
            (px, py)
            for py in range(y, y + height)
            for px in range(x, x + width)
        }
    return set()


def object_centroid(obj: Mapping[str, Any]) -> tuple[float, float]:
    centroid = obj.get("centroid")
    if isinstance(centroid, Sequence) and not isinstance(centroid, (str, bytes, bytearray)) and len(centroid) >= 2:
        return float(centroid[0]), float(centroid[1])
    for x_key, y_key in (
        ("centroid_x", "centroid_y"),
        ("centroidX", "centroidY"),
        ("x", "y"),
    ):
        if x_key in obj and y_key in obj:
            return float(obj[x_key]), float(obj[y_key])
    pixels = object_pixels(obj)
    if pixels:
        return _centroid_from_pixels(pixels)
    raise ValueError(f"Object is missing centroid or footprint: {obj!r}")


def object_id(obj: Mapping[str, Any], fallback_index: int) -> str:
    for key in ("id", "object_id", "roi_id", "candidate_id", "gt_id"):
        if key in obj:
            return str(obj[key])
    return str(fallback_index)


def _bbox_from_object(obj: Mapping[str, Any]) -> tuple[int, int, int, int] | None:
    if "bbox" in obj:
        bbox = obj["bbox"]
        if isinstance(bbox, Mapping):
            x = bbox.get("x", bbox.get("xmin", bbox.get("x_min")))
            y = bbox.get("y", bbox.get("ymin", bbox.get("y_min")))
            width = bbox.get("width", bbox.get("w"))
            height = bbox.get("height", bbox.get("h"))
            if width is not None and height is not None and x is not None and y is not None:
                return int(x), int(y), int(width), int(height)
        if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes, bytearray)) and len(bbox) >= 4:
            return int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    x_min = obj.get("x_min", obj.get("xmin"))
    y_min = obj.get("y_min", obj.get("ymin"))
    x_max = obj.get("x_max", obj.get("xmax"))
    y_max = obj.get("y_max", obj.get("ymax"))
    if None not in (x_min, y_min, x_max, y_max):
        x = int(x_min)
        y = int(y_min)
        return x, y, max(0, int(x_max) - x), max(0, int(y_max) - y)
    return None


def _pixels_from_sequence(raw_pixels: Any) -> set[Point]:
    pixels = set()
    for point in raw_pixels or []:
        if isinstance(point, Mapping):
            pixels.add((int(point["x"]), int(point["y"])))
        else:
            pixels.add((int(point[0]), int(point[1])))
    return pixels


def _pixels_from_mask(mask: Any) -> set[Point]:
    pixels = set()
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if bool(value):
                pixels.add((int(x), int(y)))
    return pixels


def _centroid_from_pixels(pixels: set[Point]) -> tuple[float, float]:
    count = len(pixels)
    return sum(x for x, _y in pixels) / count, sum(y for _x, y in pixels) / count


def _mean(values: Any) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0
