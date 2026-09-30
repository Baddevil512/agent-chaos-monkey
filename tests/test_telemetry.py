"""
Unit tests for telemetry tracking and resilience score calculations.
"""

import unittest
from chaos_engine import get_tracker, FaultType


class TestTelemetryTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = get_tracker()
        self.tracker.reset()

    def test_telemetry_resilience_score_calculation(self):
        # Initial state with no calls should be 100
        self.assertEqual(self.tracker.calculate_resilience_score(), 100.0)

        # Simulate 5 successful calls
        for i in range(5):
            self.tracker.record_call(
                call_id=f"c-{i}",
                function_name="tool_a",
                execution_time_ms=50.0,
                status="SUCCESS"
            )

        summary = self.tracker.get_summary()
        self.assertEqual(summary["resilience_score"], 100.0)
        self.assertEqual(summary["total_invocations"], 5)

        # Reset and simulate fault injections with retries
        self.tracker.reset()
        for i in range(3):
            self.tracker.record_call(
                call_id=f"c-{i}",
                function_name="flaky_tool",
                execution_time_ms=100.0,
                status="UNHANDLED_FAILURE",
                fault_type="http_502",
                error_message="HTTP 502 Bad Gateway"
            )

        low_summary = self.tracker.get_summary()
        self.assertLess(low_summary["resilience_score"], 50.0)
        self.assertGreater(low_summary["wasted_tokens"], 0)
        self.assertGreaterEqual(low_summary["monthly_leak_risk_usd"], 0.0)

    def test_token_estimation_and_waste(self):
        # Call with large input text
        input_text = "x" * 400   # ~100 tokens
        output_text = "y" * 800  # ~200 tokens

        self.tracker.record_call(
            call_id="c-1",
            function_name="heavy_tool",
            execution_time_ms=120.0,
            status="UNHANDLED_FAILURE",
            fault_type="corrupted_json",
            input_args=input_text,
            output_data=output_text
        )

        summary = self.tracker.get_summary()
        self.assertGreaterEqual(summary["total_tokens"], 300)
        self.assertGreaterEqual(summary["wasted_tokens"], 300)


if __name__ == "__main__":
    unittest.main()
