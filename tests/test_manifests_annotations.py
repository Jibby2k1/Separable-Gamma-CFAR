from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest


def test_annotation_v2_migrates_to_v3_without_losing_labels():
    from neurobench.annotations import migrate_annotations_v3

    migrated = migrate_annotations_v3(
        {
            "version": 2,
            "rois": {"7": {"state": "accept", "notes": "cell"}},
            "events": {"7:12": {"state": "reject", "notes": "noise"}},
            "settings": {"eventThreshold": 2.4},
        }
    )

    assert migrated["schema_version"] == 3
    assert migrated["rois"]["7"]["cell_state"] == "accepted"
    assert migrated["rois"]["7"]["notes"] == "cell"
    assert migrated["events"]["7:12"]["event_state"] == "rejected"
    assert migrated["settings"]["eventThreshold"] == 2.4


def test_manifest_relative_paths_resolve():
    from neurobench.manifests import load_dataset_manifest, manifest_path

    with TemporaryDirectory() as td:
        tmp_path = Path(td)
        raw = tmp_path / "raw.tif"
        raw.write_bytes(b"fixture")
        manifest_path_file = tmp_path / "dataset.json"
        manifest_path_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "dataset_id": "unit",
                    "paths": {"raw_video": "raw.tif", "app_dir": "app", "review_data": "app/review_data.json"},
                }
            )
        )

        manifest = load_dataset_manifest(manifest_path_file)

        assert manifest_path(manifest, "raw_video") == raw.resolve()


class ManifestAnnotationTests(unittest.TestCase):
    def test_annotation_v2_migrates_to_v3_without_losing_labels(self):
        test_annotation_v2_migrates_to_v3_without_losing_labels()

    def test_manifest_relative_paths_resolve(self):
        test_manifest_relative_paths_resolve()


if __name__ == "__main__":
    unittest.main()
