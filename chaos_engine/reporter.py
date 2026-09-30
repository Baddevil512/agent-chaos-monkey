"""
HTML Audit Report Generator for Agent Chaos Monkey.
Generates an executive-ready, dark-themed standalone HTML dashboard report.
"""

import os
import json
from typing import Dict, Any, Optional
from datetime import datetime

from .telemetry import get_tracker, TelemetryTracker


def generate_html_report(
    summary_data: Optional[Dict[str, Any]] = None,
    output_filepath: str = "chaos_report.html",
    title: str = "Agent Chaos Monkey — Reliability Audit Report"
) -> str:
    """
    Generates a standalone dark-themed HTML report based on telemetry data.

    :param summary_data: Dictionary output from tracker.get_summary() or None to pull from global tracker.
    :param output_filepath: File path to save the HTML report.
    :param title: Custom report header title.
    :return: Absolute file path of the generated HTML report.
    """
    if summary_data is None:
        summary_data = get_tracker().get_summary()

    score = summary_data.get("resilience_score", 0.0)
    
    # Determine Health Status Badge Theme
    if score >= 80:
        health_status = "EXCELLENT RESILIENCE"
        theme_color = "#10b981"  # Emerald
        theme_glow = "rgba(16, 185, 129, 0.2)"
        theme_border = "#059669"
        health_icon = "🛡️"
    elif score >= 50:
        health_status = "MODERATE FINANCIAL & STABILITY RISK"
        theme_color = "#f59e0b"  # Amber
        theme_glow = "rgba(245, 158, 11, 0.2)"
        theme_border = "#d97706"
        health_icon = "⚠️"
    else:
        health_status = "CRITICAL FINANCIAL LEAK & UNSTABLE AGENT"
        theme_color = "#f43f5e"  # Rose
        theme_glow = "rgba(244, 63, 94, 0.2)"
        theme_border = "#e11d48"
        health_icon = "🚨"

    call_logs = summary_data.get("call_logs", [])
    fault_counts = summary_data.get("fault_counts", {})
    total_invocations = summary_data.get("total_invocations", 0)

    # Format Call Log Rows for JavaScript
    call_logs_json = json.dumps([
        {
            "call_id": log.call_id,
            "function_name": log.function_name,
            "timestamp": log.timestamp,
            "execution_time_ms": log.execution_time_ms,
            "status": log.status,
            "fault_type": log.fault_type or "-",
            "error_message": log.error_message or "",
            "input_args_summary": log.input_args_summary,
            "output_summary": log.output_summary,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "total_tokens": log.total_tokens,
            "is_retry": log.is_retry
        }
        for log in call_logs
    ])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg-main: #0b0f19;
            --bg-card: #151c2c;
            --bg-card-hover: #1e293b;
            --border-color: #2e3a52;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-cyan: #38bdf8;
            --accent-purple: #c084fc;
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
            --health-color: {theme_color};
            --health-glow: {theme_glow};
            --health-border: {theme_border};
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Fira Code', monospace, sans-serif;
        }}

        body {{
            background-color: var(--bg-main);
            color: var(--text-primary);
            padding: 2rem;
            line-height: 1.5;
        }}

        .container {{
            max-width: 1300px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 2rem;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .brand-icon {{
            font-size: 2.2rem;
            background: linear-gradient(135deg, #f43f5e, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #f8fafc, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .subtitle {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        .report-meta {{
            text-align: right;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}

        /* Executive Summary Score Card */
        .executive-banner {{
            background: linear-gradient(135deg, rgba(21, 28, 44, 0.9), rgba(15, 23, 42, 0.95));
            border: 1px solid var(--health-border);
            box-shadow: 0 10px 30px -10px var(--health-glow);
            border-radius: 16px;
            padding: 2rem;
            display: grid;
            grid-template-columns: 240px 1fr;
            gap: 2rem;
            align-items: center;
            margin-bottom: 2rem;
        }}

        .score-box {{
            text-align: center;
            padding: 1.5rem;
            background: rgba(11, 15, 25, 0.6);
            border-radius: 12px;
            border: 1px solid var(--health-border);
        }}

        .score-val {{
            font-size: 4rem;
            font-weight: 800;
            color: var(--health-color);
            line-height: 1;
            margin-bottom: 0.5rem;
            text-shadow: 0 0 20px var(--health-glow);
        }}

        .score-label {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-secondary);
        }}

        .banner-details {{
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }}

        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.4rem 1rem;
            border-radius: 30px;
            background: var(--health-glow);
            border: 1px solid var(--health-color);
            color: var(--health-color);
            font-weight: 600;
            font-size: 0.95rem;
            width: fit-content;
        }}

        /* Key Metric Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            transition: transform 0.2s, border-color 0.2s;
        }}

        .metric-card:hover {{
            transform: translateY(-2px);
            border-color: var(--accent-cyan);
        }}

        .metric-header {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }}

        .metric-val {{
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }}

        .metric-desc {{
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}

        .text-cyan {{ color: var(--accent-cyan); }}
        .text-purple {{ color: var(--accent-purple); }}
        .text-amber {{ color: var(--accent-amber); }}
        .text-rose {{ color: var(--accent-rose); }}

        /* Fault Distribution Section */
        .section-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}

        .section-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1.2rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .fault-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
        }}

        .fault-item {{
            background: rgba(11, 15, 25, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
        }}

        .fault-name {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 0.3rem;
        }}

        .fault-count {{
            font-size: 1.5rem;
            font-weight: 700;
        }}

        .progress-bar {{
            height: 4px;
            background: var(--border-color);
            border-radius: 2px;
            margin-top: 0.5rem;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
        }}

        /* Table & Filtering */
        .table-controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            gap: 1rem;
        }}

        .tabs {{
            display: flex;
            gap: 0.5rem;
        }}

        .tab-btn {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.5rem 1rem;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.2s;
        }}

        .tab-btn:hover, .tab-btn.active {{
            background: var(--accent-cyan);
            color: #0b0f19;
            font-weight: 600;
            border-color: var(--accent-cyan);
        }}

        .search-box {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.5rem 1rem;
            border-radius: 8px;
            outline: none;
            width: 250px;
            font-size: 0.85rem;
        }}

        .search-box:focus {{
            border-color: var(--accent-cyan);
        }}

        .table-wrapper {{
            overflow-x: auto;
            border: 1px solid var(--border-color);
            border-radius: 10px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.85rem;
        }}

        th {{
            background: rgba(15, 23, 42, 0.95);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 0.8rem 1rem;
            border-bottom: 1px solid var(--border-color);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
        }}

        td {{
            padding: 0.8rem 1rem;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}

        tr:hover td {{
            background: rgba(30, 41, 59, 0.4);
        }}

        .badge {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .badge-success {{ background: rgba(16, 185, 129, 0.15); color: var(--accent-green); border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge-fault {{ background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.3); }}
        .badge-fallback {{ background: rgba(56, 189, 248, 0.15); color: var(--accent-cyan); border: 1px solid rgba(56, 189, 248, 0.3); }}
        .badge-unhandled {{ background: rgba(244, 63, 94, 0.15); color: var(--accent-rose); border: 1px solid rgba(244, 63, 94, 0.3); }}

        .code-cell {{
            font-family: 'Fira Code', monospace;
            background: rgba(11, 15, 25, 0.7);
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-size: 0.8rem;
            color: var(--accent-purple);
        }}

        footer {{
            margin-top: 3rem;
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.8rem;
            border-top: 1px solid var(--border-color);
            padding-top: 1.5rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="brand-icon">🐒⚡</div>
                <div>
                    <h1>Agent Chaos Monkey</h1>
                    <div class="subtitle">QA Reliability & Token Burn Audit Report</div>
                </div>
            </div>
            <div class="report-meta">
                <div>Generated: <strong>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</strong></div>
                <div>Target Framework: <strong>CrewAI & LLM Tools</strong></div>
            </div>
        </header>

        <!-- Executive Summary Banner -->
        <div class="executive-banner">
            <div class="score-box">
                <div class="score-val">{score}</div>
                <div class="score-label">Resilience Score / 100</div>
            </div>
            <div class="banner-details">
                <div class="status-badge">
                    <span>{health_icon}</span>
                    <span>{health_status}</span>
                </div>
                <h2>Executive Reliability Diagnostics</h2>
                <p style="color: var(--text-secondary); font-size: 0.95rem;">
                    During this chaos engineering trial, <strong>{summary_data.get('faults_injected_count', 0)}</strong> fault(s) were injected across <strong>{total_invocations}</strong> tool invocations. 
                    The AI agent triggered <strong>{summary_data.get('retry_count', 0)}</strong> retries, wasting an estimated <strong>{summary_data.get('wasted_tokens', 0):,}</strong> tokens.
                </p>
            </div>
        </div>

        <!-- Metric KPI Cards -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-header">Est. Monthly Financial Leak Risk</div>
                <div class="metric-val text-rose">${summary_data.get('monthly_leak_risk_usd', 0.0):,.2f}</div>
                <div class="metric-desc">Extrapolated cost leak based on retry token burn</div>
            </div>

            <div class="metric-card">
                <div class="metric-header">Wasted Token Burn</div>
                <div class="metric-val text-amber">{summary_data.get('wasted_tokens', 0):,}</div>
                <div class="metric-desc">Out of {summary_data.get('total_tokens', 0):,} total tokens (${summary_data.get('wasted_cost_usd', 0.0):.4f} wasted)</div>
            </div>

            <div class="metric-card">
                <div class="metric-header">Fault Handling Ratio</div>
                <div class="metric-val text-cyan">{summary_data.get('fallback_handled_count', 0)} / {summary_data.get('faults_injected_count', 0)}</div>
                <div class="metric-desc">Faults gracefully handled via fallback or circuit breaker</div>
            </div>

            <div class="metric-card">
                <div class="metric-header">Retry Amplification Loops</div>
                <div class="metric-val text-purple">{summary_data.get('retry_count', 0)}</div>
                <div class="metric-desc">Tool re-invocations triggered after error</div>
            </div>
        </div>

        <!-- Fault Breakdown Section -->
        <div class="section-card">
            <div class="section-title">⚡ Injected Fault Type Breakdown</div>
            <div class="fault-grid">
                {_render_fault_breakdown_html(fault_counts, total_invocations)}
            </div>
        </div>

        <!-- Call Log Table -->
        <div class="section-card">
            <div class="section-title">📜 Detailed Execution & Chaos Call Log</div>
            
            <div class="table-controls">
                <div class="tabs">
                    <button class="tab-btn active" onclick="filterLogs('ALL')">All ({len(call_logs)})</button>
                    <button class="tab-btn" onclick="filterLogs('FAULT')">Fault Injected</button>
                    <button class="tab-btn" onclick="filterLogs('RETRY')">Retries</button>
                    <button class="tab-btn" onclick="filterLogs('FAILED')">Unhandled Failures</button>
                </div>
                <input type="text" id="searchInput" class="search-box" placeholder="Search function or error..." onkeyup="searchLogs()">
            </div>

            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Call ID</th>
                            <th>Time</th>
                            <th>Tool Function</th>
                            <th>Status</th>
                            <th>Injected Fault</th>
                            <th>Latency</th>
                            <th>Tokens</th>
                            <th>Retry</th>
                            <th>Input / Error Details</th>
                        </tr>
                    </thead>
                    <tbody id="logsTableBody">
                        <!-- Rendered dynamically by JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            Agent Chaos Monkey • Reliability & Fault Injection Suite for AI Agents • Standard Executive HTML Audit
        </footer>
    </div>

    <script>
        const logsData = {call_logs_json};

        function getStatusBadge(status) {{
            switch(status) {{
                case 'SUCCESS': return '<span class="badge badge-success">SUCCESS</span>';
                case 'FAULT_INJECTED': return '<span class="badge badge-fault">FAULT INJECTED</span>';
                case 'FALLBACK_HANDLED': return '<span class="badge badge-fallback">FALLBACK HANDLED</span>';
                case 'UNHANDLED_FAILURE': return '<span class="badge badge-unhandled">UNHANDLED FAIL</span>';
                default: return '<span class="badge">' + status + '</span>';
            }}
        }}

        function renderLogs(logs) {{
            const tbody = document.getElementById('logsTableBody');
            if (!logs || logs.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding: 2rem; color: var(--text-secondary);">No matching call records found.</td></tr>';
                return;
            }}

            tbody.innerHTML = logs.map(log => `
                <tr>
                    <td><span class="code-cell">${{log.call_id}}</span></td>
                    <td>${{log.timestamp}}</td>
                    <td><strong style="color: var(--text-primary);">${{log.function_name}}</strong></td>
                    <td>${{getStatusBadge(log.status)}}</td>
                    <td><span style="color: var(--accent-amber); font-size: 0.8rem;">${{log.fault_type !== '-' ? log.fault_type : ''}}</span></td>
                    <td>${{log.execution_time_ms}} ms</td>
                    <td>${{log.total_tokens}} tok</td>
                    <td>${{log.is_retry ? '<span style="color: var(--accent-rose); font-weight: bold;">YES</span>' : 'NO'}}</td>
                    <td>
                        <div style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary);">
                            ${{log.error_message ? '<span style="color: var(--accent-rose);">' + log.error_message + '</span>' : log.input_args_summary}}
                        </div>
                    </td>
                </tr>
            `).join('');
        }}

        let currentFilter = 'ALL';

        function filterLogs(category) {{
            currentFilter = category;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            let filtered = logsData;
            if (category === 'FAULT') {{
                filtered = logsData.filter(l => l.status === 'FAULT_INJECTED' || l.fault_type !== '-');
            }} else if (category === 'RETRY') {{
                filtered = logsData.filter(l => l.is_retry);
            }} else if (category === 'FAILED') {{
                filtered = logsData.filter(l => l.status === 'UNHANDLED_FAILURE');
            }}
            renderLogs(filtered);
        }}

        function searchLogs() {{
            const query = document.getElementById('searchInput').value.toLowerCase();
            const filtered = logsData.filter(l => 
                l.function_name.toLowerCase().includes(query) ||
                l.status.toLowerCase().includes(query) ||
                l.fault_type.toLowerCase().includes(query) ||
                l.error_message.toLowerCase().includes(query) ||
                l.input_args_summary.toLowerCase().includes(query)
            );
            renderLogs(filtered);
        }}

        // Initial render
        renderLogs(logsData);
    </script>
</body>
</html>
"""

    abs_output = os.path.abspath(output_filepath)
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output, "w", encoding="utf-8") as f:
        f.write(html_content)

    return abs_output


def _render_fault_breakdown_html(fault_counts: Dict[str, int], total_calls: int) -> str:
    """Renders HTML cards for each fault type count."""
    items = []
    fault_labels = {
        "network_latency": "Network Latency",
        "http_502": "HTTP 502 Bad Gateway",
        "http_503": "HTTP 503 Unavailable",
        "http_429": "HTTP 429 Rate Limit",
        "corrupted_json": "Corrupted JSON Payload",
        "empty_response": "Empty 0-Byte Response"
    }

    for f_key, count in fault_counts.items():
        label = fault_labels.get(f_key, f_key)
        pct = (count / max(1, total_calls)) * 100.0
        items.append(f"""
        <div class="fault-item">
            <div class="fault-name">{label}</div>
            <div class="fault-count">{count}</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {min(100.0, pct):.1f}%;"></div>
            </div>
        </div>
        """)
    return "".join(items)
