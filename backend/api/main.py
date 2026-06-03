"""
Smart RCA Agent — FastAPI Backend
All routes for Pain 1-4 agents + health + vector store management.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agents.standup_agent import run_standup_analysis
from backend.agents.memory_agent import search_failure_memory, index_document, index_failure
from backend.agents.reporter_knowledge_agents import generate_status_report, knowledge_chat
from backend.models.llm_router import llm_router
from backend.rag.vector_store import vector_store
from backend.integrations.github_client import github_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


# ── Seed vector DB with initial runbooks on startup ───────────────────────
SEED_DOCS = [
    ("VeloCloud SSH Troubleshooting",
     "SSH connection issues on VeloCloud runner VMs (avn-velaut-vm-13 to vm-23) are typically caused by "
     "maxsessions limit (default 10). Fix: increase MaxSessions in /etc/ssh/sshd_config and restart sshd. "
     "For ConnectionResetError errno 104, check for dual-default-gateway conflict on ens160. "
     "Fix: ip route add <subnet> via <gw> dev ens160 metric 100. Persist via systemd oneshot service.",
     "runbook"),
    ("Robot Framework BGP-BFD Keywords",
     "BGP BFD validation uses SSH to Nokia TiMOS. Known issue: 'show router bfd session' hangs if no BFD "
     "sessions are active — no output prompt returned. Fix: use invoke_shell() with timeout=120 and explicit "
     "prompt detection pattern. Partner Gateway traceroute: checks hop sequence from YAML config. "
     "If expected hop missing, check business policy on VeloCloud edge port 80.",
     "runbook"),
    ("CI/CD Pipeline Architecture",
     "GitHub Actions self-hosted runners: avn-velaut-vm-13, -14, -16, -21, -23. VM-16 primary for VeloCloud EFS. "
     "Routing conflict: VeloCloud VLAN subinterfaces at metric 0 override ens160. "
     "Fix with explicit subnet routes via systemd oneshot service at boot. "
     "Workflows: ExecuteTC.py is core driver. output.xml parsed for results. "
     "Retry logic: 2 retries on infra_flake type failures.",
     "architecture"),
    ("VeloCloud UI Locator Patterns",
     "Angular/Clarity components use dynamic IDs. ElementClickInterceptedException typically caused by "
     "ng-loading overlay or clarity-modal. Fix: WebDriverWait(driver,10).until(EC.invisibility_of_element_located"
     "(By.CSS_SELECTOR, '.modal-backdrop')) before click. For buttons: use JS executor as fallback: "
     "driver.execute_script('arguments[0].click()', element).",
     "runbook"),
    ("Meraki KTLO Onboarding Guide",
     "Meraki KTLO: Dashboard API automation for MR/MS/MX devices. Auth: X-Cisco-Meraki-API-Key header. "
     "Key contacts: Sonali (SME). Base URL: https://api.meraki.com/api/v1. "
     "Common tests: network-wide settings, SSID validation, firewall rules, switch port config. "
     "Robot Framework library: requests. Rate limit: 10 req/s per org.",
     "runbook"),
    ("Viptela / Catalyst SD-WAN",
     "Viptela KTLO under VOIS. Key contacts: Jitendra and Ravi (SMEs). "
     "vManage REST API: POST /dataservice/auth/token for session. "
     "Device templates, policy validation, OMP route checks. "
     "Common failure: certificate expiry on vManage causing 401. Fix: renew cert via vManage UI.",
     "runbook"),
]

SEED_FAILURES = [
    ("SSH maxsessions on avn-velaut-vm-16 — ConnectionResetError errno 104",
     "Set MaxSessions 15 in /etc/ssh/sshd_config, systemctl restart sshd. Add MaxStartups 10:30:60.",
     "VeloCloud_EFS", "infra_flake"),
    ("Nokia TiMOS SSH hang on 'show router bfd session'",
     "Use invoke_shell() with 120s timeout. Add explicit prompt detection: wait for '#' char. "
     "If no BFD sessions, command hangs indefinitely — add timeout guard.",
     "CCFW_BGP_BFD", "infra_flake"),
    ("DNS resolution failing from ens160 — socket.gaierror errno -2",
     "Add explicit route: ip route add 10.10.10.0/24 via 192.168.1.1 dev ens160 metric 100. "
     "Persist via /etc/systemd/system/fix-routing.service (oneshot, WantedBy=multi-user.target).",
     "VeloCloud_EFS", "env_issue"),
    ("ElementClickInterceptedException Angular overlay blocking button click",
     "Add: WebDriverWait(driver,10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR,'.modal-backdrop'))). "
     "Fallback: driver.execute_script('arguments[0].click()', element).",
     "VeloCloud_EFS", "ui_locator"),
    ("BGP route 10.45.0.0/16 missing from routing table on vce-uk-lon-01",
     "Re-apply VeloCloud business policy: Profile > Policy > Application > Port 80 rule. "
     "Check segment association on edge. Verify OFC connectivity.",
     "VeloCloud_EFS", "real_bug"),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed vector DB if empty
    stats = vector_store.stats()
    if stats["docs_indexed"] == 0:
        logger.info("Seeding vector DB with initial runbooks...")
        for title, content, dtype in SEED_DOCS:
            vector_store.add_document(title, content, dtype)
    if stats["failures_indexed"] == 0:
        logger.info("Seeding vector DB with initial failure history...")
        for failure, fix, suite, ftype in SEED_FAILURES:
            vector_store.add_failure(failure, fix, suite, ftype)
    yield


app = FastAPI(
    title="Smart RCA Agent API",
    description="AI-powered CI/CD failure analysis — LangChain + RAG + ChromaDB",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ───────────────────────────────────────────────
class StandupRequest(BaseModel):
    post_to_teams: bool = True

class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = 5

class IndexDocRequest(BaseModel):
    title: str
    content: str
    doc_type: str = "runbook"

class IndexFailureRequest(BaseModel):
    failure_text: str
    fix_text: str
    suite: str
    failure_type: str

class ReportRequest(BaseModel):
    report_type: Literal["daily", "weekly", "sprint"] = "weekly"
    post_to_teams: bool = False

class ChatMessage(BaseModel):
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ── Health ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    llm_status = await llm_router.status()
    vs_stats   = vector_store.stats()
    return {
        "status": "ok",
        "llm":    llm_status,
        "vector_store": vs_stats,
        "version": "2.0.0",
    }


# ── Pain 1: Standup ───────────────────────────────────────────────────────
@app.post("/api/standup/run")
async def run_standup(req: StandupRequest, background_tasks: BackgroundTasks):
    """Trigger morning standup analysis. Returns RCA for all failed runs."""
    result = await run_standup_analysis(post_to_teams=req.post_to_teams)
    return result

@app.get("/api/standup/runs")
async def get_recent_runs(limit: int = 10):
    """Fetch recent GitHub Actions runs."""
    try:
        runs = await github_client.get_recent_runs(limit=limit)
        return {"runs": runs}
    except Exception as e:
        raise HTTPException(500, f"GitHub API error: {e}")

@app.get("/api/standup/failed-runs")
async def get_failed_runs(limit: int = 5):
    try:
        runs = await github_client.get_failed_runs(limit=limit)
        return {"runs": runs}
    except Exception as e:
        raise HTTPException(500, f"GitHub API error: {e}")


# ── Pain 2: Memory ────────────────────────────────────────────────────────
@app.post("/api/memory/search")
async def memory_search(req: MemorySearchRequest):
    """Semantic search over failure history + RAG-augmented answer."""
    return await search_failure_memory(req.query, top_k=req.top_k)

@app.post("/api/memory/index-doc")
async def index_doc(req: IndexDocRequest):
    return await index_document(req.title, req.content, req.doc_type)

@app.post("/api/memory/index-failure")
async def index_fail(req: IndexFailureRequest):
    return await index_failure(req.failure_text, req.fix_text, req.suite, req.failure_type)

@app.get("/api/memory/stats")
async def memory_stats():
    return vector_store.stats()


# ── Pain 3: Reporter ──────────────────────────────────────────────────────
@app.post("/api/report/generate")
async def generate_report(req: ReportRequest):
    """Generate daily/weekly/sprint status report."""
    return await generate_status_report(req.report_type, req.post_to_teams)


# ── Pain 4: Knowledge ─────────────────────────────────────────────────────
@app.post("/api/knowledge/chat")
async def knowledge_chat_endpoint(req: ChatRequest):
    """RAG-augmented knowledge assistant chat."""
    history = [{"role": "user", "content": m.content} for m in req.history]
    return await knowledge_chat(req.message, history)
