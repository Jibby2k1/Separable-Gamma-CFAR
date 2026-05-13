from __future__ import annotations

import unittest
from pathlib import Path

from tools.generate_api_reference import collect_public_api, render_reference, write_reference


ROOT = Path(__file__).resolve().parents[1]


class ApiReferenceGenerationTests(unittest.TestCase):
    def test_collects_public_exports_from_all_declarations(self):
        packages = collect_public_api(ROOT)
        entries = {
            (entry.package, entry.name): entry
            for package in packages
            for entry in package.entries
        }

        self.assertIn(("neurobench.algorithms", "gamma_cfar_mask"), entries)
        self.assertIn(("neurobench.data", "SyntheticDataset"), entries)
        self.assertIn(("neurobench.pipelines", "ArtifactStore"), entries)
        self.assertEqual(entries[("neurobench.algorithms", "gamma_cfar_mask")].kind, "function")
        self.assertEqual(entries[("neurobench.data", "SyntheticDataset")].kind, "class")
        self.assertIn("gamma_cfar_mask(video", entries[("neurobench.algorithms", "gamma_cfar_mask")].signature)
        self.assertIn("neurobench.data.synthetic", entries[("neurobench.data", "SyntheticDataset")].module)

    def test_rendered_reference_documents_offline_generation_contract(self):
        text = render_reference(collect_public_api(ROOT))

        self.assertIn("# Neurobench API Reference", text)
        self.assertIn("local source files only", text)
        self.assertIn("does not need internet access", text)
        self.assertIn("raw video data", text)
        self.assertIn("`__all__` declarations", text)
        self.assertIn("## `neurobench.algorithms`", text)
        self.assertIn("### `gamma_cfar_mask`", text)
        self.assertIn("- Source: `neurobench.algorithms.cfar`", text)

    def test_checked_in_reference_matches_generator_output(self):
        expected = (ROOT / "docs" / "API_REFERENCE.md").read_text(encoding="utf-8")
        actual = render_reference(collect_public_api(ROOT))

        self.assertEqual(expected, actual)

    def test_write_reference_supports_temporary_output_path(self):
        out = ROOT / "docs" / ".api_reference_test.md"
        try:
            written = write_reference(ROOT, out)

            self.assertEqual(written, out)
            self.assertIn("### `gamma_cfar_mask`", out.read_text(encoding="utf-8"))
        finally:
            out.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
