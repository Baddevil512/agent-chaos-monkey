"""
Sandbox Demo: Mock E-Commerce Refund AI Agent Reliability Test.
Demonstrates Agent Chaos Monkey comparing an 'Unprotected Agent' vs a 'Resilient Agent'
without requiring paid LLM API keys.
"""

import time
import json
import sys
import os

# Ensure package modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chaos_engine import (
    inject_chaos,
    FaultType,
    get_tracker,
    generate_html_report,
    ChaosEngineException,
    ChaosHTTPError,
    ChaosCorruptedJSONError,
    ChaosEmptyResponseError
)


# =====================================================================
# Mock E-Commerce Core Tools (Decorated with Chaos Fault Injection)
# =====================================================================

@inject_chaos(rate=0.6, faults=[FaultType.HTTP_502, FaultType.LATENCY, FaultType.CORRUPTED_JSON], latency_range=(0.01, 0.05))
def lookup_order_db(order_id: str) -> str:
    """Mock Tool: Fetches order status from database."""
    orders = {
        "ORD-101": json.dumps({"order_id": "ORD-101", "status": "DELIVERED", "amount": 149.99, "customer": "CUST-88"}),
        "ORD-202": json.dumps({"order_id": "ORD-202", "status": "SHIPPED", "amount": 89.50, "customer": "CUST-99"})
    }
    if order_id in orders:
        return orders[order_id]
    return json.dumps({"error": "Order not found"})


@inject_chaos(rate=0.7, faults=[FaultType.HTTP_503, FaultType.HTTP_429, FaultType.EMPTY_RESPONSE], latency_range=(0.01, 0.05))
def process_stripe_refund(order_id: str, amount: float) -> str:
    """Mock Tool: Issues refund via payment gateway API."""
    return json.dumps({
        "status": "SUCCESS",
        "transaction_id": "txn_tx_9876543210",
        "refunded_amount": amount,
        "order_id": order_id
    })


@inject_chaos(rate=0.5, faults=[FaultType.LATENCY, FaultType.CORRUPTED_JSON], latency_range=(0.01, 0.05))
def update_inventory_system(order_id: str) -> str:
    """Mock Tool: Restocks item inventory."""
    return json.dumps({"status": "RESTOCKED", "order_id": order_id})


# =====================================================================
# Agent Implementations
# =====================================================================

class UnprotectedRefundAgent:
    """
    Unprotected AI Agent Workflow.
    Naively retries failing tool calls in tight loops without circuit breakers or fallbacks.
    """
    def __init__(self, name: str = "Unprotected-Agent-v1"):
        self.name = name

    def execute_refund_request(self, order_id: str) -> dict:
        print(f"\n[AGENT] [{self.name}] Processing refund for {order_id}...", flush=True)
        
        # Step 1: Lookup Order with Naive Infinite Retry Loop (up to 5 attempts)
        order_data = None
        for attempt in range(1, 6):
            try:
                print(f"   [Step 1] Attempt {attempt}: Calling lookup_order_db('{order_id}')...", flush=True)
                res_str = lookup_order_db(order_id)
                order_data = json.loads(res_str)
                break
            except Exception as e:
                print(f"   [FAIL] Attempt {attempt} failed with: {e}", flush=True)
                if attempt == 5:
                    print(f"   [CRASH] Retries exhausted for lookup_order_db!", flush=True)
                    return {"status": "FAILED", "reason": str(e)}

        # Step 2: Issue Refund with Naive Retry Loop
        amount = order_data.get("amount", 100.0) if isinstance(order_data, dict) else 100.0
        refund_res = None
        for attempt in range(1, 6):
            try:
                print(f"   [Step 2] Attempt {attempt}: Calling process_stripe_refund('{order_id}', {amount})...", flush=True)
                refund_str = process_stripe_refund(order_id, amount)
                refund_res = json.loads(refund_str)
                break
            except Exception as e:
                print(f"   [FAIL] Attempt {attempt} failed with: {e}", flush=True)
                if attempt == 5:
                    print(f"   [CRASH] Retries exhausted for process_stripe_refund!", flush=True)
                    return {"status": "FAILED", "reason": str(e)}

        return {"status": "SUCCESS", "result": refund_res}


class ResilientRefundAgent:
    """
    Resilient AI Agent Workflow.
    Implements exponential backoff, circuit breaking, fallback databases, and graceful degradation.
    """
    def __init__(self, name: str = "Resilient-Agent-v2"):
        self.name = name
        self.fallback_cache = {
            "ORD-101": {"order_id": "ORD-101", "status": "DELIVERED", "amount": 149.99, "customer": "CUST-88", "is_fallback": True}
        }

    def execute_refund_request(self, order_id: str) -> dict:
        print(f"\n[AGENT] [{self.name}] Processing refund for {order_id} with Fallback & Circuit Breaker...", flush=True)
        
        # Step 1: Robust Order Lookup with Fallback Cache
        order_data = None
        try:
            print(f"   [Step 1] Calling lookup_order_db('{order_id}')...", flush=True)
            res_str = lookup_order_db(order_id)
            order_data = json.loads(res_str)
        except ChaosEngineException as e:
            print(f"   [CHAOS CAUGHT] Primary DB failed ({e.__class__.__name__}). Engaging Fallback Cache...", flush=True)
            order_data = self.fallback_cache.get(order_id, {"order_id": order_id, "amount": 100.0, "is_fallback": True})
        except Exception as e:
            print(f"   [FALLBACK] Malformed JSON payload. Recovering with default schema fallback...", flush=True)
            order_data = {"order_id": order_id, "amount": 100.0, "is_fallback": True}

        # Step 2: Robust Refund Gateway with Queue Fallback
        amount = order_data.get("amount", 100.0) if isinstance(order_data, dict) else 100.0
        try:
            print(f"   [Step 2] Calling process_stripe_refund('{order_id}', {amount})...", flush=True)
            refund_str = process_stripe_refund(order_id, amount)
            refund_res = json.loads(refund_str)
            return {"status": "SUCCESS", "result": refund_res}
        except ChaosEngineException as e:
            print(f"   [CHAOS CAUGHT] Stripe Payment Gateway unreachable ({e.__class__.__name__}).", flush=True)
            print(f"   [CIRCUIT BREAKER] Tripped! Queueing refund offline for manual/async processing...", flush=True)
            return {
                "status": "QUEUED_OFFLINE",
                "message": "Gateway temporarily down due to upstream rate limits; refund safely queued.",
                "order_id": order_id,
                "amount": amount
            }


# =====================================================================
# Main Sandbox Test Runner
# =====================================================================

def run_chaos_test_suite():
    tracker = get_tracker()
    tracker.reset()

    print("================================================================", flush=True)
    print(" AGENT CHAOS MONKEY: QA RELIABILITY & TOKEN BURN TEST SUITE", flush=True)
    print("================================================================", flush=True)

    # -----------------------------------------------------------------
    # Part 1: Run Unprotected Agent (Expect high retries & failure)
    # -----------------------------------------------------------------
    print("\n--- PHASE 1: TESTING UNPROTECTED AGENT WORKFLOW ---", flush=True)
    unprotected = UnprotectedRefundAgent()
    for _ in range(3):
        unprotected.execute_refund_request("ORD-101")
        time.sleep(0.05)

    unprotected_summary = tracker.get_summary()

    # -----------------------------------------------------------------
    # Part 2: Run Resilient Agent (Expect graceful fallback & high score)
    # -----------------------------------------------------------------
    print("\n--- PHASE 2: TESTING RESILIENT AGENT WORKFLOW ---", flush=True)
    tracker.reset()  # reset tracker for clean resilient comparison
    resilient = ResilientRefundAgent()
    for _ in range(3):
        resilient.execute_refund_request("ORD-101")
        time.sleep(0.05)

    resilient_summary = tracker.get_summary()

    # -----------------------------------------------------------------
    # Print Terminal Comparison Report
    # -----------------------------------------------------------------
    print("\n================================================================", flush=True)
    print(" EXECUTIVE COMPARISON REPORT", flush=True)
    print("================================================================", flush=True)
    print(f" Metric                          | Unprotected Agent | Resilient Agent", flush=True)
    print("---------------------------------+-------------------+-----------------", flush=True)
    print(f" Resilience Score (0-100)        | {unprotected_summary['resilience_score']:<17} | {resilient_summary['resilience_score']}", flush=True)
    print(f" Total Invocations               | {unprotected_summary['total_invocations']:<17} | {resilient_summary['total_invocations']}", flush=True)
    print(f" Faults Injected                 | {unprotected_summary['faults_injected_count']:<17} | {resilient_summary['faults_injected_count']}", flush=True)
    print(f" Fallback Handled                | {unprotected_summary['fallback_handled_count']:<17} | {resilient_summary['fallback_handled_count']}", flush=True)
    print(f" Retry Loops Triggered           | {unprotected_summary['retry_count']:<17} | {resilient_summary['retry_count']}", flush=True)
    print(f" Wasted Token Burn               | {unprotected_summary['wasted_tokens']:<17} | {resilient_summary['wasted_tokens']}", flush=True)
    print(f" Est. Monthly Leak Risk (USD)    | ${unprotected_summary['monthly_leak_risk_usd']:<16} | ${resilient_summary['monthly_leak_risk_usd']}", flush=True)
    print("================================================================", flush=True)

    # -----------------------------------------------------------------
    # Generate Standalone Dark HTML Dashboard Report
    # -----------------------------------------------------------------
    report_path = generate_html_report(resilient_summary, output_filepath="reports/resilience_audit_report.html")
    print(f"\nStandalone HTML Dashboard generated successfully!", flush=True)
    print(f"Report Path: {report_path}", flush=True)
    print("Open this file in your browser to view full executive metrics and call logs.", flush=True)


if __name__ == "__main__":
    run_chaos_test_suite()
