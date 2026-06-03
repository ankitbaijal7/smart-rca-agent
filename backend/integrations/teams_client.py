"""
Microsoft Teams Webhook Client
Posts adaptive cards for standup updates, alerts, and reports.
"""
import logging
import os
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")


class TeamsClient:
    def __init__(self):
        self.webhook_url = TEAMS_WEBHOOK_URL

    # ── Core post ─────────────────────────────────────────────────────────
    async def _post(self, payload: dict) -> bool:
        if not self.webhook_url:
            logger.warning("TEAMS_WEBHOOK_URL not set — skipping Teams notification")
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(self.webhook_url, json=payload, timeout=15)
        ok = r.status_code == 200
        if not ok:
            logger.error("Teams post failed: %s %s", r.status_code, r.text)
        return ok

    # ── Standup update ────────────────────────────────────────────────────
    async def post_standup(
        self,
        summary: str,
        failures: list[dict],
        run_stats: dict,
        github_url: str = "",
    ) -> bool:
        color = "attention" if run_stats.get("failed", 0) > 0 else "good"
        status_emoji = "🔴" if run_stats.get("failed", 0) > 0 else "🟢"

        facts = [
            {"title": "Total Runs",  "value": str(run_stats.get("total_runs", 0))},
            {"title": "Pass Rate",   "value": f"{run_stats.get('pass_rate', 0)}%"},
            {"title": "Failures",    "value": str(run_stats.get("failed", 0))},
            {"title": "Generated",   "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")},
        ]

        failure_items = "\n".join(
            f"• **{f.get('test','?')}** — {f.get('type','?')} → _{f.get('fix','see RCA')}_"
            for f in failures[:5]
        )

        payload = {
            "@type":      "MessageCard",
            "@context":   "http://schema.org/extensions",
            "themeColor": "00d9a3" if color == "good" else "f85149",
            "summary":    "Smart RCA Morning Standup",
            "sections": [
                {
                    "activityTitle":    f"{status_emoji} **Smart RCA — Morning Standup**",
                    "activitySubtitle": datetime.utcnow().strftime("%A %d %B %Y"),
                    "activityText":     summary,
                    "facts":            facts,
                },
                {
                    "title": "🔍 Failure Breakdown",
                    "text":  failure_items or "No failures 🎉",
                },
            ],
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name":  "View GitHub Actions",
                    "targets": [{"os": "default", "uri": github_url or "https://github.com"}],
                }
            ] if github_url else [],
        }
        return await self._post(payload)

    # ── RCA alert ─────────────────────────────────────────────────────────
    async def post_rca_alert(
        self,
        test_name: str,
        failure_type: str,
        root_cause: str,
        fix: str,
        jira_key: str = "",
        run_url: str = "",
    ) -> bool:
        color = {"real_bug": "f85149", "infra_flake": "d29922", "env_issue": "f7a23e"}.get(failure_type, "7c6af7")
        payload = {
            "@type":    "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary":    f"RCA Alert: {test_name}",
            "sections": [
                {
                    "activityTitle":    f"⚡ **RCA Alert — {failure_type.upper()}**",
                    "activitySubtitle": test_name,
                    "facts": [
                        {"title": "Root Cause", "value": root_cause[:200]},
                        {"title": "Suggested Fix", "value": fix[:200]},
                        {"title": "Jira", "value": jira_key or "Not created"},
                    ],
                }
            ],
            "potentialAction": [
                {"@type": "OpenUri", "name": "View Run", "targets": [{"os": "default", "uri": run_url}]},
                {"@type": "OpenUri", "name": f"Jira: {jira_key}", "targets": [{"os": "default", "uri": f"{os.getenv('JIRA_URL','')}/browse/{jira_key}"}]},
            ] if run_url else [],
        }
        return await self._post(payload)

    # ── Weekly report ─────────────────────────────────────────────────────
    async def post_weekly_report(self, report_markdown: str, stats: dict) -> bool:
        payload = {
            "@type":    "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "7c6af7",
            "summary":    "Smart RCA Weekly Report",
            "sections": [
                {
                    "activityTitle":    "📊 **Weekly Status Report — Vodafone Ready Networks**",
                    "activitySubtitle": f"w/e {datetime.utcnow().strftime('%d %B %Y')}",
                    "activityText":     report_markdown[:1000],
                    "facts": [
                        {"title": "Pass Rate",     "value": f"{stats.get('pass_rate', 0)}%"},
                        {"title": "Total Tests",   "value": str(stats.get("total_tests", 0))},
                        {"title": "Jira Bugs",     "value": str(stats.get("jira_created", 0))},
                    ],
                }
            ],
        }
        return await self._post(payload)


teams_client = TeamsClient()
