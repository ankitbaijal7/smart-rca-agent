# ⚡ Smart RCA Agent v2.0
### AI-Powered CI/CD Failure Analysis for Vodafone Ready Networks

Full-stack monorepo — LangChain · RAG · ChromaDB · Ollama (on-prem) · Capgemini LLM (cloud fallback)

---

## 📁 Project Structure

```
smart-rca-agent/
├── backend/                    # FastAPI Python backend
│   ├── agents/                 # LangChain agent implementations
│   │   ├── standup_agent.py    # Pain 1: Morning standup bot
│   │   ├── memory_agent.py     # Pain 2: Recurring failure memory
│   │   ├── reporter_agent.py   # Pain 3: Auto status reporter
│   │   └── knowledge_agent.py  # Pain 4: Team knowledge assistant
│   ├── api/                    # FastAPI routes
│   │   ├── main.py             # App entry point
│   │   └── routes.py           # All API endpoints
│   ├── rag/                    # RAG pipeline
│   │   ├── embeddings.py       # Embedding engine (local + cloud)
│   │   ├── vector_store.py     # ChromaDB manager
│   │   └── retriever.py        # Semantic search + retrieval
│   ├── integrations/           # External service clients
│   │   ├── github_client.py    # GitHub Actions API
│   │   ├── jira_client.py      # Jira REST API
│   │   └── teams_client.py     # MS Teams webhook
│   ├── models/                 # LLM abstraction layer
│   │   └── llm_router.py       # Ollama (local) / Cloud LLM router
│   └── utils/
│       ├── classifier.py       # Failure type classifier
│       └── log_parser.py       # Robot Framework log parser
├── frontend/                   # React dashboard
│   └── src/
│       ├── components/         # Reusable UI components
│       ├── pages/              # Pain 1-4 pages
│       └── hooks/              # API hooks
├── .github/workflows/          # GitHub Actions
│   ├── rca_trigger.yml         # Auto-trigger RCA on failure
│   └── nightly_report.yml      # Nightly standup report
├── docker-compose.yml          # Full stack deployment
├── docker-compose.local.yml    # Local Ollama + ChromaDB
└── .env.example                # Environment variables template
```

---

## 🚀 Quick Start

### Option A — Local (On-Prem Proxmox VM)
```bash
cp .env.example .env
# Edit .env: set LLM_MODE=local, fill Ollama/ChromaDB URLs
docker-compose -f docker-compose.local.yml up -d
```

### Option B — Cloud (Capgemini LLM fallback)
```bash
cp .env.example .env
# Edit .env: set LLM_MODE=cloud, fill cloud LLM credentials
docker-compose up -d
```

### Option C — Hybrid (local primary, cloud fallback)
```bash
cp .env.example .env
# Edit .env: set LLM_MODE=hybrid
docker-compose up -d
```

Access dashboard: http://localhost:3000
API docs: http://localhost:8000/docs

---

## ⚙️ Configuration (.env)

| Variable | Description | Default |
|---|---|---|
| `LLM_MODE` | `local` / `cloud` / `hybrid` | `hybrid` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `deepseek-r1:8b` |
| `CLOUD_LLM_API_KEY` | Cloud LLM API key (fallback) | — |
| `CHROMA_HOST` | ChromaDB host | `localhost` |
| `CHROMA_PORT` | ChromaDB port | `8001` |
| `GITHUB_TOKEN` | GitHub PAT | — |
| `GITHUB_ORG` | GitHub org/owner | — |
| `GITHUB_REPO` | Repository name | — |
| `JIRA_URL` | Jira instance URL | — |
| `JIRA_EMAIL` | Jira user email | — |
| `JIRA_API_TOKEN` | Jira API token | — |
| `JIRA_PROJECT_KEY` | Jira project key | `VRN` |
| `TEAMS_WEBHOOK_URL` | MS Teams incoming webhook URL | — |

---

## 🧩 Architecture

```
GitHub Actions Failure
        ↓
  rca_trigger.yml  ←── post-job step
        ↓
  FastAPI Backend
        ↓
  LLM Router ──→ Ollama (local primary)
        |    └──→ Capgemini LLM (cloud fallback)
        ↓
  LangChain Agent
        ↓
  RAG Pipeline ──→ ChromaDB (semantic search)
                └──→ Embeddings (all-MiniLM-L6-v2)
        ↓
  ┌─────┬──────┬────────┐
Jira  Teams  GitHub   React
               Summary Dashboard
```
