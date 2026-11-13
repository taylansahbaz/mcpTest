from __future__ import annotations

import sys
import unittest
from pathlib import Path

import anyio
from mcp import Client
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import server  # noqa: E402


class DeviceDataToolTests(unittest.TestCase):
    def test_mcp_protocol_lists_tools_and_calls_data_range(self) -> None:
        async def scenario() -> tuple[set[str], dict[str, object] | None, bool]:
            async with Client(server.mcp) as client:
                tools = await client.list_tools()
                result = await client.call_tool("get_data_range", {})
                return (
                    {tool.name for tool in tools.tools},
                    result.structured_content,
                    result.is_error,
                )

        tool_names, data_range, is_error = anyio.run(scenario)

        self.assertEqual(
            {
                "list_devices",
                "get_data_range",
                "get_measurement_summary",
                "find_data_gaps",
                "find_threshold_violations",
                "find_duplicate_measurements",
                "get_latest_measurements",
                "get_daily_summary",
                "get_hourly_profile",
                "compare_devices",
                "get_measurement_percentiles",
                "get_correlation_analysis",
                "get_time_bucket_summary",
                "get_device_health_report",
                "list_device_events",
                "get_device_event_summary",
                "generate_device_event_report",
            },
            tool_names,
        )
        self.assertFalse(is_error)
        self.assertIsNotNone(data_range)
        self.assertEqual(35945, data_range["measurement_count"])

    def test_devices_and_data_range(self) -> None:
        devices = server.list_devices()
        data_range = server.get_data_range()

        self.assertEqual(5, devices["device_count"])
        self.assertEqual({"Ankara", "İstanbul", "İzmir"}, {row["location"] for row in devices["devices"]})
        self.assertEqual(35945, data_range["measurement_count"])
        self.assertEqual(5, data_range["device_count"])

    def test_known_demo_anomalies(self) -> None:
        gaps = server.find_data_gaps()
        violations = server.find_threshold_violations(limit=100)
        duplicates = server.find_duplicate_measurements(limit=100)

        self.assertEqual(1, gaps["gap_count"])
        self.assertEqual(60, gaps["missing_sample_count"])
        self.assertEqual("Cihaz-03", gaps["gaps"][0]["device_name"])
        self.assertEqual(30, violations["current_violation_count"])
        self.assertEqual(40, violations["temperature_violation_count"])
        self.assertEqual(5, duplicates["duplicate_group_count"])

    def test_reader_role_is_read_only(self) -> None:
        role = server._fetch_one(
            """
            SELECT current_user AS role_name,
                   current_setting('transaction_read_only')::boolean AS transaction_read_only,
                   has_table_privilege(current_user, 'public.measurements', 'SELECT') AS can_select,
                   has_table_privilege(current_user, 'public.measurements', 'INSERT') AS can_insert,
                   has_table_privilege(current_user, 'public.device_events', 'SELECT') AS can_select_events,
                   has_table_privilege(current_user, 'public.device_events', 'INSERT') AS can_insert_events
            """
        )

        self.assertEqual("mcp_demo_mcp_reader", role["role_name"])
        self.assertTrue(role["transaction_read_only"])
        self.assertTrue(role["can_select"])
        self.assertFalse(role["can_insert"])
        self.assertTrue(role["can_select_events"])
        self.assertFalse(role["can_insert_events"])

    def test_invalid_time_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(Exception, "start_time, end_time değerinden önce"):
            server.get_measurement_summary(
                start_time="2026-11-11T00:00:00Z",
                end_time="2026-11-10T00:00:00Z",
            )

    def test_new_analysis_tools(self) -> None:
        latest = server.get_latest_measurements(limit=3)
        daily = server.get_daily_summary()
        hourly = server.get_hourly_profile()
        comparison = server.compare_devices()
        percentiles = server.get_measurement_percentiles()
        correlations = server.get_correlation_analysis()
        buckets = server.get_time_bucket_summary(bucket_minutes=1440)
        health = server.get_device_health_report()

        self.assertEqual(3, latest["measurement_count"])
        self.assertEqual(25, daily["summary_count"])
        self.assertEqual(120, hourly["profile_count"])
        self.assertEqual(5, comparison["device_count"])
        self.assertEqual(35945, percentiles["measurement_count"])
        self.assertEqual(35945, correlations["measurement_count"])
        self.assertEqual(25, buckets["bucket_count"])
        self.assertEqual(5, health["device_count"])

        statuses = {
            row["device_name"]: row["health_status"]
            for row in health["health_reports"]
        }
        self.assertEqual("normal", statuses["Cihaz-01"])
        self.assertEqual("inceleme_gerekli", statuses["Cihaz-03"])

    def test_tool_descriptions_are_turkish(self) -> None:
        async def scenario() -> list[str]:
            async with Client(server.mcp) as client:
                tools = await client.list_tools()
                return [tool.description or "" for tool in tools.tools]

        descriptions = anyio.run(scenario)
        self.assertTrue(all(descriptions))
        self.assertTrue(any("Cihazları" in description for description in descriptions))

    def test_device_event_data_and_distributions(self) -> None:
        events = server.list_device_events(limit=100)
        summary = server.get_device_event_summary()

        self.assertEqual(70, events["event_count"])
        self.assertFalse(events["results_truncated"])
        self.assertEqual(70, summary["summary"]["event_count"])
        self.assertEqual(4, summary["summary"]["critical_event_count"])
        self.assertEqual(55, summary["summary"]["warning_event_count"])
        self.assertEqual(11, summary["summary"]["info_event_count"])
        self.assertEqual(8, summary["summary"]["open_event_count"])
        self.assertEqual(62, summary["summary"]["resolved_event_count"])
        self.assertEqual("Cihaz-03", summary["by_device"][0]["device_name"])
        self.assertEqual(24, summary["by_device"][0]["event_count"])
        self.assertEqual("Ankara", summary["by_location"][0]["location"])
        self.assertEqual(40, summary["by_location"][0]["event_count"])

    def test_resources_and_prompt_are_exposed(self) -> None:
        async def scenario() -> tuple[set[str], set[str], set[str], str, str]:
            async with Client(server.mcp) as client:
                resources = await client.list_resources()
                templates = await client.list_resource_templates()
                prompts = await client.list_prompts()
                catalog = await client.read_resource("device-events://catalog")
                prompt = await client.get_prompt(
                    "cihaz_olay_raporu",
                    {
                        "start_time": "2026-11-06T00:00:00Z",
                        "end_time": "2026-11-11T00:00:00Z",
                        "device_id": "3",
                    },
                )
                return (
                    {str(item.uri) for item in resources.resources},
                    {item.uri_template for item in templates.resource_templates},
                    {item.name for item in prompts.prompts},
                    catalog.contents[0].text,
                    prompt.messages[0].content.text,
                )

        resource_uris, template_uris, prompt_names, catalog_text, prompt_text = anyio.run(scenario)

        self.assertIn("device-events://catalog", resource_uris)
        self.assertIn("device-events://device/{device_id}", template_uris)
        self.assertIn("cihaz_olay_raporu", prompt_names)
        self.assertIn('"event_count": 70', catalog_text)
        self.assertIn("generate_device_event_report", prompt_text)

    def test_pdf_event_report_is_created(self) -> None:
        async def scenario() -> dict[str, object]:
            async with Client(server.mcp) as client:
                response = await client.call_tool(
                    "generate_device_event_report",
                    {
                        "start_time": "2026-11-06T00:00:00Z",
                        "end_time": "2026-11-11T00:00:00Z",
                        "device_id": 3,
                    },
                )
                self.assertFalse(response.is_error)
                self.assertIsNotNone(response.structured_content)
                return response.structured_content

        result = anyio.run(scenario)
        report_path = Path(result["report_path"])
        try:
            self.assertTrue(report_path.is_file())
            self.assertEqual(b"%PDF-", report_path.read_bytes()[:5])
            reader = PdfReader(report_path)
            self.assertGreaterEqual(len(reader.pages), 4)
            extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Cihaz Olay Raporu", extracted_text)
            self.assertIn("Cihaz-03", extracted_text)
            self.assertIn("Ankara", extracted_text)
            self.assertEqual(24, result["event_count"])
            self.assertEqual(3, result["device_id"])
        finally:
            report_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
