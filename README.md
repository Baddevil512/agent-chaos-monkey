# 🐒⚡ Agent Chaos Monkey

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![Live Cloud Scanner](https://img.shields.io/badge/24%2F7_Live_Scanner-GitHub_Pages-6f42c1.svg)](https://baddevil512.github.io/agent-chaos-monkey/)
[![Reliability Score](https://img.shields.io/badge/Agentic_Resilience-Scorecard-purple.svg)]()

> 🌐 **[Try the 24/7 Online Cloud Web Scanner](https://baddevil512.github.io/agent-chaos-monkey/)** — Instant AST audit of CrewAI & LangChain code or public GitHub repositories right from your browser! Zero local setup needed.

**Agent Chaos Monkey** is a CTO-grade Chaos Engineering & QA Reliability Suite designed specifically for AI Agents (CrewAI, LangChain, and custom LLM tool-calling workflows).

---

## 🚨 The Problem: Preventing $5,000 Overnight LLM Token Loops

When an upstream microservice, database, or API dependency fails (e.g. `HTTP 502 Bad Gateway`, rate limit `429`, or corrupted JSON), AI agents without fallback decorators or circuit breakers enter **unbounded retry loops**.

Because LLM agents re-send full conversation history and prompt context on every retry attempt:
- A single downstream API failure can burn **100,000+ LLM tokens in minutes**.
- Unmonitored production bots risk **$5,000+ overnight API bill spikes** and silent agent hallucinations.

**Agent Chaos Monkey** simulates these real-world production faults safely in QA environments *before* code hits production.

---

## 🌟 Key Features

1. **Core Middleware (`@inject_chaos`)**: Decorates any Python function, async coroutine, or AI Agent tool to inject controlled production faults.
2. **Configurable Fault Injections**:
   - `network_latency`: Injected random latency & sleep spikes.
   - `http_502`, `http_503`, `http_429`: Upstream gateway crashes and rate limits.
   - `corrupted_json`: Truncated or malformed JSON payloads returned from tool APIs.
   - `empty_response`: Unexpected 0-byte or `None` payloads.
3. **Telemetry & Token Burn Tracker**:
   - Computes an **Agent Resilience Score (0 to 100)**.
   - Tracks **Wasted LLM Token Burn** caused by unhandled retry loops.
   - Estimates **Monthly Leak Risk ($ USD)**.
4. **Executive HTML Audit Dashboard**:
   - Standalone dark-themed executive dashboard featuring resilience gauges, fault distribution charts, and interactive step-by-step trace logs.
5. **Autonomous Lead Hunter Bot (`lead_hunter_bot.py`)**:
   - Scans GitHub repositories via AST analysis for vulnerable CrewAI patterns (`Agent()` missing `max_iter`, unprotected tool handlers), runs chaos simulations, generates client audit packages, and dispatches real-time Discord notifications.

---

## 📁 Repository Structure

```
agent-chaos-monkey/
├── chaos_engine/             # Core Middleware Package
│   ├── __init__.py           # Package exports
│   ├── ast_scanner.py        # Static AST Code Scanner CLI & engine
│   ├── config.py             # Fault types & financial leak settings
│   ├── exceptions.py         # Custom chaos exceptions
│   ├── decorator.py          # @inject_chaos decorator middleware
│   ├── telemetry.py          # Token burn & resilience calculator
│   └── reporter.py           # Dark-theme HTML audit dashboard generator
├── agent_chaos_monkey/       # Package Alias
│   └── __init__.py
├── examples/
│   └── test_refund_agent.py  # Zero-API-key sandbox demo
├── tests/
│   ├── test_ast_scanner.py   # AST scanner unit tests
│   ├── test_decorator.py     # Decorator unit tests
│   ├── test_telemetry.py     # Telemetry & scoring unit tests
│   └── test_reporter.py      # HTML reporter unit tests
├── .env.example              # Environment variables template
├── .gitignore                # Security exclusion rules
├── requirements.txt          # Python dependencies
└── setup.py                  # Package installer
```

---

## 🚀 Quickstart & Usage

### 1. Installation

```bash
pip install -e .
```

### 2. Decorating Agent Tools with `@inject_chaos`

```python
from chaos_engine import inject_chaos, FaultType, generate_html_report

# Inject 50% rate of HTTP 502 & Corrupted JSON faults into tool API
@inject_chaos(rate=0.5, faults=[FaultType.HTTP_502, FaultType.CORRUPTED_JSON])
def fetch_stripe_customer(customer_id: str) -> str:
    # Tool logic here...
    return '{"status": "active", "balance": 150.0}'

# Execute your agent workflow...
try:
    data = fetch_stripe_customer("CUST-99")
except Exception as e:
    print(f"Agent fallback engaged: {e}")

# Generate Executive HTML Audit Report
report_path = generate_html_report(output_filepath="reports/resilience_audit.html")
print(f"Audit Report generated at: {report_path}")
```

---

## 🔍 Static AST Code Scanner (`python -m chaos_engine.ast_scanner`)

Detect missing circuit breakers and unprotected `@tool` handlers in your agent codebase *statically* without executing code or making API calls.

### CLI Usage

```bash
# Scan current directory or specific target folder/file
python -m chaos_engine.ast_scanner ./src

# Scan and generate an Executive HTML Scorecard Report
python -m chaos_engine.ast_scanner ./src --report --output reports/ast_scorecard.html
```

### What it Detects:

1. **CrewAI `Agent()` Missing Circuit Breakers**:
   - Flags `Agent()` initializations missing `max_iter` or `max_execution_time`.
   - Elevates severity to **CRITICAL** if `allow_delegation=True` (preventing infinite delegation loop cascades).
2. **Unprotected `@tool` Functions**:
   - Flags `@tool` handlers lacking `try-except` blocks against network, HTTP 502, or JSON parsing errors.
3. **Resilience Score (0 to 100)**:
   - Computes a static health score based on severity weights.

---

## 🧪 Running the Sandbox Demo

Run the mock e-commerce refund test suite without paid API keys:

```bash
python examples/test_refund_agent.py
```

This compares an **Unprotected Agent** (unbounded retries & high token burn) against a **Resilient Agent** (fallback cache & circuit breaker), rendering a side-by-side terminal comparison and producing `reports/resilience_audit_report.html`.

---

## 🤖 Lead Hunter Bot & Discord Alerts

The included `lead_hunter_bot.py` scans GitHub repositories for vulnerable agent configurations, generates client audit packages, and dispatches real-time alerts to Discord.

### Setup Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Set your credentials:
   ```env
   GITHUB_TOKEN=your_github_personal_access_token
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url
   ```

### Launch Lead Hunter Bot

```bash
python lead_hunter_bot.py
```

---

## 🔄 CI/CD & Automated Testing Instructions

Integrate Agent Chaos Monkey directly into your GitHub Actions workflow (`.github/workflows/chaos-test.yml`):

```yaml
name: Agent Chaos Monkey QA Suite

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  chaos-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .
          pip install pytest pytest-asyncio
      - name: Run Unit Tests & Reliability Suite
        run: |
          pytest
          python examples/test_refund_agent.py
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for details.
