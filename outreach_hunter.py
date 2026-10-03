import os
import sys
import time
import json
import requests
import tempfile
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set

# UTF-8 stdout setup for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

from dotenv import load_dotenv
load_dotenv()

from chaos_engine import scan_directory, scan_file, ScanResult

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

CONTACTED_REPOS_FILE = os.path.join(os.path.dirname(__file__), "contacted_repos.json")

# Framework search queries with stars:30..1000
SEARCH_QUERIES = [
    '"crewai" language:Python stars:30..1000',
    '"langgraph" language:Python stars:30..1000',
    '"autogen" language:Python stars:30..1000',
    '"mcp-server" language:Python stars:30..1000',
    '"pydantic-ai" language:Python stars:30..1000'
]

EXCLUDE_REPOS = {
    "baddevil512/agent-chaos-monkey",
    "joaomdmoura/crewai",
    "crewaiinc/crewai",
    "langchain-ai/langgraph",
    "microsoft/autogen"
}

EXCLUDE_PATH_KEYWORDS = [
    "use-cases/", "use_cases/", "examples/", "samples/",
    "_anti_patterns/", "cookbook/", "templates/", "tutorials/",
    "notebooks/", "docs/", "example/", "sample/", "tutorial/",
    "tests/", "test/", "benchmarks/", "benchmark/", "test_", "_test.py",
    "mock", "dummy"
]

def load_contacted_repos() -> Set[str]:
    """Load previously contacted/scanned repositories (case-insensitive)."""
    if os.path.exists(CONTACTED_REPOS_FILE):
        try:
            with open(CONTACTED_REPOS_FILE, "r", encoding="utf-8") as f:
                repos = json.load(f)
                if isinstance(repos, list):
                    return {r.strip().lower() for r in repos if isinstance(r, str)}
        except Exception as e:
            print(f"⚠️ Error reading {CONTACTED_REPOS_FILE}: {e}")
    return set()

def save_contacted_repo(repo_full_name: str):
    """Append a newly processed repository to contacted_repos.json."""
    current_list = []
    if os.path.exists(CONTACTED_REPOS_FILE):
        try:
            with open(CONTACTED_REPOS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    current_list = data
        except Exception:
            current_list = []

    # Check case-insensitive existence before appending
    existing_lower = {r.lower() for r in current_list}
    if repo_full_name.lower() not in existing_lower:
        current_list.append(repo_full_name)
        try:
            with open(CONTACTED_REPOS_FILE, "w", encoding="utf-8") as f:
                json.dump(current_list, f, indent=2)
            print(f"💾 Added '{repo_full_name}' to {CONTACTED_REPOS_FILE}")
        except Exception as e:
            print(f"⚠️ Error updating {CONTACTED_REPOS_FILE}: {e}")

def search_github_repos(contacted: Set[str]) -> List[Dict[str, Any]]:
    """Search GitHub for active python repos matching target agent frameworks."""
    print("🔍 Searching GitHub for fresh AI agent repositories (30 - 1000 stars)...")
    repos_map = {}

    for query in SEARCH_QUERIES:
        url = f"https://api.github.com/search/repositories?q={query}&sort=updated&order=desc&per_page=30"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                print(f"  Found {len(items)} candidates for query: {query}")
                for item in items:
                    full_name = item.get("full_name", "")
                    if not full_name:
                        continue
                    full_name_lower = full_name.lower()
                    if full_name_lower in EXCLUDE_REPOS or full_name_lower in contacted:
                        continue
                    if not item.get("archived") and item.get("has_issues", True):
                        repos_map[full_name_lower] = item
            else:
                print(f"  ⚠️ Search query '{query}' failed with status {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  ⚠️ Error searching GitHub with query '{query}': {e}")
        time.sleep(1.5)

    return list(repos_map.values())

def is_excluded_path(file_path: str) -> bool:
    """Check if file path contains benchmark, test, example, mock, or dummy keywords."""
    path_lower = file_path.lower()
    return any(kw in path_lower for kw in EXCLUDE_PATH_KEYWORDS)

def analyze_repo(repo_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetches top python files from repo and runs AST static analyzer."""
    repo_name = repo_item.get("full_name", "")
    stars = repo_item.get("stargazers_count", 0)
    html_url = repo_item.get("html_url", f"https://github.com/{repo_name}")
    owner_url = repo_item.get("owner", {}).get("html_url", f"https://github.com/{repo_name.split('/')[0]}")
    owner_login = repo_item.get("owner", {}).get("login", repo_name.split('/')[0])
    pushed_at = repo_item.get("pushed_at", "")

    # Fetch tree
    tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/main?recursive=1"
    try:
        resp = requests.get(tree_url, headers=HEADERS, timeout=10)
        if resp.status_code == 404:
            tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/master?recursive=1"
            resp = requests.get(tree_url, headers=HEADERS, timeout=10)
    except Exception as e:
        print(f"  ⚠️ Error fetching tree for {repo_name}: {e}")
        return None

    if resp.status_code != 200:
        return None

    tree_data = resp.json().get("tree", [])
    py_files = []
    for item in tree_data:
        path = item.get("path", "")
        if path.endswith(".py") and item.get("type") == "blob":
            # Exclude test, benchmark, example, mock, dummy paths
            if not is_excluded_path(path):
                py_files.append(item)

    if not py_files:
        return None

    # Limit to top 15 py files per repo
    py_files = py_files[:15]

    with tempfile.TemporaryDirectory() as tmp_dir:
        downloaded = 0
        file_mapping = {}
        for item in py_files:
            f_path = item.get("path", "")
            raw_url = f"https://raw.githubusercontent.com/{repo_name}/HEAD/{f_path}"
            try:
                r = requests.get(raw_url, headers=HEADERS, timeout=10)
                if r.status_code == 200:
                    safe_filename = f_path.replace("/", "_")
                    local_path = os.path.join(tmp_dir, safe_filename)
                    with open(local_path, "w", encoding="utf-8", errors="ignore") as f:
                        f.write(r.text)
                    file_mapping[safe_filename] = f_path
                    downloaded += 1
            except Exception as e:
                print(f"  ⚠️ Error downloading {f_path}: {e}")
                continue

        if downloaded == 0:
            return None

        scan_res = scan_directory(tmp_dir)

        # Filter vulnerabilities strictly excluding test/benchmark/example/mock/dummy file paths
        vulns_data = []
        for v in scan_res.vulnerabilities:
            clean_rel_path = v.file_path.replace(tmp_dir, "").lstrip("\\/")
            actual_path = file_mapping.get(clean_rel_path, clean_rel_path.replace("_", "/"))
            
            # Double-check file path exclusion
            if is_excluded_path(actual_path):
                continue

            vulns_data.append({
                "file_path": actual_path,
                "line_number": v.line_number,
                "category": v.category,
                "severity": v.severity,
                "description": v.description,
                "code_snippet": v.code_snippet,
                "fix_recommendation": v.fix_recommendation
            })

        critical_high_vulns = [
            v for v in vulns_data
            if v["severity"] in ("CRITICAL", "HIGH")
        ]

        if not critical_high_vulns:
            return None

        # Calculate severity priority score
        crit_count = sum(1 for v in vulns_data if v["severity"] == "CRITICAL")
        high_count = sum(1 for v in vulns_data if v["severity"] == "HIGH")

        return {
            "repo_name": repo_name,
            "stars": stars,
            "html_url": html_url,
            "owner_url": owner_url,
            "owner_login": owner_login,
            "pushed_at": pushed_at,
            "resilience_score": scan_res.resilience_score,
            "risk_grade": scan_res.risk_grade,
            "total_issues": len(vulns_data),
            "crit_count": crit_count,
            "high_count": high_count,
            "vulnerabilities": vulns_data,
            "one_click_link": f"https://baddevil512.github.io/agent-chaos-monkey/?repo={repo_name}"
        }

def generate_pitch(target: Dict[str, Any]) -> str:
    """Generate personalized founder outreach pitch."""
    repo_name = target["repo_name"]
    top_vulns = target["vulnerabilities"][:2]
    one_click = target["one_click_link"]

    vuln_bullets = ""
    for idx, v in enumerate(top_vulns, 1):
        vuln_bullets += f"  {idx}. **`{v['category']}`** in `{v['file_path']}` (Line {v['line_number']})\n     - *Impact*: {v['description']}\n"

    pitch = f"""Hey {target['owner_login']} Team 👋

We ran an automated static AST reliability audit across active AI agent codebases and noticed a couple of potential production fault traps in **[{repo_name}]({target['html_url']})**:

{vuln_bullets}
When upstream APIs experience rate limits (HTTP 429), gateway drops (HTTP 502), or network latency spikes, these missing circuit breakers can cause unhandled retry cascades and unnecessary token burn.

⚡ **View Live Interactive Audit Dashboard (1-Click Run)**:
👉 [{one_click}]({one_click})

We built **Agentic Chaos Monkey** to help AI teams inject synthetic production faults during QA and test agent resilience before deploying to production.

Feel free to run the free cloud scan above or check out our open-source suite: https://github.com/Baddevil512/agent-chaos-monkey

Best,
Abhay & Agentic Chaos Monkey Team
"""
    return pitch

def build_outreach_targets_md(targets: List[Dict[str, Any]], filepath: str = "OUTREACH_TARGETS.md"):
    """Build OUTREACH_TARGETS.md report."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    md = f"""# 🐒⚡ B2B Founder Outreach & Lead Generation Targets
> Generated automatically by `outreach_hunter.py` on {now_str}
> Total Verified Targets: **{len(targets)}** High-Value Repositories with Critical Fault Risks

---

## 📊 Summary of Qualified Targets

| # | Repository | Stars | Resilience Score | Risk Grade | Critical Issues | 1-Click Live Audit Link |
|---|------------|-------|------------------|------------|-----------------|-------------------------|
"""

    for idx, t in enumerate(targets, 1):
        md += f"| {idx} | [{t['repo_name']}]({t['html_url']}) | ⭐ {t['stars']} | `{t['resilience_score']}/100` | **Grade {t['risk_grade']}** | {t['crit_count']} Critical, {t['high_count']} High | [Run Live Scan 🚀]({t['one_click_link']}) |\n"

    md += "\n---\n\n## 🎯 Target Outreach Profiles & Pre-filled Pitches\n\n"

    for idx, t in enumerate(targets, 1):
        top_2 = t["vulnerabilities"][:2]
        md += f"### {idx}. [{t['repo_name']}]({t['html_url']})\n\n"
        md += f"- **Owner / Org Profile**: [{t['owner_login']}]({t['owner_url']})\n"
        md += f"- **GitHub Stars**: ⭐ {t['stars']}\n"
        md += f"- **Agent Resilience Rating**: Score `{t['resilience_score']}/100` (Grade **{t['risk_grade']}**)\n"
        md += f"- **1-Click Live Scanner Link**: [{t['one_click_link']}]({t['one_click_link']})\n\n"

        md += f"#### Top Findings:\n"
        for v in top_2:
            md += f"- **[{v['severity']}] {v['category']}** at `{v['file_path']}:{v['line_number']}`\n"
            md += f"  - *Details*: {v['description']}\n"
            md += f"  - *Recommended Fix*: `{v['fix_recommendation']}`\n"
        md += "\n"

        md += f"#### Ready-to-Copy Founder DM / GitHub Issue Pitch:\n\n"
        md += "```markdown\n"
        md += generate_pitch(t)
        md += "```\n\n"
        md += "---\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"✅ Generated {filepath} with {len(targets)} high-priority targets.")

def main():
    print("🚀 Starting Agentic Chaos Monkey B2B Outreach Hunter Engine...")
    contacted = load_contacted_repos()
    print(f"📋 Loaded {len(contacted)} previously contacted repositories from contacted_repos.json.")

    candidates = search_github_repos(contacted)
    print(f"📦 Total fresh candidate repositories fetched: {len(candidates)}")

    qualified_targets = []

    for idx, candidate in enumerate(candidates, 1):
        repo_name = candidate.get("full_name", "")
        if repo_name.lower() in contacted:
            print(f"[{idx}/{len(candidates)}] ⏭️ Skipping previously contacted repo: {repo_name}")
            continue

        print(f"[{idx}/{len(candidates)}] Auditing AST fault surface for {repo_name}...")
        
        target_info = analyze_repo(candidate)
        if target_info:
            print(f"  🎯 QUALIFIED: {repo_name} - Score {target_info['resilience_score']}/100 (Grade {target_info['risk_grade']}) | {target_info['total_issues']} Issues Found")
            qualified_targets.append(target_info)
        else:
            print(f"  ⏭️ Skipped: No critical AST defects found or unreachable tree.")

        time.sleep(1.0)

        if len(qualified_targets) >= 5:
            print("✨ Reached target threshold of 5 brand-new qualified AI agent startups!")
            break

    if not qualified_targets:
        print("⚠️ No new qualified targets found in this run.")
        return

    # Sort qualified targets by priority (highest critical count first, then lowest resilience score)
    qualified_targets.sort(key=lambda x: (-x["crit_count"], -x["high_count"], x["resilience_score"]))
    
    top_targets = qualified_targets[:5]
    build_outreach_targets_md(top_targets)

    # Automatically dispatch to Discord webhook and update contacted_repos.json for each sent lead
    try:
        from send_to_discord import send_embed_to_discord, parse_outreach_targets_md
        parsed_targets = parse_outreach_targets_md("OUTREACH_TARGETS.md")
        sent_count = 0
        for t in parsed_targets:
            if send_embed_to_discord(t):
                sent_count += 1
                save_contacted_repo(t["repo_name"])
            time.sleep(1.5)
        print(f"✨ Dispatched {sent_count}/{len(parsed_targets)} brand-new lead notifications to Discord!")
    except Exception as e:
        print(f"⚠️ Error automatically dispatching Discord notifications: {e}")

if __name__ == "__main__":
    main()

