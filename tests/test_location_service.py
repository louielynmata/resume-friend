import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_location_service(test_case: unittest.TestCase):
    module_name = "backend.services.location_service"
    test_case.assertIsNotNone(
        importlib.util.find_spec(module_name),
        "The canonical location service has not been implemented.",
    )
    return importlib.import_module(module_name)


class LocationNormalizerTests(unittest.TestCase):
    def test_raw_location_examples_resolve_to_one_canonical_value(self):
        module = _load_location_service(self)
        cases = {
            "Calgary, AB (Hybrid)": "Calgary",
            "calgary": "Calgary",
            "Remote - Canada": "Remote",
            "Toronto / Remote": "Remote",
            "New York, NY": "New York",
            "Location:  Fort   McMurray | Canada": "Fort McMurray",
            "St. John's, NL": "St. John's",
            "L'Île-d'Orléans, QC": "L'Île-d'Orléans",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(module.normalize_location(raw), expected)

    def test_rejects_empty_arrangement_only_numeric_and_implausible_values(self):
        module = _load_location_service(self)

        for raw in ("", "   ", "Hybrid", "On-site", "12345", "Canada", "@@@"):
            with self.subTest(raw=raw):
                self.assertIsNone(module.normalize_location(raw))

    def test_catalog_creates_seed_reuses_spelling_and_prevents_case_duplicates(self):
        module = _load_location_service(self)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "normalized_locations.json"
            catalog = module.LocationCatalog(path)

            self.assertEqual(catalog.list_locations(), ["Remote"])
            first = catalog.normalize("Fort McMurray", persist=True)
            second = catalog.normalize(" fort mcmurray ", persist=True)

            self.assertTrue(path.is_file())
            self.assertTrue(first.added)
            self.assertFalse(second.added)
            self.assertEqual(second.normalized, "Fort McMurray")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"locations": ["Remote", "Fort McMurray"]},
            )

    def test_preview_and_invalid_values_do_not_pollute_the_catalog(self):
        module = _load_location_service(self)
        with tempfile.TemporaryDirectory() as tmp:
            catalog = module.LocationCatalog(Path(tmp) / "normalized_locations.json")

            preview = catalog.normalize("Calgary, AB", persist=False)
            invalid = catalog.normalize("Hybrid", persist=True)

            self.assertEqual(preview.normalized, "Calgary")
            self.assertFalse(preview.added)
            self.assertIsNone(invalid.normalized)
            self.assertEqual(catalog.list_locations(), ["Remote"])

    def test_malformed_catalog_is_reported_and_not_overwritten(self):
        module = _load_location_service(self)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "normalized_locations.json"
            path.write_text("not json", encoding="utf-8")
            catalog = module.LocationCatalog(path)

            with self.assertRaises(module.LocationCatalogError):
                catalog.list_locations()

            self.assertEqual(path.read_text(encoding="utf-8"), "not json")


if __name__ == "__main__":
    unittest.main()
