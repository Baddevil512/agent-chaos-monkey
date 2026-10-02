"""
Discord Webhook Alert Dispatcher for Agentic Chaos Monkey
Reads OUTREACH_TARGETS.md (or receives targets list) and dispatches clean, rich Discord embed cards
with 1-click pre-filled live cloud scanner links, direct vulnerable file links, 1-click GitHub Issue creation links,
and ready-to-copy founder pitches.
"""

import os
import sys
import time
import re
import json
import urllib.parse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# UTF-8 stdout configuration for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def parse_outreach_targets_md(filepath: str = "OUTREACH_TARGETS.md") -> list:
    """Parses OUTREACH_TARGETS.md file into structured target dictionaries."""
    if not os.path.exists(filepath):
        print(f"❌ Error: {filepath} does not exist.")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by target headers: ### 1. [owner/repo](url)
    target_blocks = re.split(r'\n### \d+\. \[', content)[1:]
    targets = []

    for block in target_blocks:
        try:
            repo_match = re.search(r'^([^\]]+)\]\(([^)]+)\)', block)
            if not repo_match:
                continue
            repo_name = repo_match.group(1)
            html_url = repo_match.group(2)

            stars_match = re.search(r'⭐\s*(\d+)', block)
            stars = stars_match.group(1) if stars_match else "N/A"

            score_match = re.search(r'Score `([^`]+)` \(Grade \*\*([^*]+)\*\*\)', block)
            score = score_match.group(1) if score_match else "0.0/100"
            grade = score_match.group(2) if score_match else "F"

            link_match = re.search(r'1-Click Live Scanner Link\*\*: \[([^\]]+)\]', block)
            one_click = link_match.group(1) if link_match else f"https://baddevil512.github.io/agent-chaos-monkey/?repo={repo_name}"

            # Extract Top Findings & File/Line details
            findings = []
            first_file_path = ""
            first_line_num = ""

            findings_section = re.search(r'#### Top Findings:\s*\n(.*?)(?=\n####|\Z)', block, re.DOTALL)
            if findings_section:
                findings_lines = findings_section.group(1).strip().split('\n')
                for line in findings_lines:
                    if line.strip().startswith('- **['):
                        finding_str = line.strip().lstrip('- ').strip()
                        findings.append(finding_str)

                        # Extract first file path and line number for direct link
                        if not first_file_path:
                            file_line_match = re.search(r'at `([^:]+):(\d+)`', finding_str)
                            if file_line_match:
                                first_file_path = file_line_match.group(1)
                                first_line_num = file_line_match.group(2)

            # Extract Pitch block
            pitch_match = re.search(r'```markdown\s*\n(.*?)\n```', block, re.DOTALL)
            pitch_text = pitch_match.group(1).strip() if pitch_match else ""

            # Direct vulnerable file URL
            if first_file_path and first_line_num:
                vulnerable_file_url = f"https://github.com/{repo_name}/blob/main/{first_file_path}#L{first_line_num}"
            elif first_file_path:
                vulnerable_file_url = f"https://github.com/{repo_name}/blob/main/{first_file_path}"
            else:
                vulnerable_file_url = html_url

            # Short concise pre-filled GitHub Issue URL
            short_title = urllib.parse.quote("Reliability Advisory: Potential infinite retry loop & missing circuit breakers")
            short_body = urllib.parse.quote(
                f"Hey team! We ran a static AST audit on `{repo_name}` and identified potential infinite loops and missing circuit breakers (`max_iter`).\n\n"
                f"⚡ View 1-Click Interactive Cloud Report:\n{one_click}"
            )
            create_issue_url = f"https://github.com/{repo_name}/issues/new?title={short_title}&body={short_body}"

            targets.append({
                "repo_name": repo_name,
                "html_url": html_url,
                "stars": stars,
                "score": score,
                "grade": grade,
                "one_click": one_click,
                "vulnerable_file_url": vulnerable_file_url,
                "create_issue_url": create_issue_url,
                "findings": findings,
                "pitch": pitch_text
            })
        except Exception as e:
            print(f"⚠️ Error parsing target block: {e}")

    return targets

def send_embed_to_discord(target: dict) -> bool:
    """Dispatches a single target embed card to Discord Webhook."""
    if not DISCORD_WEBHOOK_URL:
        print("❌ Error: DISCORD_WEBHOOK_URL is not set in environment or .env file.")
        return False

    repo_name = target["repo_name"]
    html_url = target["html_url"]
    stars = target["stars"]
    score = target["score"]
    grade = target["grade"]
    one_click = target["one_click"]
    vulnerable_file_url = target.get("vulnerable_file_url", html_url)
    create_issue_url = target.get("create_issue_url", f"https://github.com/{repo_name}/issues/new")
    findings = target.get("findings", [])
    pitch = target.get("pitch", "")

    # Embed color based on grade
    if grade in ("F", "D"):
        color = 0xef4444  # Rose/Red
    elif grade == "C":
        color = 0xf59e0b  # Amber/Yellow
    else:
        color = 0x10b981  # Emerald/Green

    findings_text = "\n".join([f"• {f}" for f in findings[:3]]) if findings else "• Code fault surface issues detected."

    # Discord field limit is 1024 chars
    if len(pitch) > 600:
        pitch_codeblock = f"```markdown\n{pitch[:550]}...\n```"
    else:
        pitch_codeblock = f"```markdown\n{pitch}\n```"

    action_links_text = (
        f"👉 [Open Vulnerable File]({vulnerable_file_url})\n"
        f"⚡ [Create GitHub Issue (1-Click)]({create_issue_url})\n"
        f"🌐 [Run Live Cloud Scanner]({one_click})"
    )

    payload = {
        "username": "Agentic Chaos Monkey Lead Bot 🐒⚡",
        "avatar_url": "https://raw.githubusercontent.com/Baddevil512/agent-chaos-monkey/main/docs/assets/logo.png",
        "embeds": [
            {
                "title": f"🎯 B2B Lead Found: {repo_name}",
                "url": html_url,
                "color": color,
                "fields": [
                    {
                        "name": "📊 Stats & Resilience Rating",
                        "value": f"⭐ **{stars}** Stars | Score: **{score}** (Grade **{grade}**)",
                        "inline": True
                    },
                    {
                        "name": "🛡️ Top AST Vulnerabilities",
                        "value": findings_text,
                        "inline": False
                    },
                    {
                        "name": "🚀 Quick Action Links",
                        "value": action_links_text,
                        "inline": False
                    },
                    {
                        "name": "💬 Ready-to-Copy Founder Pitch",
                        "value": pitch_codeblock,
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "Agentic Chaos Monkey • B2B Founder Lead Engine"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

    for attempt in range(3):
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                print(f"  ✅ Sent Discord notification for {repo_name}")
                return True
            else:
                print(f"  ⚠️ Failed to send Discord notification for {repo_name} (HTTP {resp.status_code}): {resp.text[:150]}")
                return False
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            print(f"  ❌ Error sending to Discord for {repo_name}: {e}")
            return False

def dispatch_all_targets(filepath: str = "OUTREACH_TARGETS.md"):
    """Reads OUTREACH_TARGETS.md and sends all targets to Discord with a 1.5s delay."""
    print("🚀 Reading OUTREACH_TARGETS.md and sending lead notification cards to Discord...")
    targets = parse_outreach_targets_md(filepath)
    if not targets:
        print("⚠️ No valid targets found to dispatch.")
        return

    print(f"📦 Found {len(targets)} targets. Dispatching to Discord webhook...")

    sent_count = 0
    for idx, target in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] Dispatching {target['repo_name']}...")
        if send_embed_to_discord(target):
            sent_count += 1
        time.sleep(1.5)  # Respect Discord rate limit

    print(f"\n✨ Done! Successfully sent {sent_count}/{len(targets)} lead cards to Discord.")

if __name__ == "__main__":
    dispatch_all_targets()
