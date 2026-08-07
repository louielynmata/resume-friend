import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services.location_service import LocationCatalog


def _load_location_router(test_case: unittest.TestCase):
    module_name = "backend.routers.locations"
    test_case.assertIsNotNone(
        importlib.util.find_spec(module_name),
        "The location API router has not been implemented.",
    )
    return importlib.import_module(module_name)


class LocationRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalog_path = Path(self.temp_dir.name) / "normalized_locations.json"
        router_module = _load_location_router(self)
        app = FastAPI()
        app.include_router(router_module.router)
        app.dependency_overrides[router_module.get_location_catalog] = lambda: LocationCatalog(
            self.catalog_path
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_preview_and_persist_contracts(self):
        listed = self.client.get("/api/locations")
        preview = self.client.post(
            "/api/locations/normalize",
            json={"location": "Calgary, AB (Hybrid)", "persist": False},
        )
        persisted = self.client.post(
            "/api/locations/normalize",
            json={"location": "calgary", "persist": True},
        )

        self.assertEqual(listed.json(), {"locations": ["Remote"]})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["normalized"], "Calgary")
        self.assertFalse(preview.json()["added"])
        self.assertEqual(persisted.status_code, 200)
        self.assertTrue(persisted.json()["added"])
        self.assertEqual(persisted.json()["locations"], ["Remote", "Calgary"])

    def test_malformed_catalog_returns_an_actionable_error_without_replacing_it(self):
        self.catalog_path.write_text("not json", encoding="utf-8")

        response = self.client.get("/api/locations")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "LOCATION_CATALOG_INVALID")
        self.assertIn("normalized_locations.json", response.json()["detail"]["message"])
        self.assertEqual(self.catalog_path.read_text(encoding="utf-8"), "not json")


if __name__ == "__main__":
    unittest.main()
