from __future__ import annotations

import json
import unittest
from unittest.mock import patch

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


def test_cpu_import_smoke():
    require_numpy()
    import core.filters  # noqa: F401
    import worker  # noqa: F401


def test_numpy_encoder_preserves_integer_ids():
    require_numpy()
    from utils import NumpyEncoder

    encoded = json.dumps({"id": np.int64(7), "score": np.float32(1.25)}, cls=NumpyEncoder)
    decoded = json.loads(encoded)

    assert decoded["id"] == 7
    assert isinstance(decoded["id"], int)
    assert decoded["score"] == 1.25


def test_component_detections_return_one_detection_per_blob():
    require_numpy()
    from utils import extract_component_detections

    mask = np.zeros((1, 8, 8), dtype=np.uint8)
    mask[0, 1:3, 1:3] = 1
    mask[0, 5, 5] = 1
    mask[0, 5, 6] = 1

    detections = extract_component_detections(mask, min_area=2)

    assert list(detections) == [0]
    assert len(detections[0]) == 2
    assert sorted(d["area"] for d in detections[0]) == [2, 4]


def test_component_detections_filter_small_speckles():
    require_numpy()
    from utils import extract_component_detections

    mask = np.zeros((1, 8, 8), dtype=np.uint8)
    mask[0, 1:3, 1:3] = 1
    mask[0, 6, 6] = 1

    detections = extract_component_detections(mask, min_area=2)

    assert len(detections[0]) == 1
    assert detections[0][0]["area"] == 4


def test_metric_helpers_accept_canonical_and_legacy_keys():
    require_numpy()
    from evaluation.metrics import calculate_truncated_auc, metric_value

    assert metric_value({"TPR": 1.0}, "TPR") == 1.0
    assert metric_value({"tpr": 0.5}, "TPR") == 0.5
    assert calculate_truncated_auc([{"fppi": 0.0, "tpr": 0.0}, {"FPPI": 1.0, "TPR": 1.0}], 1.0) == 0.5


def test_truncated_auc_preserves_limit_extension_behavior():
    require_numpy()
    from evaluation.metrics import calculate_truncated_auc

    points = [
        {"FPPI": 0.0, "TPR": 0.0},
        {"FPPI": 0.5, "TPR": 0.5},
        {"FPPI": 2.0, "TPR": 1.0},
    ]

    assert calculate_truncated_auc(points, 1.0) == 0.375


def test_worker_records_nonzero_canonical_tpr():
    require_numpy()
    import torch
    import worker

    z_map = np.zeros((1, 5, 5), dtype=np.float32)
    z_map[0, 2, 3] = 5.0

    def fake_run_single_stage(**kwargs):
        return {"z1": z_map}

    params = {
        "arch": "single",
        "varied_param": {"filter_type": "gamma"},
        "st1": {},
        "cfar1_params": {},
        "neighborhood_config": (1, 1),
        "distance_tolerance": 0.1,
    }
    gt_data = {0: [(3.0, 2.0, 1)]}

    with patch.object(worker, "run_single_stage", fake_run_single_stage), patch.object(
        worker, "apply_neighborhood_filter", lambda mask, _k, _size: mask
    ), patch.object(torch.cuda, "is_available", lambda: False):
        result = worker.process_full_task_for_worker(((z_map * 0), params, [4.0], gt_data, z_map.shape))

    point = result["roc_points"][0]
    assert point["TPR"] == 1.0
    assert point["tpr"] == 1.0
    assert point["FPPI"] == 0.0


class CorrectnessFoundationTests(unittest.TestCase):
    def test_cpu_import_smoke(self):
        test_cpu_import_smoke()

    def test_numpy_encoder_preserves_integer_ids(self):
        if np is None:
            self.skipTest("numpy is not installed in this Python environment")
        test_numpy_encoder_preserves_integer_ids()

    def test_component_detections_return_one_detection_per_blob(self):
        if np is None:
            self.skipTest("numpy is not installed in this Python environment")
        test_component_detections_return_one_detection_per_blob()

    def test_component_detections_filter_small_speckles(self):
        if np is None:
            self.skipTest("numpy is not installed in this Python environment")
        test_component_detections_filter_small_speckles()

    def test_metric_helpers_accept_canonical_and_legacy_keys(self):
        test_metric_helpers_accept_canonical_and_legacy_keys()

    def test_truncated_auc_preserves_limit_extension_behavior(self):
        if np is None:
            self.skipTest("numpy is not installed in this Python environment")
        test_truncated_auc_preserves_limit_extension_behavior()

    def test_worker_records_nonzero_canonical_tpr(self):
        if np is None:
            self.skipTest("numpy is not installed in this Python environment")
        test_worker_records_nonzero_canonical_tpr()


if __name__ == "__main__":
    unittest.main()
