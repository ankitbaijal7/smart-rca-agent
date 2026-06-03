"""
Log Parser — extracts structured failure data from:
  - Robot Framework output.xml
  - GitHub Actions raw log text
  - Plain text CI logs
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedFailure:
    test_name:    str
    suite_name:   str
    error_message: str
    stack_trace:  str = ""
    failure_type: str = "unknown"   # infra_flake | ui_locator | env_issue | real_bug | script_error
    keywords:     list[str] = field(default_factory=list)
    duration_ms:  int = 0


@dataclass
class ParsedRun:
    run_id:    str
    suite:     str
    status:    str
    total:     int
    passed:    int
    failed:    int
    failures:  list[ParsedFailure] = field(default_factory=list)
    raw_log:   str = ""


# ── Failure type heuristics ───────────────────────────────────────────────
_PATTERNS = [
    (r"(maxsessions|connection.?reset|errno 104|ssh.*drop|connectionreset)", "infra_flake"),
    (r"(elementclick|intercepted|overlay|angular|clarity|stale.*element)", "ui_locator"),
    (r"(dns|name or service|gaierror|errno -2|resolv)", "env_issue"),
    (r"(route.*not found|bgp|bfd|traceroute|next.?hop|metric 0)", "real_bug"),
    (r"(timos|nokia.*hang|no response|timeout.*ssh|session.*timed)", "infra_flake"),
    (r"(assertionerror|keyerror|typeerror|syntaxerror|nameerror)", "script_error"),
    (r"(splunk|license|quota|permission denied)", "env_issue"),
]

def classify_failure(text: str) -> str:
    t = text.lower()
    for pattern, ftype in _PATTERNS:
        if re.search(pattern, t):
            return ftype
    return "unknown"


# ── Robot Framework XML parser ────────────────────────────────────────────
def parse_robot_xml(xml_content: str, run_id: str = "") -> ParsedRun:
    root = ET.fromstring(xml_content)
    suite_el = root.find("suite")
    suite_name = suite_el.attrib.get("name", "Unknown") if suite_el else "Unknown"

    stat_el = root.find(".//total/stat")
    passed = int(stat_el.attrib.get("pass", 0)) if stat_el is not None else 0
    failed = int(stat_el.attrib.get("fail", 0)) if stat_el is not None else 0

    failures: list[ParsedFailure] = []
    for test in root.findall(".//test"):
        status_el = test.find("status")
        if status_el is None or status_el.attrib.get("status") != "FAIL":
            continue
        msg = status_el.attrib.get("message", "") or status_el.text or ""
        kws = [kw.attrib.get("name", "") for kw in test.findall(".//kw")]
        elap = int(status_el.attrib.get("elapsed", 0))
        failures.append(ParsedFailure(
            test_name=test.attrib.get("name", "Unknown"),
            suite_name=suite_name,
            error_message=msg,
            failure_type=classify_failure(msg),
            keywords=kws[:10],
            duration_ms=elap,
        ))

    return ParsedRun(
        run_id=run_id,
        suite=suite_name,
        status="FAILED" if failed > 0 else "PASSED",
        total=passed + failed,
        passed=passed,
        failed=failed,
        failures=failures,
    )


# ── Raw log text parser ───────────────────────────────────────────────────
def parse_raw_log(log_text: str, run_id: str = "", suite: str = "Unknown") -> ParsedRun:
    """Parse GitHub Actions raw log or plain text CI output."""
    failures: list[ParsedFailure] = []
    lines = log_text.splitlines()

    # Extract FAIL lines
    fail_blocks: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if re.search(r"\bFAIL\b", line):
            fail_blocks.append((i, line))

    for idx, fail_line in fail_blocks:
        # Grab context: next 5 lines as error message
        context = "\n".join(lines[idx: idx + 6])
        test_match = re.search(r"FAIL\s+([\w\s:_\-]+)::\s*([\w\s_\-]+)", fail_line)
        suite_name  = test_match.group(1).strip() if test_match else suite
        test_name   = test_match.group(2).strip() if test_match else fail_line.strip()
        failures.append(ParsedFailure(
            test_name=test_name,
            suite_name=suite_name,
            error_message=context,
            failure_type=classify_failure(context),
        ))

    # Rough pass/fail counts
    passed_count = len(re.findall(r"\bPASS\b", log_text))
    failed_count = len(failures) or len(re.findall(r"\bFAIL\b", log_text))

    return ParsedRun(
        run_id=run_id,
        suite=suite,
        status="FAILED" if failed_count > 0 else "PASSED",
        total=passed_count + failed_count,
        passed=passed_count,
        failed=failed_count,
        failures=failures,
        raw_log=log_text[:5000],
    )


# ── Structured failure summary for LLM ───────────────────────────────────
def failures_to_prompt(run: ParsedRun) -> str:
    if not run.failures:
        return f"Suite {run.suite}: No failures detected."
    lines = [f"Suite: {run.suite} | Run: {run.run_id} | {run.failed}/{run.total} failed\n"]
    for f in run.failures:
        lines.append(
            f"TEST: {f.test_name}\n"
            f"TYPE: {f.failure_type}\n"
            f"ERROR: {f.error_message[:300]}\n"
        )
    return "\n".join(lines)
