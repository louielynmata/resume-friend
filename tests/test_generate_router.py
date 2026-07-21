import tempfile
import unittest
from pathlib import Path

from backend.routers.generate import _create_run_output_dir


class GenerateRouterTests(unittest.TestCase):
    def test_same_day_runs_use_distinct_output_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ExampleCompany_ProductDesigner_2026-07-21"

            first = _create_run_output_dir(base)
            (first / "qa_report.json").write_text("{}", encoding="utf-8")
            second = _create_run_output_dir(base)
            third = _create_run_output_dir(base)

            self.assertEqual(first, base)
            self.assertEqual(second.name, f"{base.name}_2")
            self.assertEqual(third.name, f"{base.name}_3")
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertTrue(third.is_dir())

    def test_existing_empty_folder_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ExampleCompany_ProductDesigner_2026-07-21"
            base.mkdir()

            resolved = _create_run_output_dir(base)

            self.assertEqual(resolved.name, f"{base.name}_2")


if __name__ == "__main__":
    unittest.main()
