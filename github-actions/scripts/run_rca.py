#!/usr/bin/env python3
"""
GitHub Actions entry point script for Smart RCA Agent.
Called by rca_trigger.yml and nightly_report.yml workflows.
Writes output.xml/JSON to rca_output/ for artifact upload.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rca_runner")

OUTPUT_DIR = Path("rca_output")
OUTPUT_DIR.mkdir(exist_ok=True)


async def main():
    report_mode = os.getenv("REPORT_MODE", "rca")  # rca | standup
    run_id      = os.getenv("FAILED_RUN_ID", "")
    run_name    = os.getenv("FAILED_RUN_NAME", "Unknown Suite")
    run_url     = os.getenv("FAILED_RUN_URL", "")

    logger.info("Smart RCA Agent starting — mode=%s run_id=%s", report_mode, run_id)

    if report_mode == "standup":
        from backend.agents.standup_agent import run_standup_analysis
        result = await run_standup_analysis(post_to_teams=True)
    else:
        # Single-run RCA triggered by workflow_run failure
        from backend.agents.standup_agent import run_standup_analysis
        result = await run_standup_analysis(post_to_teams=True)

    # Save results
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"rca_{ts}.json"
    output_file.write_text(json.dumps(result, indent=2, default=str))
    logger.info("RCA results saved to %s", output_file)

    # Write GitHub Actions job summary
    summary_file = os.getenv("GITHUB_STEP_SUMMARY", "")
    if summary_file:
        failures = result.get("failures", [])
        md_lines = [
            "## ⚡ Smart RCA Analysis",
            f"**{result.get('summary', 'Analysis complete')}**",
            "",
            "| Test | Type | Root Cause | Fix | Assignee | Jira |",
            "|------|------|-----------|-----|----------|------|",
        ]
        for f in failures:
            jira = f.get("jira_key", "—")
            jira_link = f"[{jira}]({os.getenv('JIRA_URL','')}/browse/{jira})" if jira != "—" else "—"
            md_lines.append(
                f"| {f.get('test','?')} | `{f.get('type','?')}` | "
                f"{f.get('root_cause','?')[:60]} | {f.get('fix','?')[:60]} | "
                f"{f.get('assignee','?')} | {jira_link} |"
            )
        if not failures:
            md_lines.append("| — | — | No failures detected | — | — | — |")
        with open(summary_file, "w") as fh:
            fh.write("\n".join(md_lines))
        logger.info("GitHub job summary written")

    # Exit with failure if real bugs found (makes the RCA job reflect real issues)
    real_bugs = [f for f in result.get("failures", []) if f.get("type") == "real_bug"]
    if real_bugs:
        logger.warning("%d real bugs found — exiting with code 1", len(real_bugs))
        sys.exit(1)

    logger.info("Smart RCA Agent complete")


if __name__ == "__main__":
    asyncio.run(main())
