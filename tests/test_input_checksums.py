from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path


class InputChecksumTests(unittest.TestCase):
    def test_sha256_path_matches_hashlib(self):
        from neurobench.data.checksums import sha256_path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.tif"
            path.write_bytes(b"calcium frames")

            self.assertEqual(sha256_path(path), hashlib.sha256(b"calcium frames").hexdigest())

    def test_checksum_file_records_path_id_size_and_relative_path(self):
        from neurobench.data.checksums import checksum_file

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "inputs" / "raw.tif"
            path.parent.mkdir()
            path.write_bytes(b"abc")

            record = checksum_file(path, path_id="raw_video", base_dir=root)

            self.assertEqual(record["path_id"], "raw_video")
            self.assertEqual(record["path"], "inputs/raw.tif")
            self.assertEqual(record["size_bytes"], 3)
            self.assertEqual(record["sha256"], hashlib.sha256(b"abc").hexdigest())

    def test_dataset_input_checksums_selects_input_paths_and_skips_outputs(self):
        from neurobench.data.checksums import dataset_input_checksums

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.tif"
            labels = root / "labels.json"
            review_data = root / "app" / "review_data.json"
            raw.write_bytes(b"raw")
            labels.write_text("{}", encoding="utf-8")
            review_data.parent.mkdir()
            review_data.write_text("{}", encoding="utf-8")
            manifest = {
                "schema_version": 1,
                "dataset_id": "sample",
                "_manifest_dir": str(root),
                "paths": {
                    "raw_video": "raw.tif",
                    "labels": "labels.json",
                    "review_data": "app/review_data.json",
                    "app_dir": "app",
                },
            }

            records = dataset_input_checksums(manifest)

            self.assertEqual([record["path_id"] for record in records], ["raw_video", "labels"])
            self.assertEqual([record["path"] for record in records], ["raw.tif", "labels.json"])

    def test_dataset_input_checksums_can_use_explicit_path_keys(self):
        from neurobench.data.checksums import dataset_input_checksums

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "calibration.dat"
            path.write_text("gain=1.0", encoding="utf-8")
            manifest = {"_manifest_dir": str(root), "paths": {"calibration": "calibration.dat"}}

            records = dataset_input_checksums(manifest, path_keys=["calibration"])

            self.assertEqual(records[0]["path_id"], "calibration")

    def test_dataset_input_checksums_can_skip_missing_portable_inputs(self):
        from neurobench.data.checksums import dataset_input_checksums

        manifest = {"paths": {"raw_video": "not_checked_in.tif", "review_data": "app/review_data.json"}}

        self.assertEqual(dataset_input_checksums(manifest, require_exists=False), [])

    def test_dataset_input_checksums_raises_for_missing_required_input(self):
        from neurobench.data.checksums import dataset_input_checksums

        manifest = {"paths": {"raw_video": "not_checked_in.tif"}}

        with self.assertRaises(FileNotFoundError):
            dataset_input_checksums(manifest)


if __name__ == "__main__":
    unittest.main()
