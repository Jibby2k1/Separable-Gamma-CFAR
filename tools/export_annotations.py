#!/usr/bin/env python3
"""Export migrated v3 annotations and simple ROI/event TSV files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.annotations import migrate_annotations_v3
from neurobench.manifests import load_json


def clean(value) -> str:
    return str(value if value is not None else "").replace("\t", " ").replace("\n", " ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Neurobench annotations.")
    parser.add_argument("--review-data", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    review = load_json(args.review_data)
    ann = migrate_annotations_v3(load_json(args.annotations))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "annotations_v3.json").write_text(json.dumps(ann, indent=2, sort_keys=True) + "\n")

    roi_rows = ["roi_id\troi_kind\tsource_roi_ids\tcell_state\ttrace_quality\tcontrol_ready\tartifact_class\tidentity_group\tneeds_action\tnotes"]
    for roi in review.get("rois", []):
        item = ann["rois"].get(str(roi.get("id")), {})
        roi_rows.append(
            "\t".join(
                [
                    clean(roi.get("id")),
                    "source",
                    "",
                    clean(item.get("cell_state", "")),
                    clean(item.get("trace_quality", "")),
                    clean(item.get("control_ready", "")),
                    clean(item.get("artifact_class", "")),
                    clean(item.get("identity_group", "")),
                    clean(item.get("needs_action", "")),
                    clean(item.get("notes", "")),
                ]
            )
        )
    for virtual in ann.get("virtualRois", {}).values():
        roi_rows.append(
            "\t".join(
                [
                    clean(virtual.get("id")),
                    clean(virtual.get("roi_kind", "virtual")),
                    clean(",".join(str(v) for v in virtual.get("source_roi_ids", []))),
                    clean(virtual.get("cell_state", "")),
                    clean(virtual.get("trace_quality", "")),
                    clean(virtual.get("control_ready", "")),
                    clean(virtual.get("artifact_class", "")),
                    clean(virtual.get("identity_group", "")),
                    "merge_needed" if virtual.get("roi_kind") == "virtual_merge" else "",
                    clean(virtual.get("notes", "")),
                ]
            )
        )
    (args.out_dir / "accepted_rois.tsv").write_text("\n".join(roi_rows) + "\n")

    event_rows = ["roi_id\tframe\tevent_state\tevent_type\ttiming_quality\tnotes"]
    for roi in review.get("rois", []):
        for event in roi.get("events", []):
            key = f"{roi.get('id')}:{event.get('frame')}"
            item = ann["events"].get(key, {})
            event_rows.append("\t".join([clean(roi.get("id")), clean(event.get("frame")), clean(item.get("event_state", "")), clean(item.get("event_type", "")), clean(item.get("timing_quality", "")), clean(item.get("notes", ""))]))
    (args.out_dir / "accepted_events.tsv").write_text("\n".join(event_rows) + "\n")
    print(f"Wrote annotation exports to {args.out_dir}")


if __name__ == "__main__":
    main()
