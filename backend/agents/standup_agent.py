"""
Pain 1 — Morning Standup Agent
LangChain agent that:
1. Fetches failed GitHub Actions runs
2. Downloads and parses logs
3. RAG-retrieves similar past failures from ChromaDB
4. LLM generates RCA + assigns team members
5. Posts to MS Teams + GitHub job summary
6. Stores new RCAs back to vector DB
"""
import json
import logging
from datetime import datetime

from backend.integrations.github_client import github_client
from backend.integrations.jira_client import jira_client
from backend.integrations.teams_client import teams_client
from backend.models.llm_router import llm_router
from backend.rag.vector_store import vector_store
from backend.utils.log_parser import parse_raw_log, failures_to_prompt

logger = logging.getLogger(__name__)

TEAM_MEMBERS = ["Praveen", "Piyush", "Sneha", "Kalyani", "Raja", "Vinay", "Nowel"]

SYSTEM_PROMPT = """You are a senior CI/CD failure analyst for the Vodafone Ready Networks SD-WAN automation programme.
Your job: analyse Robot Framework test failures, classify them, identify root causes, suggest fixes, and assign to team members.

Failure types:
- infra_flake: SSH resets, maxsessions, VM routing, DNS — usually NOT a code bug
- ui_locator: Angular/Clarity element issues — script needs updating
- env_issue: DNS, network, Splunk, cert problems — infra team action
- real_bug: actual product/config regression — raise Jira bug
- script_error: Python/RF keyword logic error — automation team fix

Team: {team_members}
Assign based on: Praveen/Piyush = VeloCloud, Sneha/Kalyani = Viptela/Meraki, Raja/Vinay = infra issues.

Always respond with valid JSON only. No markdown fences."""


async def run_standup_analysis(post_to_teams: bool = True) -> dict:
    """Main entry point for morning standup analysis."""
    logger.info("Starting morning standup analysis")

    # 1. Fetch failed runs from GitHub
    try:
        failed_runs = await github_client.get_failed_runs(limit=10)
    except Exception as e:
        logger.error("GitHub fetch failed: %s", e)
        failed_runs = []

    if not failed_runs:
        result = {"summary": "No failed runs in last 24h 🎉", "failures": [], "standup": "All CI runs passing. No action required."}
        if post_to_teams:
            await teams_client.post_standup(result["standup"], [], {"failed": 0, "pass_rate": 100, "total_runs": 0})
        return result

    # 2. For each failed run, get logs
    all_parsed = []
    for run in failed_runs[:5]:  # cap at 5 runs
        try:
            log_text = await github_client.get_run_logs(run["id"])
            parsed = parse_raw_log(log_text, run_id=run["id"], suite=run["name"])
            parsed.raw_log = log_text[:3000]
            all_parsed.append((run, parsed))
        except Exception as e:
            logger.warning("Could not fetch logs for run %s: %s", run["id"], e)

    # 3. Build RAG context from vector store
    combined_logs = " ".join(p.raw_log for _, p in all_parsed)
    rag_context = vector_store.retrieve_context(combined_logs, failure_k=5, doc_k=3)

    # 4. Build LLM prompt
    failures_text = "\n\n".join(failures_to_prompt(p) for _, p in all_parsed)
    user_prompt = f"""RAG CONTEXT (past similar failures & fixes):
{rag_context}

CURRENT CI FAILURES:
{failures_text}

Generate standup analysis. Respond ONLY with this JSON structure:
{{
  "summary": "one paragraph executive summary",
  "standup": "ready-to-post Teams message (2-3 sentences, include numbers)",
  "failures": [
    {{
      "test": "test name",
      "suite": "suite name",
      "type": "infra_flake|ui_locator|env_issue|real_bug|script_error",
      "root_cause": "one sentence",
      "fix": "actionable fix",
      "assignee": "team member name",
      "raise_jira": true|false,
      "confidence": 0.0-1.0
    }}
  ],
  "run_stats": {{
    "total_runs": 0,
    "failed": 0,
    "pass_rate": 0
  }}
}}"""

    # 5. LLM invocation
    try:
        raw = await llm_router.invoke(
            SYSTEM_PROMPT.format(team_members=", ".join(TEAM_MEMBERS)),
            user_prompt
        )
        clean = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
    except Exception as e:
        logger.error("LLM invocation/parse failed: %s", e)
        result = {
            "summary": f"LLM analysis failed: {e}",
            "standup": "CI analysis unavailable. Please check logs manually.",
            "failures": [],
            "run_stats": {"total_runs": len(failed_runs), "failed": len(failed_runs), "pass_rate": 0},
        }

    # 6. Auto-create Jira bugs for real failures
    for failure in result.get("failures", []):
        if failure.get("raise_jira") and failure.get("confidence", 0) >= 0.7:
            run_url = failed_runs[0]["html_url"] if failed_runs else ""
            jira_result = await jira_client.create_bug(
                summary=f"[Smart RCA] {failure['suite']}: {failure['test']}",
                description=f"Root cause: {failure['root_cause']}\n\nSuggested fix: {failure['fix']}\n\nType: {failure['type']}",
                priority="High" if failure["type"] == "real_bug" else "Medium",
                labels=[failure["type"], failure["suite"]],
                github_run_url=run_url,
            )
            if jira_result:
                failure["jira_key"] = jira_result["key"]

    # 7. Post to Teams
    if post_to_teams:
        await teams_client.post_standup(
            summary=result.get("standup", ""),
            failures=result.get("failures", []),
            run_stats=result.get("run_stats", {}),
            github_url=failed_runs[0]["html_url"] if failed_runs else "",
        )

    # 8. Store new failures in vector DB for future memory
    for failure in result.get("failures", []):
        if failure.get("fix") and failure["type"] != "unknown":
            vector_store.add_failure(
                failure_text=f"{failure['test']}: {failure['root_cause']}",
                fix_text=failure["fix"],
                suite=failure.get("suite", ""),
                failure_type=failure["type"],
                run_id=failed_runs[0]["id"] if failed_runs else "",
            )

    logger.info("Standup analysis complete: %d failures processed", len(result.get("failures", [])))
    return result
