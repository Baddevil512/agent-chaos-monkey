"""
Unit tests for @inject_chaos decorator.
"""

import unittest
import asyncio

from chaos_engine import (
    inject_chaos,
    FaultType,
    ChaosHTTPError,
    ChaosCorruptedJSONError,
    ChaosEmptyResponseError,
    get_tracker
)


class TestChaosDecorator(unittest.TestCase):
    def setUp(self):
        get_tracker().reset()

    def test_decorator_normal_execution(self):
        @inject_chaos(rate=0.0)
        def add_numbers(a, b):
            return a + b

        res = add_numbers(3, 5)
        self.assertEqual(res, 8)
        summary = get_tracker().get_summary()
        self.assertEqual(summary["total_invocations"], 1)
        self.assertEqual(summary["successful_invocations"], 1)

    def test_decorator_http_fault_injection(self):
        @inject_chaos(rate=1.0, faults=[FaultType.HTTP_502])
        def api_call():
            return "ok"

        with self.assertRaises(ChaosHTTPError) as cm:
            api_call()

        self.assertEqual(cm.exception.status_code, 502)
        summary = get_tracker().get_summary()
        self.assertEqual(summary["faults_injected_count"], 1)
        self.assertEqual(summary["fault_counts"]["http_502"], 1)

    def test_decorator_corrupted_json_raise(self):
        @inject_chaos(rate=1.0, faults=[FaultType.CORRUPTED_JSON], raise_exceptions=True)
        def fetch_json():
            return '{"valid": true}'

        with self.assertRaises(ChaosCorruptedJSONError):
            fetch_json()

    def test_decorator_corrupted_json_payload(self):
        @inject_chaos(rate=1.0, faults=[FaultType.CORRUPTED_JSON], raise_exceptions=False)
        def fetch_json():
            return '{"valid": true}'

        res = fetch_json()
        self.assertIn("invalid json", res)

    def test_decorator_empty_response(self):
        @inject_chaos(rate=1.0, faults=[FaultType.EMPTY_RESPONSE], raise_exceptions=False)
        def fetch_data():
            return "data"

        res = fetch_data()
        self.assertEqual(res, "")


class TestAsyncChaosDecorator(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_tracker().reset()

    async def test_async_decorator_fault_injection(self):
        @inject_chaos(rate=1.0, faults=[FaultType.HTTP_429])
        async def async_fetch():
            await asyncio.sleep(0.01)
            return "async_ok"

        with self.assertRaises(ChaosHTTPError) as cm:
            await async_fetch()

        self.assertEqual(cm.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
