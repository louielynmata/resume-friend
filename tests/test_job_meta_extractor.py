import asyncio
import unittest
from unittest import mock

from backend.services.job_meta_extractor import extract_job_meta


class JobMetaExtractorTests(unittest.TestCase):
    def test_extracted_location_is_normalized_without_persisting_a_catalog(self):
        text = """Job title: Product Designer
Company: Example Studio
Location: Calgary, AB (Hybrid)
"""

        with mock.patch(
            "backend.services.job_meta_extractor._ai_available", return_value=False
        ):
            result = asyncio.run(extract_job_meta(text))

        self.assertEqual(result["location"], "Calgary")


if __name__ == "__main__":
    unittest.main()
