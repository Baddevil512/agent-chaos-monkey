"""
Ship Achievement CLI Utility — Agentic Chaos Monkey Proof-of-Work Engine
Appends new engineering milestones to docs/achievements.json, updates live metrics,
generates a Build-in-Public LinkedIn post (via Gemini API or smart template),
dispatches 1-Click LinkedIn Share links to Discord, triggers Make/Zapier LinkedIn automation webhook if present,
and commits/pushes to GitHub main branch.
"""

import os
import sys
import json
import argparse
import urllib.parse
import subprocess
import requests
from datetime import datetime, timezone

# Ensure UTF-8 output handling
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from dotenv import load_dotenv
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
MAKE_LINKEDIN_WEBHOOK_URL = os.getenv("MAKE_LINKEDIN_WEBHOOK_URL", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

ACHIEVEMENTS_FILE = os.path.join(os.path.dirname(__file__), "docs", "achievements.json")

def generate_linkedin_post(title: str, category: str, desc: str, link: str) -> str:
    """Generates an engaging Build-in-Public LinkedIn post via Gemini API or smart fallback."""
    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = (
                f"You are a top 1% AI Engineer & Systems Builder sharing a new engineering win on LinkedIn.\n"
                f"Title: {title}\nCategory: {category}\nDescription: {desc}\nProof Link: {link}\n\n"
                f"Write a concise, high-converting, professional 'Build in Public' LinkedIn post with emojis, key impact points, hashtags, and a call to action to verify the proof link."
            )
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
        except Exception as e:
            print(f"  ⚠️ Gemini API post generation fallback: {e}")

    # Fallback Smart Template
    return f"""🚀 Shipped New Engineering Milestone!

📌 Category: {category}
🏆 Title: {title}

💡 What it is & Impact:
{desc}

🔍 Verify Live System & Proof:
👉 {link}

Built & verified using Python & Agentic Chaos Monkey Reliability Suite. 

#BuildInPublic #AI #Python #SoftwareEngineering #AgenticAI #CloudArchitecture #TechInnovation"""

def ship_achievement(title: str, category: str, desc: str, link: str):
    print("🚀 Shipping new Proof-of-Work achievement...")

    if not os.path.exists(ACHIEVEMENTS_FILE):
        data = {"metrics_summary": {"confirmed_bugs": 0, "cloud_saas_actors": 0, "repos_audited": "50+"}, "achievements": []}
    else:
        with open(ACHIEVEMENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

    metrics = data.get("metrics_summary", {"confirmed_bugs": 0, "cloud_saas_actors": 0, "repos_audited": "50+"})
    achievements = data.get("achievements", [])

    # Update metric counters
    if category == "CONFIRMED BUG CATCH":
        metrics["confirmed_bugs"] = metrics.get("confirmed_bugs", 0) + 1
    elif category == "CLOUD SAAS ACTOR":
        metrics["cloud_saas_actors"] = metrics.get("cloud_saas_actors", 0) + 1

    new_id = f"ach-{len(achievements) + 1:03d}"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new_entry = {
        "id": new_id,
        "title": title,
        "category": category,
        "description": desc,
        "proof_link": link,
        "date": today_str
    }

    achievements.insert(0, new_entry) # Put newest first
    data["metrics_summary"] = metrics
    data["achievements"] = achievements

    with open(ACHIEVEMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"  ✅ Appended achievement '{title}' to docs/achievements.json")

    # Generate LinkedIn Post
    post_text = generate_linkedin_post(title, category, desc, link)

    # Build 1-Click LinkedIn Share URL
    encoded_text = urllib.parse.quote(post_text)
    linkedin_share_url = f"https://www.linkedin.com/feed/?shareActive=true&text={encoded_text}"

    print(f"\n📝 Generated Build-in-Public LinkedIn Post:\n{'-'*50}\n{post_text}\n{'-'*50}")
    print(f"\n🔗 1-Click LinkedIn Share URL:\n👉 {linkedin_share_url}\n")

    # Dispatch to Discord Webhook
    if DISCORD_WEBHOOK_URL:
        embed_payload = {
            "username": "Proof-of-Work Engine 🏆",
            "avatar_url": "https://raw.githubusercontent.com/Baddevil512/agent-chaos-monkey/main/docs/assets/logo.png",
            "embeds": [
                {
                    "title": f"🏆 New Milestone Shipped: {title}",
                    "url": link,
                    "color": 0x38bdf8,
                    "fields": [
                        {"name": "📌 Category", "value": f"`{category}`", "inline": True},
                        {"name": "📅 Date", "value": f"`{today_str}`", "inline": True},
                        {"name": "💡 Description", "value": desc, "inline": False},
                        {"name": "🔗 Proof Link", "value": f"[Verify Proof ↗]({link})", "inline": False},
                        {"name": "📱 1-Click Share to LinkedIn", "value": f"[👉 **Post to LinkedIn in 1-Click**]({linkedin_share_url})", "inline": False},
                        {"name": "📝 LinkedIn Post Copy", "value": f"```markdown\n{post_text[:800]}\n```", "inline": False}
                    ],
                    "footer": {"text": "Agentic Chaos Monkey • Proof-of-Work & Shipped SaaS Engine"}
                }
            ]
        }
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=embed_payload, timeout=10)
            if resp.status_code in (200, 204):
                print("  ✅ Dispatched achievement announcement & 1-click share link to Discord!")
            else:
                print(f"  ⚠️ Discord dispatch status: {resp.status_code}")
        except Exception as e:
            print(f"  ⚠️ Discord dispatch exception: {e}")

    # Optionally trigger Make/Zapier Webhook for hands-free auto-posting
    if MAKE_LINKEDIN_WEBHOOK_URL:
        try:
            requests.post(MAKE_LINKEDIN_WEBHOOK_URL, json={"text": post_text, "link": link, "title": title}, timeout=10)
            print("  🤖 Sent payload to Make/Zapier LinkedIn automation webhook!")
        except Exception as e:
            print(f"  ⚠️ Make webhook error: {e}")

    # Git commit & push
    try:
        subprocess.run(["git", "add", "docs/achievements.json"], check=True)
        subprocess.run(["git", "commit", "-m", f"feat(achievements): ship new achievement '{title}'"], check=True)
        push_res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
        if push_res.returncode == 0:
            print("  🚀 Automatically pushed docs/achievements.json to GitHub main branch!")
        else:
            print(f"  ⚠️ Git push output: {push_res.stderr.strip()[:100]}")
    except Exception as e:
        print(f"  ⚠️ Git commit/push step error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Ship new Proof-of-Work achievement & auto-publish to website, LinkedIn, and Discord.")
    parser.add_argument("--title", required=True, help="Title of the achievement or milestone")
    parser.add_argument("--category", default="SECURITY ENGINE", choices=["CONFIRMED BUG CATCH", "CLOUD SAAS ACTOR", "SECURITY ENGINE", "ENGINEERING MILESTONE"], help="Category of achievement")
    parser.add_argument("--desc", required=True, help="Description of the win / impact")
    parser.add_argument("--link", default="https://github.com/baddevil512/agent-chaos-monkey", help="Proof URL (GitHub Issue, Apify Actor, PR, Live system)")

    args = parser.parse_args()
    ship_achievement(title=args.title, category=args.category, desc=args.desc, link=args.link)

if __name__ == "__main__":
    main()
