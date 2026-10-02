"""
Static AST Code Scanner for Agent Chaos Monkey.
Recursively scans local Python files and directories using Python's built-in `ast` module.
Detects:
 1. Unbounded Agent Loops & Missing Circuit Breakers (max_iter, max_execution_time, allow_delegation)
 2. Missing LLM Timeout & Retry Guards (OpenAI, ChatOpenAI, Anthropic, litellm, requests.post)
 3. Unsafe Tool Execution / Prompt Injection Sinks (eval, exec, subprocess with shell=True)
 4. Unhandled JSON / Tool Output Parsing (json.loads without try/except or Pydantic)
 5. Hardcoded API Keys / Secrets in Agent Configs
"""

import ast
import os
import sys
import re
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
    category: str       # e.g. "MISSING_CIRCUIT_BREAKER", "UNBOUNDED_LOOP", "MISSING_TIMEOUT", etc.
    severity: str       # "CRITICAL", "HIGH", or "MEDIUM"
    symbol_name: str    # "Agent()", "while True", "eval()", etc.
    description: str
    code_snippet: str = ""
    fix_recommendation: str = ""


@dataclass
class ScanResult:
    """Aggregated results from an AST security & resilience scan."""
    target_path: str
    scanned_files_count: int
    total_issues_count: int
    resilience_score: float
    risk_grade: str     # "A", "B", "C", "D", "F"
    vulnerabilities: List[Vulnerability] = field(default_factory=list)


SECRET_PATTERNS = [
    (re.compile(r'(?i)(sk-[a-zA-Z0-9]{32,})'), "OpenAI Secret Key"),
    (re.compile(r'(?i)(sk-ant-api[a-zA-Z0-9_\-]{30,})'), "Anthropic API Key"),
    (re.compile(r'(?i)(ghp_[a-zA-Z0-9]{36})'), "GitHub Personal Access Token"),
    (re.compile(r'(?i)(api[_-]?key\s*=\s*[\'"][a-zA-Z0-9_\-]{16,}[\'"])'), "Hardcoded API Key Assignment"),
    (re.compile(r'(?i)(secret[_-]?key\s*=\s*[\'"][a-zA-Z0-9_\-]{16,}[\'"])'), "Hardcoded Secret Key Assignment")
]


class ComprehensiveAgentASTVisitor(ast.NodeVisitor):
    """Full-spectrum AST Node Visitor for AI Agent reliability and security auditing."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_lines = source_code.splitlines()
        self.has_crewai_import = False
        self.has_langchain_import = False
        self.vulnerabilities: List[Vulnerability] = []
        self._check_secrets()

    def _check_secrets(self):
        """Scans raw source code lines for hardcoded secrets/API keys."""
        for lineno, line in enumerate(self.source_lines, 1):
            for pattern, label in SECRET_PATTERNS:
                if pattern.search(line):
                    self.vulnerabilities.append(Vulnerability(
                        file_path=self.file_path,
                        line_number=lineno,
                        category="HARDCODED_SECRET",
                        severity="CRITICAL",
                        symbol_name="API_KEY_SECRET",
                        description=f"Detected {label} hardcoded in agent configuration.",
                        code_snippet=line.strip()[:100],
                        fix_recommendation="os.getenv('OPENAI_API_KEY')  # Use environment variables or secrets manager"
                    ))

    def visit_Import(self, node):
        for alias in node.names:
            name_lower = alias.name.lower()
            if "crewai" in name_lower:
                self.has_crewai_import = True
            elif "langchain" in name_lower or "langgraph" in name_lower:
                self.has_langchain_import = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            mod_lower = node.module.lower()
            if "crewai" in mod_lower:
                self.has_crewai_import = True
            elif "langchain" in mod_lower or "langgraph" in mod_lower:
                self.has_langchain_import = True
        self.generic_visit(node)

    def visit_While(self, node):
        """Rule 1: Detect Unbounded Agent Loops (while True without max_iter / step break)."""
        is_always_true = False
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            is_always_true = True
        elif isinstance(node.test, ast.NameConstant) and node.test.value is True:
            is_always_true = True

        if is_always_true:
            # Check if there is a step counter cap inside loop body
            has_break_guard = False
            for child in ast.walk(node):
                if isinstance(child, ast.If):
                    # Simple heuristic: If inside while True checks max_iter, step > limit, etc.
                    for sub in ast.walk(child.test):
                        if isinstance(sub, ast.Name) and sub.id in ("max_iter", "max_steps", "step", "attempts", "retry_count", "i"):
                            has_break_guard = True
                            break

            if not has_break_guard:
                snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else "while True:"
                self.vulnerabilities.append(Vulnerability(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    category="UNBOUNDED_AGENT_LOOP",
                    severity="CRITICAL",
                    symbol_name="while True",
                    description="Infinite retry loop detected (`while True:`) without step counter cap or circuit breaker guard.",
                    code_snippet=snippet,
                    fix_recommendation="for step in range(MAX_STEPS):\n    # Agent iteration logic\n    if done:\n        break"
                ))
        self.generic_visit(node)

    def visit_Call(self, node):
        func_id = ""
        if isinstance(node.func, ast.Name):
            func_id = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_id = node.func.attr

        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}

        # --- Rule 1b: CrewAI Agent Circuit Breakers ---
        if func_id == "Agent":
            has_crewai_params = "role" in keywords or "goal" in keywords
            if has_crewai_params or self.has_crewai_import:
                has_max_iter = "max_iter" in keywords
                has_max_exec_time = "max_execution_time" in keywords

                allow_delegation = False
                if "allow_delegation" in keywords:
                    kw_val = keywords["allow_delegation"]
                    if (isinstance(kw_val, ast.Constant) and kw_val.value is True) or \
                       (isinstance(kw_val, ast.NameConstant) and kw_val.value is True):
                        allow_delegation = True

                if not has_max_iter and not has_max_exec_time:
                    severity = "CRITICAL" if allow_delegation else "HIGH"
                    snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else "Agent(...)"
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
                        code_snippet=snippet,
                        fix_recommendation="Agent(role='...', goal='...', max_iter=10, max_execution_time=300)"
                    ))

        # --- Rule 2: Missing LLM Timeout & Retry Guards ---
        llm_providers = ("OpenAI", "ChatOpenAI", "Anthropic", "Client", "Claude", "litellm", "post")
        if func_id in llm_providers:
            # Check requests.post / LLM client instantiation for timeout
            if "timeout" not in keywords and "request_timeout" not in keywords:
                snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else f"{func_id}(...)"
                self.vulnerabilities.append(Vulnerability(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    category="MISSING_LLM_TIMEOUT",
                    severity="HIGH",
                    symbol_name=f"{func_id}()",
                    description=f"LLM or API call '{func_id}()' initialized without an explicit timeout guard (risks thread hanging).",
                    code_snippet=snippet,
                    fix_recommendation=f"{func_id}(..., timeout=30.0)"
                ))

        # --- Rule 3: Unsafe Tool Execution / Prompt Injection Sinks ---
        if func_id in ("eval", "exec"):
            snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else f"{func_id}(...)"
            self.vulnerabilities.append(Vulnerability(
                file_path=self.file_path,
                line_number=node.lineno,
                category="PROMPT_INJECTION_SINK",
                severity="CRITICAL",
                symbol_name=f"{func_id}()",
                description=f"Unsafe code execution sink '{func_id}()' found in tool/agent path. Prone to severe Remote Code Execution (RCE).",
                code_snippet=snippet,
                fix_recommendation="Use ast.literal_eval() or safe sandbox interpreters instead of eval()/exec()"
            ))

        if func_id in ("Popen", "run", "call", "check_output"):
            if "shell" in keywords:
                kw_val = keywords["shell"]
                if (isinstance(kw_val, ast.Constant) and kw_val.value is True) or \
                   (isinstance(kw_val, ast.NameConstant) and kw_val.value is True):
                    snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else "subprocess.run(..., shell=True)"
                    self.vulnerabilities.append(Vulnerability(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        category="PROMPT_INJECTION_SINK",
                        severity="CRITICAL",
                        symbol_name="subprocess(shell=True)",
                        description="Subprocess execution with `shell=True` detected in agent tool. Highly vulnerable to prompt injection command hijacking.",
                        code_snippet=snippet,
                        fix_recommendation="subprocess.run(['command', 'arg1'], shell=False)"
                    ))

        # --- Rule 4: Unhandled JSON / Tool Output Parsing ---
        if func_id == "loads" or (isinstance(node.func, ast.Attribute) and node.func.attr == "loads"):
            # Check if json.loads call is wrapped in a try block
            in_try = False
            curr = node
            # Walk up parents isn't directly supported in std ast without parent pointers, check FunctionDef body
            snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else "json.loads(...)"
            # Heuristic check on line context
            if "llm" in snippet.lower() or "response" in snippet.lower() or "tool" in snippet.lower() or "output" in snippet.lower() or "result" in snippet.lower():
                # Verify if current function containing json.loads has try-except
                pass # FunctionDef handles try check or tool check below

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
                snippet = self.source_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(self.source_lines) else f"def {node.name}(...):"
                self.vulnerabilities.append(Vulnerability(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    category="UNPROTECTED_TOOL",
                    severity="HIGH",
                    symbol_name=f"@{node.name}",
                    description=f"Tool function '{node.name}()' lacks try-except fault handling against network/API failures.",
                    code_snippet=snippet,
                    fix_recommendation=f"def {node.name}(...):\n    try:\n        # Tool logic\n    except Exception as e:\n        return f'Tool error: {{e}}'"
                ))

        # Rule 4: Unhandled json.loads inside functions parsing LLM output without try/except
        has_json_loads = False
        json_line = node.lineno
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Call):
                func_name = ""
                if isinstance(stmt.func, ast.Name):
                    func_name = stmt.func.id
                elif isinstance(stmt.func, ast.Attribute):
                    func_name = stmt.func.attr
                if func_name == "loads":
                    has_json_loads = True
                    json_line = stmt.lineno
                    break

        if has_json_loads:
            has_try_block = any(isinstance(stmt, ast.Try) for stmt in ast.walk(node))
            if not has_try_block:
                snippet = self.source_lines[json_line - 1].strip() if 0 <= json_line - 1 < len(self.source_lines) else "json.loads(...)"
                if "llm" in snippet.lower() or "response" in snippet.lower() or "text" in snippet.lower() or "content" in snippet.lower():
                    self.vulnerabilities.append(Vulnerability(
                        file_path=self.file_path,
                        line_number=json_line,
                        category="UNHANDLED_JSON_PARSING",
                        severity="MEDIUM",
                        symbol_name="json.loads()",
                        description="`json.loads()` called on LLM/tool output without `try-except` exception handling or Pydantic validation.",
                        code_snippet=snippet,
                        fix_recommendation="try:\n    data = json.loads(llm_output)\nexcept json.JSONDecodeError:\n    data = {'fallback': True}"
                    ))

        self.generic_visit(node)


def calculate_risk_grade(resilience_score: float) -> str:
    """Calculates risk grade from A to F based on Resilience Score."""
    if resilience_score >= 90:
        return "A"
    elif resilience_score >= 80:
        return "B"
    elif resilience_score >= 70:
        return "C"
    elif resilience_score >= 50:
        return "D"
    else:
        return "F"


def scan_file(file_path: str) -> List[Vulnerability]:
    """Scans a single Python file for AST vulnerabilities."""
    if not os.path.isfile(file_path) or not file_path.endswith(".py"):
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        tree = ast.parse(code, filename=file_path)
        visitor = ComprehensiveAgentASTVisitor(file_path, code)
        visitor.visit(tree)

        return visitor.vulnerabilities
    except SyntaxError:
        return []
    except Exception:
        return []


def scan_directory(target_path: str) -> ScanResult:
    """
    Recursively scans a target directory or file for CrewAI/LLM agent pattern flaws
    and returns an aggregated ScanResult.
    """
    abs_path = os.path.abspath(target_path)
    all_vulnerabilities: List[Vulnerability] = []
    scanned_files_count = 0

    SKIP_DIRS = {".venv", "venv", "env", ".git", "__pycache__", "node_modules", "build", "dist", ".pytest_cache", "docs"}

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
    risk_grade = calculate_risk_grade(resilience_score)

    return ScanResult(
        target_path=abs_path,
        scanned_files_count=scanned_files_count,
        total_issues_count=len(all_vulnerabilities),
        resilience_score=resilience_score,
        risk_grade=risk_grade,
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
    print(f" Risk Grade        : Grade {result.risk_grade}")
    print(f" Resilience Score  : {result.resilience_score} / 100")
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
        if v.fix_recommendation:
            print(f"        └─ Fix   : {v.fix_recommendation}")
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
        tracker = TelemetryTracker()
        tracker.reset()

        for idx, v in enumerate(result.vulnerabilities):
            status = "UNHANDLED_FAILURE" if v.severity in ("CRITICAL", "HIGH") else "FAULT_INJECTED"
            tracker.record_call(
                call_id=f"ast-{idx+1}",
                function_name=v.symbol_name,
                execution_time_ms=0.0,
                status=status,
                fault_type="http_502" if v.category == "MISSING_CIRCUIT_BREAKER" else "corrupted_json",
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
