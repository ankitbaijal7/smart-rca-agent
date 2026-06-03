"""
Pain 3 — Auto Status Reporter Agent
Generates daily/weekly/sprint reports from CI history + Jira data.

Pain 4 — Team Knowledge Assistant Agent
RAG chatbot over runbooks + past RCAs for junior engineer self-service.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Literal

from backend.integrations.github_client import github_client
from backend.integrations.teams_client import teams_client
from backend.models.llm_router import llm_router
from backend.rag.vector_store import vector_store

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# PAIN 3 — Reporter Agent
# ═══════════════════════════════════════════════════════════════════════════

REPORTER_SYSTEM = """You are a Senior Delivery Consultant at Capgemini UK writing a status report for the Vodafone Ready Networks SD-WAN automation programme.
Write in professional British English. Be concise, factual, and highlight risks with mitigations.
Audience: Srinath (delivery manager) and Nihit Kumar (VOIS lead).
Tone: confident, delivery-focused. Use ✅ ⚠️ 🔴 for status indicators."""


async def generate_status_report(
    report_type: Literal["daily", "weekly", "sprint"] = "weekly",
    post_to_teams: bool = False,
) -> dict:
    """Generate a status report from CI run history and RAG context."""

    # Fetch run history
    try:
        runs = await github_client.get_recent_runs(limit=20)
    except Exception as e:
        logger.warning("Could not fetch GitHub runs: %s", e)
        runs = []

    # Compute stats
    total      = len(runs)
    passed     = sum(1 for r in runs if r.get("conclusion") == "success")
    failed     = sum(1 for r in runs if r.get("conclusion") == "failure")
    pass_rate  = round(passed / total * 100) if total else 0
    failed_suites = list({r["name"] for r in runs if r.get("conclusion") == "failure"})

    # RAG: recurring issues context
    rag_context = vector_store.retrieve_context(
        f"recurring failures {' '.join(failed_suites)}", failure_k=4, doc_k=2
    )

    stats_text = f"""Run Statistics:
- Report period: {report_type}
- Total workflow runs: {total}
- Passed: {passed} | Failed: {failed}
- Pass rate: {pass_rate}%
- Failed suites: {', '.join(failed_suites) or 'None'}
- Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"""

    user_prompt = f"""{stats_text}

Recurring Issues (from RAG memory):
{rag_context}

Team: Ankit Baijal (Automation Lead), Praveen, Piyush, Sneha, Kalyani, Raja, Vinay, Nowel
Programme: VeloCloud SD-WAN, Cisco Viptela/Catalyst, Meraki KTLO — Vodafone Ready Networks

Generate a {report_type} status report with sections:
1. Executive Summary
2. Test Execution Results
3. Key Issues & Resolutions
4. Risks & Mitigations
5. Next Steps / Actions

Respond with JSON:
{{
  "report_markdown": "full report in markdown",
  "summary_one_liner": "one sentence for subject line",
  "rag_issues_flagged": ["list of recurring issues mentioned"],
  "stats": {{
    "total_runs": 0, "passed": 0, "failed": 0,
    "pass_rate": 0, "failed_suites": []
  }}
}}"""

    try:
        raw = await llm_router.invoke(REPORTER_SYSTEM, user_prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        result["report_type"] = report_type
    except Exception as e:
        result = {
            "report_markdown": f"Report generation failed: {e}",
            "summary_one_liner": "Error generating report",
            "stats": {"total_runs": total, "passed": passed, "failed": failed, "pass_rate": pass_rate},
            "report_type": report_type,
        }

    if post_to_teams:
        await teams_client.post_weekly_report(
            result.get("report_markdown", "")[:1000],
            result.get("stats", {}),
        )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# PAIN 4 — Knowledge Assistant Agent
# ═══════════════════════════════════════════════════════════════════════════

KNOWLEDGE_SYSTEM = """You are the Smart RCA Knowledge Assistant for the Vodafone Ready Networks SD-WAN automation team at Capgemini UK.

You have deep expertise in:
- VeloCloud SD-WAN (EFS, CCFW, BGP-BFD, Partner Gateway, business policies)
- Cisco Viptela / Catalyst SD-WAN
- Meraki (MR/MS/MX, Dashboard API)
- Robot Framework, Python, SSH automation
- GitHub Actions CI/CD (self-hosted runners, workflow YAML)
- Nokia TiMOS, BGP, BFD, traceroute validation
- Linux networking (routing, iptables, systemd)

Use the RAG context provided to give precise, accurate answers.
When you have an exact command or fix, always include it.
For onboarding questions, give step-by-step guidance.
Be direct and concise — engineers need fast answers."""


async def knowledge_chat(
    user_message: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """RAG-augmented chat for team knowledge assistant."""

    # Semantic search over both collections
    rag_context = vector_store.retrieve_context(user_message, failure_k=4, doc_k=3)

    # Build conversation context
    history_text = ""
    if conversation_history:
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:200]}"
            for m in conversation_history[-6:]
        )

    history_section = ("CONVERSATION HISTORY:\n" + history_text) if history_text else ""

    user_prompt = f"""RAG CONTEXT:
{rag_context}

{history_section}

USER QUESTION: {user_message}

Provide a helpful, accurate answer. Include exact commands/code where applicable."""

    answer = await llm_router.invoke(KNOWLEDGE_SYSTEM, user_prompt)

    # Find relevant docs for citations
    doc_hits = vector_store.search_docs(user_message, top_k=2)
    sources = [{"title": d["title"], "score": d["score"]} for d in doc_hits if d["score"] > 0.3]

    return {
        "answer":   answer,
        "sources":  sources,
        "rag_used": bool(rag_context and "No relevant" not in rag_context),
    }
