"""
Unit tests for HTML report generator.
"""

import os
import tempfile
import unittest
from chaos_engine import generate_html_report, get_tracker


class TestHTMLReporter(unittest.TestCase):
    def setUp(self):
        self.tracker = get_tracker()
        self.tracker.reset()

    def test_generate_html_report(self):
        self.tracker.record_call(
            call_id="test-1",
            function_name="demo_func",
            execution_time_ms=45.2,
            status="SUCCESS",
            input_args="hello",
            output_data="world"
        )

        self.tracker.record_call(
            call_id="test-2",
            function_name="demo_func",
            execution_time_ms=120.0,
            status="FAULT_INJECTED",
            fault_type="http_502",
            error_message="HTTP 502 Bad Gateway"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            report_file = os.path.join(tmp_dir, "test_report.html")
            generated_path = generate_html_report(output_filepath=report_file)

            self.assertTrue(os.path.exists(generated_path))
            with open(generated_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Agent Chaos Monkey", content)
                self.assertIn("demo_func", content)
                self.assertIn("HTTP 502 Bad Gateway", content)
                self.assertIn("Resilience Score", content)


if __name__ == "__main__":
    unittest.main()
