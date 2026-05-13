import pytest

from neurobench.metrics import (
    event_correlation_summary,
    event_raster_summary,
    population_activity_summary,
    population_time_series_summary,
    trace_correlation_summary,
)


def test_event_raster_summary_bins_events_deterministically():
    events = [
        {"roi_id": "b", "frame": 1},
        {"roi_id": "a", "start_frame": 1},
        {"roi_id": "a", "onset_frame": 3},
        {"roi_id": "b", "frame": 4},
        {"roi_id": "outside", "frame": 8},
    ]

    summary = event_raster_summary(events, frame_count=6, bin_size_frames=2, object_ids=["a", "b"])

    assert summary["schema_version"] == 1
    assert summary["summary_type"] == "event_raster"
    assert summary["parameters"] == {"frame_count": 6, "bin_size_frames": 2}
    assert summary["object_ids"] == ["a", "b"]
    assert summary["bin_edges"] == [[0, 2], [2, 4], [4, 6]]
    assert summary["raster"] == [[1, 1, 0], [1, 0, 1]]
    assert summary["dropped_event_count"] == 1
    assert summary["rows"] == [
        {"object_id": "a", "event_count": 2, "active_bin_count": 2},
        {"object_id": "b", "event_count": 2, "active_bin_count": 2},
    ]


def test_population_activity_summary_reports_activity_curves():
    events = [
        {"roi_id": "b", "frame": 1},
        {"roi_id": "a", "frame": 1},
        {"roi_id": "a", "frame": 3},
        {"roi_id": "b", "frame": 4},
    ]

    summary = population_activity_summary(events, frame_count=6, bin_size_frames=2)

    assert summary["schema_version"] == 1
    assert summary["summary_type"] == "population_activity"
    assert summary["total_event_count_by_bin"] == [2, 1, 1]
    assert summary["active_object_count_by_bin"] == [2, 1, 1]
    assert summary["active_fraction_by_bin"] == [1.0, 0.5, 0.5]
    assert summary["mean_events_per_active_object_by_bin"] == [1.0, 1.0, 1.0]
    assert summary["coactive_bin_count"] == 1
    assert summary["peak_bin_index"] == 0
    assert summary["peak_event_count"] == 2


def test_event_correlation_summary_uses_binned_raster():
    events = [
        {"roi_id": "a", "frame": 1},
        {"roi_id": "a", "frame": 3},
        {"roi_id": "b", "frame": 1},
        {"roi_id": "b", "frame": 4},
    ]

    summary = event_correlation_summary(events, frame_count=6, bin_size_frames=2)

    assert summary["schema_version"] == 1
    assert summary["summary_type"] == "event_correlation"
    assert summary["object_ids"] == ["a", "b"]
    assert summary["correlation_matrix"][0][0] == 1.0
    assert summary["correlation_matrix"][1][1] == 1.0
    assert summary["correlation_matrix"][0][1] == pytest.approx(-0.5)
    assert summary["correlation_matrix"][1][0] == pytest.approx(-0.5)
    assert summary["pairwise_correlations"] == [
        {"object_id_a": "a", "object_id_b": "b", "correlation": pytest.approx(-0.5)}
    ]
    assert summary["statistics"] == {
        "pair_count": 1,
        "undefined_pair_count": 0,
        "mean_correlation": pytest.approx(-0.5),
        "min_correlation": pytest.approx(-0.5),
        "max_correlation": pytest.approx(-0.5),
    }


def test_trace_correlation_summary_handles_mapping_and_constant_traces():
    traces = {
        "b": [2.0, 1.0, 0.0],
        "a": [0.0, 1.0, 2.0],
        "c": [5.0, 5.0, 5.0],
    }

    summary = trace_correlation_summary(traces)

    assert summary["schema_version"] == 1
    assert summary["summary_type"] == "trace_correlation"
    assert summary["object_ids"] == ["a", "b", "c"]
    assert summary["correlation_matrix"] == [
        [1.0, pytest.approx(-1.0), 0.0],
        [pytest.approx(-1.0), 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    assert summary["statistics"]["pair_count"] == 3
    assert summary["statistics"]["undefined_pair_count"] == 2
    assert summary["statistics"]["mean_correlation"] == pytest.approx(-1.0 / 3.0)


def test_population_time_series_summary_combines_event_and_trace_outputs():
    events = [{"roi_id": "a", "frame": 0}, {"roi_id": "b", "frame": 1}]
    traces = [{"roi_id": "a", "trace": [0, 1]}, {"roi_id": "b", "trace": [1, 0]}]

    summary = population_time_series_summary(
        events=events,
        traces=traces,
        frame_count=2,
        bin_size_frames=1,
    )

    assert summary["schema_version"] == 1
    assert summary["summary_type"] == "population_time_series"
    assert summary["event_raster"]["raster"] == [[1, 0], [0, 1]]
    assert summary["population_activity"]["total_event_count_by_bin"] == [1, 1]
    assert summary["event_correlation"]["correlation_matrix"][0][1] == pytest.approx(-1.0)
    assert summary["trace_correlation"]["correlation_matrix"][0][1] == pytest.approx(-1.0)
