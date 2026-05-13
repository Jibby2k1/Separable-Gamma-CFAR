from __future__ import annotations

import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


def require_numpy():
    if np is None:
        raise unittest.SkipTest("numpy is not installed in this Python environment")


class ChunkedProcessingTests(unittest.TestCase):
    def test_chunked_cfar_matches_full_video_outputs(self):
        require_numpy()
        from neurobench.algorithms.cfar import robust_local_cfar
        from neurobench.algorithms.chunking import process_independent_frame_chunks
        from neurobench.data.synthetic import generate_synthetic_calcium_dataset

        dataset = generate_synthetic_calcium_dataset(frames=13, height=28, width=30, include_impulse_artifact=False)
        params = {"pfa": 0.08, "guard_px": 1, "training_radius_px": 4, "epsilon": 1e-6}
        full = robust_local_cfar(dataset.video, **params)
        chunked = process_independent_frame_chunks(
            dataset.video,
            lambda chunk: robust_local_cfar(chunk, **params),
            chunk_size=5,
            concatenate_keys=("mask", "score", "local_mean", "local_std"),
        )

        np.testing.assert_array_equal(chunked["mask"], full["mask"])
        np.testing.assert_allclose(chunked["score"], full["score"], rtol=0, atol=0)
        np.testing.assert_allclose(chunked["local_mean"], full["local_mean"], rtol=0, atol=0)
        np.testing.assert_allclose(chunked["local_std"], full["local_std"], rtol=0, atol=0)
        self.assertEqual(
            chunked["chunk_ranges"],
            [
                {"start_frame": 0, "end_frame": 5},
                {"start_frame": 5, "end_frame": 10},
                {"start_frame": 10, "end_frame": 13},
            ],
        )

    def test_chunked_processing_accepts_video_store_input(self):
        require_numpy()
        from neurobench.algorithms.chunking import process_independent_frame_chunks
        from neurobench.data.video import VideoStore

        video = np.arange(7 * 3 * 4, dtype=np.float32).reshape(7, 3, 4)
        store = VideoStore.from_array(video)
        result = process_independent_frame_chunks(
            store,
            lambda chunk: {"identity": chunk.astype(np.float32, copy=False)},
            chunk_size=3,
            concatenate_keys=("identity",),
        )

        np.testing.assert_array_equal(result["identity"], video)
        self.assertEqual(result["chunk_ranges"][-1], {"start_frame": 6, "end_frame": 7})

    def test_chunked_processing_validates_processor_contract(self):
        require_numpy()
        from neurobench.algorithms.chunking import process_independent_frame_chunks

        video = np.zeros((4, 5, 6), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "chunk_size must be positive"):
            process_independent_frame_chunks(video, lambda chunk: {"x": chunk}, chunk_size=0, concatenate_keys=("x",))
        with self.assertRaisesRegex(ValueError, "concatenate_keys"):
            process_independent_frame_chunks(video, lambda chunk: {"x": chunk}, chunk_size=2, concatenate_keys=())
        with self.assertRaisesRegex(KeyError, "missing key 'x'"):
            process_independent_frame_chunks(video, lambda chunk: {"y": chunk}, chunk_size=2, concatenate_keys=("x",))
        with self.assertRaisesRegex(ValueError, "first dimension"):
            process_independent_frame_chunks(
                video,
                lambda chunk: {"x": np.zeros((1, 5, 6), dtype=np.float32)},
                chunk_size=2,
                concatenate_keys=("x",),
            )


if __name__ == "__main__":
    unittest.main()
