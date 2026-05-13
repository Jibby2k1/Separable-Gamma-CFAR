from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


class RealtimeStreamTests(unittest.TestCase):
    def test_synthetic_frame_source_yields_timed_packets(self):
        require_numpy()
        from neurobench.realtime.stream import SyntheticFrameSource, collect_frame_packets

        source = SyntheticFrameSource(frames=5, height=8, width=9, frame_rate_hz=100.0, event_frame=2, seed=2)
        packets = collect_frame_packets(source)
        metadata = source.metadata()

        self.assertEqual(len(packets), 5)
        self.assertEqual([packet.frame_index for packet in packets], [0, 1, 2, 3, 4])
        self.assertEqual([packet.timestamp_sec for packet in packets], [0.0, 0.01, 0.02, 0.03, 0.04])
        self.assertEqual(packets[0].frame.shape, (8, 9))
        self.assertEqual(packets[0].frame.dtype, np.dtype("float32"))
        self.assertEqual(metadata["shape"], [5, 8, 9])
        self.assertEqual(metadata["frame_rate_hz"], 100.0)
        self.assertEqual(metadata["synthetic_event"]["frame"], 2)
        self.assertGreater(float(np.max(packets[2].frame)), float(np.max(packets[1].frame)))

    def test_video_frame_source_wraps_array_without_copying_contract(self):
        require_numpy()
        from neurobench.realtime.stream import VideoFrameSource

        video = np.arange(4 * 3 * 2, dtype=np.float32).reshape(4, 3, 2)
        source = VideoFrameSource(video, frame_rate_hz=20.0, source_id="array_source")
        packets = list(source)

        self.assertEqual(source.metadata()["duration_sec"], 0.2)
        self.assertEqual(packets[-1].source_id, "array_source")
        self.assertEqual(packets[-1].timestamp_sec, 0.15)
        np.testing.assert_array_equal(packets[-1].frame, video[-1])

    def test_video_frame_source_opens_npy_path(self):
        require_numpy()
        from neurobench.realtime.stream import VideoFrameSource

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stream.npy"
            video = np.ones((3, 4, 5), dtype=np.float32)
            np.save(path, video)
            source = VideoFrameSource.from_path(path, frame_rate_hz=10.0)
            packets = list(source)

            self.assertEqual(source.metadata()["storage_mode"], "npy_memmap")
            self.assertEqual(source.metadata()["source_id"], "stream")
            self.assertEqual(packets[2].timestamp_sec, 0.2)
            np.testing.assert_array_equal(packets[2].frame, video[2])

    def test_frame_sources_validate_inputs(self):
        require_numpy()
        from neurobench.realtime.stream import SyntheticFrameSource, VideoFrameSource

        with self.assertRaisesRegex(ValueError, "frame_rate_hz"):
            VideoFrameSource(np.zeros((2, 3, 4), dtype=np.float32), frame_rate_hz=0)
        with self.assertRaisesRegex(ValueError, "positive"):
            SyntheticFrameSource(frames=0)


if __name__ == "__main__":
    unittest.main()
