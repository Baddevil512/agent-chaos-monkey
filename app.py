"""
FastAPI Server & Docker Entrypoint for Agentic Chaos Monkey 24/7 Cloud Scanner.
Serves static frontend assets from /docs (GitHub Pages) and provides API endpoints for code/repo scanning.
Port: 7860 (compatible with HuggingFace Spaces & Docker deployments).
"""

import os
import sys
import tempfile
import requests
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional

from chaos_engine import scan_directory, scan_file, ScanResult

app = FastAPI(
    title="Agentic Chaos Monkey — 24/7 Cloud Scanner API",
    description="Static Analysis & Reliability Audit Engine for AI Agents",
    version="1.0.0"
)

# Enable CORS for cross-origin browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeScanRequest(BaseModel):
    code: str
    filename: Optional[str] = "agent_workflow.py"


class RepoScanRequest(BaseModel):
    repo_url: str


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Agentic Chaos Monkey Cloud Engine"}


@app.post("/api/scan/code")
def scan_raw_code(req: CodeScanRequest):
    """Scans raw Python code content provided in request body."""
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Empty code content provided.")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(req.code)
        tmp_path = tmp.name

    try:
        vulns = scan_file(tmp_path)
        
        # Calculate resilience score & risk grade
        score = 100.0
        for v in vulns:
            if v.severity == "CRITICAL":
                score -= 25.0
            elif v.severity == "HIGH":
                score -= 15.0
            else:
                score -= 10.0

        resilience_score = round(max(0.0, min(100.0, score)), 1)
        
        if resilience_score >= 90:
            risk_grade = "A"
        elif resilience_score >= 80:
            risk_grade = "B"
        elif resilience_score >= 70:
            risk_grade = "C"
        elif resilience_score >= 50:
            risk_grade = "D"
        else:
            risk_grade = "F"

        vuln_dicts = [
            {
                "file_path": req.filename or "agent_workflow.py",
                "line_number": v.line_number,
                "category": v.category,
                "severity": v.severity,
                "symbol_name": v.symbol_name,
                "description": v.description,
                "code_snippet": v.code_snippet,
                "fix_recommendation": v.fix_recommendation
            }
            for v in vulns
        ]

        return {
            "target_path": req.filename or "agent_workflow.py",
            "scanned_files_count": 1,
            "total_issues_count": len(vulns),
            "resilience_score": resilience_score,
            "risk_grade": risk_grade,
            "vulnerabilities": vuln_dicts
        }

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/api/scan/repo")
def scan_github_repository(req: RepoScanRequest):
    """Fetches public GitHub repository trees & scans Python files."""
    url_clean = req.repo_url.strip().rstrip("/")
    if "github.com/" not in url_clean:
        raise HTTPException(status_code=400, detail="Invalid GitHub Repository URL. Expected format: https://github.com/owner/repo")

    parts = url_clean.split("github.com/")[1].split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid repository path format.")

    owner, repo = parts[0], parts[1]
    repo_name = f"{owner}/{repo}"

    # Fetch repo tree via GitHub REST API
    tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/main?recursive=1"
    headers = {"User-Agent": "Agent-Chaos-Monkey-Cloud-Scanner"}
    resp = requests.get(tree_url, headers=headers)

    if resp.status_code == 404:
        # Try master branch
        tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/master?recursive=1"
        resp = requests.get(tree_url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Unable to access GitHub repository '{repo_name}' or fetch repository tree.")

    tree_data = resp.json().get("tree", [])
    py_files = [item for item in tree_data if item.get("path", "").endswith(".py") and item.get("type") == "blob"]

    if not py_files:
        return {
            "target_path": repo_name,
            "scanned_files_count": 0,
            "total_issues_count": 0,
            "resilience_score": 100.0,
            "risk_grade": "A",
            "vulnerabilities": []
        }

    with tempfile.TemporaryDirectory() as tmp_dir:
        scanned_count = 0
        for item in py_files[:15]:  # Limit top 15 py files
            f_path = item.get("path", "")
            raw_url = f"https://raw.githubusercontent.com/{repo_name}/HEAD/{f_path}"
            r = requests.get(raw_url, headers=headers)
            if r.status_code == 200:
                scanned_count += 1
                local_file_path = os.path.join(tmp_dir, f_path.replace("/", "_"))
                with open(local_file_path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(r.text)

        res = scan_directory(tmp_dir)
        vuln_dicts = [
            {
                "file_path": v.file_path.replace(tmp_dir, "").lstrip("\\/").replace("_", "/"),
                "line_number": v.line_number,
                "category": v.category,
                "severity": v.severity,
                "symbol_name": v.symbol_name,
                "description": v.description,
                "code_snippet": v.code_snippet,
                "fix_recommendation": v.fix_recommendation
            }
            for v in res.vulnerabilities
        ]

        return {
            "target_path": repo_name,
            "scanned_files_count": scanned_count,
            "total_issues_count": len(vuln_dicts),
            "resilience_score": res.resilience_score,
            "risk_grade": res.risk_grade,
            "vulnerabilities": vuln_dicts
        }


# Mount static docs folder for GitHub Pages & Web UI
docs_dir = os.path.join(os.path.dirname(__file__), "docs")
if os.path.exists(docs_dir):
    app.mount("/docs_static", StaticFiles(directory=docs_dir), name="docs_static")

    @app.get("/", response_class=HTMLResponse)
    def read_root():
        index_path = os.path.join(docs_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return "<h1>Agentic Chaos Monkey Cloud Scanner Running</h1>"


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
