"""
Unit tests for the Static AST Scanner (chaos_engine.ast_scanner).
"""

import os
import tempfile
import unittest

from chaos_engine import ASTScanner, scan_file, scan_directory, Vulnerability, ScanResult


class TestASTScanner(unittest.TestCase):

    def test_missing_max_iter_detection(self):
        code = '''
from crewai import Agent

unprotected_agent = Agent(
    role="Researcher",
    goal="Analyze market data"
)
'''
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f_path = f.name

        try:
            vulns = scan_file(f_path)
            self.assertEqual(len(vulns), 1)
            self.assertEqual(vulns[0].category, "MISSING_CIRCUIT_BREAKER")
            self.assertEqual(vulns[0].severity, "HIGH")
        finally:
            os.remove(f_path)

    def test_allow_delegation_critical_severity(self):
        code = '''
from crewai import Agent

delegating_agent = Agent(
    role="Manager",
    goal="Delegate tasks",
    allow_delegation=True
)
'''
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f_path = f.name

        try:
            vulns = scan_file(f_path)
            self.assertEqual(len(vulns), 1)
            self.assertEqual(vulns[0].category, "MISSING_CIRCUIT_BREAKER")
            self.assertEqual(vulns[0].severity, "CRITICAL")
            self.assertIn("CRITICAL: Delegation is enabled", vulns[0].description)
        finally:
            os.remove(f_path)

    def test_protected_agent_with_circuit_breaker(self):
        code = '''
from crewai import Agent

protected_agent_1 = Agent(
    role="Researcher",
    goal="Analyze data",
    max_iter=10
)

protected_agent_2 = Agent(
    role="Analyst",
    goal="Compute metrics",
    max_execution_time=120
)
'''
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f_path = f.name

        try:
            vulns = scan_file(f_path)
            self.assertEqual(len(vulns), 0)
        finally:
            os.remove(f_path)

    def test_non_crewai_framework_agent_ignored(self):
        code = '''
from swarm import Agent

swarm_agent = Agent(
    name="SwarmBot",
    instructions="Process queue"
)
'''
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f_path = f.name

        try:
            vulns = scan_file(f_path)
            self.assertEqual(len(vulns), 0)
        finally:
            os.remove(f_path)

    def test_unprotected_tool_detection(self):
        code = '''
from crewai.tools import tool

@tool("Stripe Refund Tool")
def process_refund(amount: float) -> str:
    return "refunded"

@tool("Protected Tool")
def safe_refund(amount: float) -> str:
    try:
        return "refunded"
    except Exception as e:
        return f"Error: {e}"
'''
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f_path = f.name

        try:
            vulns = scan_file(f_path)
            self.assertEqual(len(vulns), 1)
            self.assertEqual(vulns[0].category, "UNPROTECTED_TOOL")
            self.assertEqual(vulns[0].symbol_name, "@process_refund")
        finally:
            os.remove(f_path)

    def test_scan_directory_resilience_score(self):
        code = '''
from crewai import Agent
from crewai.tools import tool

agent = Agent(role="Bot", goal="Test")

@tool("Unsafe Tool")
def unsafe():
    return "ok"
'''
        with tempfile.TemporaryDirectory() as tmp_dir:
            f_path = os.path.join(tmp_dir, "agent_workflow.py")
            with open(f_path, "w", encoding="utf-8") as f:
                f.write(code)

            result = scan_directory(tmp_dir)
            self.assertEqual(result.scanned_files_count, 1)
            self.assertEqual(result.total_issues_count, 2)
            self.assertLess(result.resilience_score, 100.0)

            # Test class wrapper ASTScanner
            scanner = ASTScanner(tmp_dir)
            res_wrapper = scanner.run()
            self.assertEqual(res_wrapper.total_issues_count, 2)

    def test_client_level_timeout_ignored(self):
        code = '''
import httpx
from langchain_community.chat_models import ChatOpenAI

client = httpx.AsyncClient(timeout=30.0)
llm = ChatOpenAI(model="gpt-4o")
'''
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f_path = f.name

        try:
            vulns = scan_file(f_path)
            self.assertEqual(len(vulns), 0)
        finally:
            os.remove(f_path)

    def test_test_path_skipped(self):
        code = '''
from crewai import Agent
agent = Agent(role="Bot", goal="Test")
'''
        with tempfile.TemporaryDirectory() as tmp_dir:
            tests_dir = os.path.join(tmp_dir, "tests")
            os.makedirs(tests_dir, exist_ok=True)
            f_path = os.path.join(tests_dir, "test_agent.py")
            with open(f_path, "w", encoding="utf-8") as f:
                f.write(code)

            result = scan_directory(tmp_dir)
            self.assertEqual(result.total_issues_count, 0)


if __name__ == "__main__":
    unittest.main()
