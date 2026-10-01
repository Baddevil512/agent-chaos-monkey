"""
Static AST Code Scanner for Agent Chaos Monkey.
Recursively scans local Python files and directories using Python's built-in `ast` module.
Detects missing CrewAI Agent circuit breakers (max_iter, max_execution_time, allow_delegation)
and unprotected @tool functions lacking try-except fault handling.
"""

import ast
import os
import sys
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Ensure stdout handles UTF-8 / unicode safely across all operating systems
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

from .reporter import generate_html_report
from .telemetry import TelemetryTracker, CallLogRecord


@dataclass
class Vulnerability:
    """Represents a single static code flaw detected by the AST scanner."""
    file_path: str
    line_number: int
    category: str       # "MISSING_CIRCUIT_BREAKER" or "UNPROTECTED_TOOL"
    severity: str       # "CRITICAL", "HIGH", or "MEDIUM"
    symbol_name: str    # "Agent()" or "@tool_name"
    description: str
    code_snippet: str = ""


@dataclass
class ScanResult:
    """Aggregated results from an AST security & resilience scan."""
    target_path: str
    scanned_files_count: int
    total_issues_count: int
    resilience_score: float
    vulnerabilities: List[Vulnerability] = field(default_factory=list)


class CrewAIASTVisitor(ast.NodeVisitor):
    """AST Node Visitor that identifies CrewAI Agent pattern flaws and unprotected tools."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_lines = source_code.splitlines()
        self.has_crewai_import = False
        self.vulnerabilities: List[Vulnerability] = []

    def visit_Import(self, node):
        for alias in node.names:
            if "crewai" in alias.name.lower():
                self.has_crewai_import = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and "crewai" in node.module.lower():
            self.has_crewai_import = True
        self.generic_visit(node)

    def visit_Call(self, node):
        is_agent_call = (
            (isinstance(node.func, ast.Name) and node.func.id == "Agent") or
            (isinstance(node.func, ast.Attribute) and node.func.attr == "Agent")
        )
        if is_agent_call:
            keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            # Verify CrewAI signature (role= or goal= keyword arguments)
            has_crewai_params = "role" in keywords or "goal" in keywords

            if has_crewai_params or self.has_crewai_import:
                has_max_iter = "max_iter" in keywords
                has_max_exec_time = "max_execution_time" in keywords

                # Check if delegation is enabled
                allow_delegation = False
                if "allow_delegation" in keywords:
                    kw_val = keywords["allow_delegation"]
                    if isinstance(kw_val, ast.Constant) and kw_val.value is True:
                        allow_delegation = True
                    elif isinstance(kw_val, ast.NameConstant) and kw_val.value is True:
                        allow_delegation = True

                if not has_max_iter and not has_max_exec_time:
                    severity = "CRITICAL" if allow_delegation else "HIGH"
                    snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else ""
                    desc = "Agent() initialized without 'max_iter' or 'max_execution_time' circuit breaker."
                    if allow_delegation:
                        desc += " (CRITICAL: Delegation is enabled, creating infinite retry cascade risk)"

                    self.vulnerabilities.append(Vulnerability(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        category="MISSING_CIRCUIT_BREAKER",
                        severity=severity,
                        symbol_name="Agent()",
                        description=desc,
                        code_snippet=snippet
                    ))

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        is_tool = any(
            (isinstance(d, ast.Name) and d.id == "tool") or
            (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "tool") or
            (isinstance(d, ast.Attribute) and d.attr == "tool")
            for d in node.decorator_list
        )
        if is_tool:
            has_try = any(isinstance(stmt, ast.Try) for stmt in ast.walk(node))
            if not has_try:
                snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else ""
                self.vulnerabilities.append(Vulnerability(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    category="UNPROTECTED_TOOL",
                    severity="HIGH",
                    symbol_name=f"@{node.name}",
                    description=f"Tool function '{node.name}()' lacks try-except fault handling against network/API errors.",
                    code_snippet=snippet
                ))

        self.generic_visit(node)


def scan_file(file_path: str) -> List[Vulnerability]:
    """Scans a single Python file for AST vulnerabilities."""
    if not os.path.isfile(file_path) or not file_path.endswith(".py"):
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Fast string pre-filter
        if "crewai" not in code.lower() and "agent(" not in code.lower() and "@tool" not in code.lower():
            return []

        tree = ast.parse(code, filename=file_path)
        visitor = CrewAIASTVisitor(file_path, code)
        visitor.visit(tree)

        # Require crewai import or explicit Agent signature match
        if not visitor.has_crewai_import and not any(v.category == "MISSING_CIRCUIT_BREAKER" for v in visitor.vulnerabilities):
            return []

        return visitor.vulnerabilities
    except SyntaxError:
        return []
    except Exception:
        return []


def scan_directory(target_path: str) -> ScanResult:
    """
    Recursively scans a target directory or file for CrewAI agent pattern flaws
    and returns an aggregated ScanResult.
    """
    abs_path = os.path.abspath(target_path)
    all_vulnerabilities: List[Vulnerability] = []
    scanned_files_count = 0

    SKIP_DIRS = {".venv", "venv", "env", ".git", "__pycache__", "node_modules", "build", "dist", ".pytest_cache"}

    if os.path.isfile(abs_path):
        if abs_path.endswith(".py"):
            scanned_files_count = 1
            all_vulnerabilities.extend(scan_file(abs_path))
    elif os.path.isdir(abs_path):
        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for file in files:
                if file.endswith(".py"):
                    scanned_files_count += 1
                    file_full_path = os.path.join(root, file)
                    vulns = scan_file(file_full_path)
                    all_vulnerabilities.extend(vulns)

    # Compute Static Resilience Score (0 to 100)
    score = 100.0
    for v in all_vulnerabilities:
        if v.severity == "CRITICAL":
            score -= 25.0
        elif v.severity == "HIGH":
            score -= 15.0
        else:
            score -= 10.0

    resilience_score = round(max(0.0, min(100.0, score)), 1)

    return ScanResult(
        target_path=abs_path,
        scanned_files_count=scanned_files_count,
        total_issues_count=len(all_vulnerabilities),
        resilience_score=resilience_score,
        vulnerabilities=all_vulnerabilities
    )


class ASTScanner:
    """Class wrapper for AST scanning operations."""

    def __init__(self, target_path: str):
        self.target_path = target_path

    def run(self) -> ScanResult:
        return scan_directory(self.target_path)


def print_cli_summary(result: ScanResult):
    """Outputs a clean terminal summary table of the AST scan results."""
    print("\n================================================================================")
    print(" AGENT CHAOS MONKEY — STATIC AST CODE RESILIENCE SCANNER")
    print("================================================================================")
    print(f" Target Path       : {result.target_path}")
    print(f" Files Scanned     : {result.scanned_files_count}")
    print(f" Flaws Detected    : {result.total_issues_count}")
    
    # Score badge
    if result.resilience_score >= 80:
        badge = "EXCELLENT RESILIENCE"
    elif result.resilience_score >= 50:
        badge = "MODERATE RISK"
    else:
        badge = "CRITICAL RISK & UNBOUNDED RETRY HAZARD"

    print(f" Resilience Score  : {result.resilience_score} / 100  [{badge}]")
    print("================================================================================")

    if not result.vulnerabilities:
        print("\n[OK] No missing circuit breakers or unprotected tools detected! Code is clean.\n")
        return

    print("\n DETECTED STATIC VULNERABILITIES:")
    print(" -------------------------------------------------------------------------------")
    print(f" {'LINE':<6} | {'SEVERITY':<8} | {'CATEGORY':<24} | {'SYMBOL':<10} | {'LOCATION'}")
    print(" -------------------------------------------------------------------------------")

    for v in result.vulnerabilities:
        rel_path = os.path.relpath(v.file_path, os.getcwd())
        location = f"{rel_path}:{v.line_number}"
        print(f" L{v.line_number:<5} | {v.severity:<8} | {v.category:<24} | {v.symbol_name:<10} | {location}")
        if v.description:
            print(f"        └─ Issue : {v.description}")
        if v.code_snippet:
            print(f"        └─ Code  : `{v.code_snippet}`")
        print(" -------------------------------------------------------------------------------")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Agent Chaos Monkey AST Static Scanner — Detect missing CrewAI circuit breakers & unprotected tools."
    )
    parser.add_argument("path", nargs="?", default=".", help="Path to Python file or directory to scan (default: current directory)")
    parser.add_argument("--report", "-r", action="store_true", help="Generate an executive HTML dashboard report")
    parser.add_argument("--output", "-o", default="reports/ast_scan_report.html", help="HTML report output file path")

    args = parser.parse_args()

    result = scan_directory(args.path)
    print_cli_summary(result)

    if args.report:
        # Convert AST vulnerabilities into simulated telemetry data for HTML reporter
        tracker = TelemetryTracker()
        tracker.reset()

        for idx, v in enumerate(result.vulnerabilities):
            status = "UNHANDLED_FAILURE" if v.category == "MISSING_CIRCUIT_BREAKER" else "FAULT_INJECTED"
            fault_type = "http_502" if v.category == "MISSING_CIRCUIT_BREAKER" else "corrupted_json"
            tracker.record_call(
                call_id=f"ast-{idx+1}",
                function_name=v.symbol_name,
                execution_time_ms=0.0,
                status=status,
                fault_type=fault_type,
                error_message=v.description,
                input_args=f"File: {os.path.basename(v.file_path)} (Line {v.line_number})",
                output_data=v.code_snippet
            )

        summary_data = tracker.get_summary()
        summary_data["resilience_score"] = result.resilience_score
        
        report_path = generate_html_report(summary_data, output_filepath=args.output, title=f"AST Resilience Audit — {os.path.basename(result.target_path)}")
        print(f"[REPORT] Standalone HTML Dashboard report generated: {report_path}")


if __name__ == "__main__":
    main()
