"""
Main Entrypoint for Agent Chaos Monkey.
Demonstrates running a static AST code scan and executing live chaos fault injection.
"""

import os
import sys

from chaos_engine import (
    inject_chaos,
    FaultType,
    scan_directory,
    generate_html_report,
    get_tracker
)


@inject_chaos(rate=0.5, faults=[FaultType.HTTP_502, FaultType.CORRUPTED_JSON], latency_range=(0.01, 0.05))
def sample_agent_tool(tool_input: str) -> str:
    """Sample decorated tool demonstrating chaos fault injection."""
    return f'{{"status": "success", "data": "processed {tool_input}"}}'


def run_quickstart():
    print("================================================================================", flush=True)
    print(" AGENT CHAOS MONKEY — STARTING QUICKSTART SUITE", flush=True)
    print("================================================================================", flush=True)
    
    # 1. Run Static AST Code Scan
    print("\n Step 1: Running Static AST Resilience Scan on '.'...", flush=True)
    ast_result = scan_directory(".")
    print(f"   Files Scanned    : {ast_result.scanned_files_count}", flush=True)
    print(f"   Flaws Detected   : {ast_result.total_issues_count}", flush=True)
    print(f"   AST Resilience   : {ast_result.resilience_score} / 100", flush=True)

    # 2. Run Live Chaos Simulation Trial
    print("\n Step 2: Executing Live Chaos Injection Trial...", flush=True)
    tracker = get_tracker()
    tracker.reset()

    for i in range(5):
        try:
            res = sample_agent_tool(f"request_{i+1}")
            print(f"   Call #{i+1}: SUCCESS -> {res}", flush=True)
        except Exception as e:
            print(f"   Call #{i+1}: FAULT INJECTED -> {e.__class__.__name__}: {e}", flush=True)

    summary = tracker.get_summary()

    # 3. Generate Executive HTML Audit Report
    print("\n Step 3: Generating Executive HTML Audit Report...", flush=True)
    report_path = generate_html_report(summary, output_filepath="reports/quickstart_audit.html")
    print(f"   Report Saved to  : {report_path}", flush=True)
    print("================================================================ raw\n", flush=True)


if __name__ == "__main__":
    run_quickstart()
