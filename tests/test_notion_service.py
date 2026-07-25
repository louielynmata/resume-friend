import unittest
from unittest.mock import AsyncMock, patch

from backend.services.notion_service import log_application


class NotionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_log_application_writes_status_as_single_select(self):
        create_page = AsyncMock(return_value={"url": "https://notion.example/page"})
        with (
            patch("notion_client.AsyncClient") as client_class,
            patch(
                "backend.services.notion_service.settings.notion_database_id",
                "database-id",
            ),
        ):
            client_class.return_value.pages.create = create_page

            result = await log_application(
                position="Software Developer",
                company="Example Company",
                folder_name="example-company-software-developer",
            )

        self.assertEqual(result, "https://notion.example/page")
        properties = create_page.await_args.kwargs["properties"]
        self.assertEqual(
            properties["Status"],
            {"select": {"name": "Applied"}},
        )
        self.assertNotIn("multi_select", properties["Status"])


if __name__ == "__main__":
    unittest.main()
