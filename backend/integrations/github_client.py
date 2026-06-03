"""
GitHub Actions API Client
Fetches workflow runs, job logs, and posts job summaries.
"""
import logging
import os
import zipfile
import io
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_ORG   = os.getenv("GITHUB_ORG", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "")
BASE_URL     = "https://api.github.com"


class GitHubClient:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.repo = f"{GITHUB_ORG}/{GITHUB_REPO}"

    def _url(self, path: str) -> str:
        return f"{BASE_URL}/repos/{self.repo}{path}"

    # ── Workflow runs ─────────────────────────────────────────────────────
    async def get_recent_runs(self, limit: int = 20, status: str = "completed") -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                self._url(f"/actions/runs?per_page={limit}&status={status}"),
                headers=self.headers, timeout=30
            )
            r.raise_for_status()
            runs = r.json().get("workflow_runs", [])
        return [
            {
                "id":           str(run["id"]),
                "name":         run["name"],
                "status":       run["status"],
                "conclusion":   run["conclusion"],
                "branch":       run["head_branch"],
                "commit":       run["head_sha"][:7],
                "created_at":   run["created_at"],
                "updated_at":   run["updated_at"],
                "html_url":     run["html_url"],
                "run_number":   run["run_number"],
            }
            for run in runs
        ]

    async def get_failed_runs(self, limit: int = 10) -> list[dict]:
        runs = await self.get_recent_runs(limit=limit * 2)
        return [r for r in runs if r["conclusion"] == "failure"][:limit]

    # ── Job logs ──────────────────────────────────────────────────────────
    async def get_run_logs(self, run_id: str) -> str:
        """Download and extract logs for a workflow run."""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(
                self._url(f"/actions/runs/{run_id}/logs"),
                headers=self.headers, timeout=60
            )
            if r.status_code == 302:
                r = await client.get(r.headers["location"], timeout=60)
            if r.status_code != 200:
                return f"Could not fetch logs (HTTP {r.status_code})"
            # Unzip log bundle
            try:
                with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                    logs = []
                    for name in zf.namelist():
                        if name.endswith(".txt"):
                            logs.append(f"=== {name} ===\n{zf.read(name).decode('utf-8', errors='replace')}")
                    return "\n\n".join(logs)[:50_000]
            except Exception:
                return r.text[:50_000]

    async def get_jobs(self, run_id: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                self._url(f"/actions/runs/{run_id}/jobs"),
                headers=self.headers, timeout=30
            )
            r.raise_for_status()
        return r.json().get("jobs", [])

    # ── Job summary ───────────────────────────────────────────────────────
    async def post_job_summary(self, run_id: str, job_id: str, markdown: str) -> bool:
        """Post RCA summary as GitHub Actions job summary."""
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self._url(f"/actions/jobs/{job_id}/summaries"),
                headers=self.headers,
                json={"summary": markdown},
                timeout=15,
            )
        success = r.status_code in (200, 201)
        if not success:
            logger.warning("Failed to post job summary: %s", r.text)
        return success

    # ── PR comment ────────────────────────────────────────────────────────
    async def post_pr_comment(self, pr_number: int, body: str) -> bool:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self._url(f"/issues/{pr_number}/comments"),
                headers=self.headers,
                json={"body": body},
                timeout=15,
            )
        return r.status_code in (200, 201)

    # ── Run artifacts ─────────────────────────────────────────────────────
    async def get_artifacts(self, run_id: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                self._url(f"/actions/runs/{run_id}/artifacts"),
                headers=self.headers, timeout=30
            )
            r.raise_for_status()
        return r.json().get("artifacts", [])

    async def get_robot_results(self, run_id: str) -> list[dict]:
        """Download robot-results artifact and parse output_merged.xml into structured failures."""
        import xml.etree.ElementTree as ET

        artifacts = await self.get_artifacts(run_id)
        robot_artifact = next(
            (a for a in artifacts if "robot-results" in a["name"]), None
        )
        if not robot_artifact:
            logger.warning("No robot-results artifact found for run %s", run_id)
            return []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(
                robot_artifact["archive_download_url"],
                headers=self.headers, timeout=60
            )
            if r.status_code != 200:
                return []
            try:
                with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                    xml_file = next(
                        (n for n in zf.namelist() if "output_merged.xml" in n or "output.xml" in n), None
                    )
                    if not xml_file:
                        return []
                    xml_content = zf.read(xml_file)
            except Exception as e:
                logger.error("Failed to read robot artifact zip: %s", e)
                return []

        failures = []
        try:
            root = ET.fromstring(xml_content)
            for test in root.findall(".//test"):
                status = test.find("status")
                if status is None or status.get("status") != "FAIL":
                    continue
                msg = status.get("message", "")
                ftype = "script_error"
                msg_low = msg.lower()
                if any(k in msg_low for k in ["ssh", "maxsessions", "connection reset", "errno 104"]):
                    ftype = "infra_flake"
                elif any(k in msg_low for k in ["ui locator", "elementclick", "angular", "css selector", "locator failure"]):
                    ftype = "ui_locator"
                elif any(k in msg_low for k in ["dns", "certificate", "vpn", "tunnel", "vmanage", "management plane"]):
                    ftype = "env_issue"
                elif any(k in msg_low for k in ["bgp", "route missing", "mpls", "real_bug", "omp", "label switching"]):
                    ftype = "real_bug"
                failures.append({
                    "test":    test.get("name", ""),
                    "suite":   test.get("source", "").split("/")[-1].replace(".robot", ""),
                    "type":    ftype,
                    "message": msg[:500],
                })
        except ET.ParseError as e:
            logger.error("Failed to parse Robot Framework XML: %s", e)

        logger.info("Parsed %d Robot Framework failures from run %s", len(failures), run_id)
        return failures


github_client = GitHubClient()
