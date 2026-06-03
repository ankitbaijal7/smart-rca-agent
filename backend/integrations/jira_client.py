"""
Jira REST API Client
Auto-creates bugs, links to GitHub runs, searches for duplicates.
"""
import logging
import os
from typing import Optional
import httpx
from base64 import b64encode

logger = logging.getLogger(__name__)

JIRA_URL         = os.getenv("JIRA_URL", "")
JIRA_EMAIL       = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN   = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "VRN")
JIRA_COMPONENT   = os.getenv("JIRA_COMPONENT", "SD-WAN-Automation")
AUTO_CREATE      = os.getenv("JIRA_AUTO_CREATE", "true").lower() == "true"
BUG_THRESHOLD    = float(os.getenv("JIRA_BUG_THRESHOLD", "0.7"))


class JiraClient:
    def __init__(self):
        token = b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        self.base = f"{JIRA_URL}/rest/api/3"

    # ── Search for duplicate ──────────────────────────────────────────────
    async def find_duplicate(self, summary: str) -> Optional[str]:
        """JQL search for similar open bugs. Returns issue key or None."""
        words = " ".join(summary.split()[:6])
        jql  = f'project={JIRA_PROJECT_KEY} AND summary ~ "{words}" AND status != Done ORDER BY created DESC'
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base}/search",
                headers=self.headers,
                params={"jql": jql, "maxResults": 1},
                timeout=15,
            )
        if r.status_code == 200:
            issues = r.json().get("issues", [])
            if issues:
                return issues[0]["key"]
        return None

    # ── Create bug ────────────────────────────────────────────────────────
    async def create_bug(
        self,
        summary: str,
        description: str,
        priority: str = "High",
        labels: list[str] | None = None,
        github_run_url: str = "",
    ) -> Optional[dict]:
        if not AUTO_CREATE:
            logger.info("Jira auto-create disabled, skipping")
            return None

        # Check for duplicate first
        dup = await self.find_duplicate(summary)
        if dup:
            logger.info("Duplicate found: %s — skipping creation", dup)
            await self.add_comment(dup, f"New occurrence detected.\nGitHub run: {github_run_url}")
            return {"key": dup, "duplicate": True}

        # Build description ADF (Atlassian Document Format)
        adf_desc = {
            "type": "doc", "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": description[:2000]}]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "GitHub Run: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": github_run_url or "N/A"},
                ]},
            ],
        }

        payload = {
            "fields": {
                "project":     {"key": JIRA_PROJECT_KEY},
                "issuetype":   {"name": "Bug"},
                "summary":     summary[:255],
                "description": adf_desc,
                "priority":    {"name": priority},
                "labels":      (labels or []) + ["smart-rca", "automation"],
                "components":  [{"name": JIRA_COMPONENT}],
            }
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base}/issue",
                headers=self.headers,
                json=payload,
                timeout=15,
            )

        if r.status_code == 201:
            data = r.json()
            logger.info("Jira bug created: %s", data["key"])
            return {"key": data["key"], "url": f"{JIRA_URL}/browse/{data['key']}", "duplicate": False}
        else:
            logger.error("Jira creation failed: %s %s", r.status_code, r.text)
            return None

    # ── Add comment ───────────────────────────────────────────────────────
    async def add_comment(self, issue_key: str, text: str) -> bool:
        body = {
            "body": {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
            }
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base}/issue/{issue_key}/comment",
                headers=self.headers, json=body, timeout=15,
            )
        return r.status_code == 201

    # ── Transition issue ──────────────────────────────────────────────────
    async def transition_issue(self, issue_key: str, transition_name: str = "In Progress") -> bool:
        # Get available transitions
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.base}/issue/{issue_key}/transitions", headers=self.headers, timeout=10)
            transitions = r.json().get("transitions", [])
            tid = next((t["id"] for t in transitions if t["name"] == transition_name), None)
            if not tid:
                return False
            r2 = await client.post(
                f"{self.base}/issue/{issue_key}/transitions",
                headers=self.headers,
                json={"transition": {"id": tid}},
                timeout=10,
            )
        return r2.status_code == 204


jira_client = JiraClient()
