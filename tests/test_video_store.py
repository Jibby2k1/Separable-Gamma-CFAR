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


class VideoStoreTests(unittest.TestCase):
    def test_video_store_wraps_array_and_iterates_frame_chunks(self):
        require_numpy()
        from neurobench.data.video import VideoStore

        video = np.arange(5 * 3 * 4, dtype=np.float32).reshape(5, 3, 4)
        store = VideoStore.from_array(video)
        chunks = list(store.iter_chunks(2))

        self.assertEqual(store.shape, (5, 3, 4))
        self.assertEqual(store.frame_count, 5)
        self.assertEqual(store.height, 3)
        self.assertEqual(store.width, 4)
        self.assertEqual(store.metadata()["storage_mode"], "array")
        self.assertEqual([(chunk.start_frame, chunk.end_frame, chunk.frame_count) for chunk in chunks], [(0, 2, 2), (2, 4, 2), (4, 5, 1)])
        np.testing.assert_array_equal(chunks[1].data, video[2:4])
        np.testing.assert_array_equal(store.frame(3), video[3])

    def test_video_store_opens_npy_as_memmap_by_default(self):
        require_numpy()
        from neurobench.data.video import open_video

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "video.npy"
            video = np.arange(6 * 2 * 3, dtype=np.float32).reshape(6, 2, 3)
            np.save(path, video)

            store = open_video(path)
            first_chunk = next(store.iter_chunks(4))
            np.testing.assert_array_equal(first_chunk.data, video[:4])

            self.assertEqual(store.shape, (6, 2, 3))
            self.assertEqual(store.dtype, np.dtype("float32"))
            self.assertEqual(store.storage_mode, "npy_memmap")
            self.assertEqual(store.metadata()["source_path"], str(path))

    def test_video_store_rejects_invalid_shape_and_chunk_size(self):
        require_numpy()
        from neurobench.data.video import VideoStore

        with self.assertRaisesRegex(ValueError, "at least 3 dimensions"):
            VideoStore.from_array(np.zeros((4, 5), dtype=np.float32))

        store = VideoStore.from_array(np.zeros((3, 4, 5), dtype=np.float32))
        with self.assertRaisesRegex(ValueError, "chunk_size must be positive"):
            list(store.iter_chunks(0))
        with self.assertRaisesRegex(IndexError, "outside"):
            store.frame(3)

    def test_dataset_qc_accepts_video_store(self):
        require_numpy()
        from neurobench.data.qc import compute_video_qc
        from neurobench.data.video import VideoStore

        store = VideoStore.from_array(np.ones((3, 4, 5), dtype=np.float32), source_path="synthetic.npy")
        qc = compute_video_qc(store, dataset_id="video_store")

        self.assertEqual(qc["dataset_id"], "video_store")
        self.assertEqual(qc["video"]["shape"], [3, 4, 5])
        self.assertEqual(qc["video"]["storage_mode"], "array")
        self.assertEqual(qc["video"]["source_path"], "synthetic.npy")


if __name__ == "__main__":
    unittest.main()
