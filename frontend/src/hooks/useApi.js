// src/hooks/useApi.js
// Centralised API client for all Smart RCA backend endpoints.

const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json();
}

// ── Health ────────────────────────────────────────────────────────────────
export const getHealth = () => request("/health");

// ── Pain 1: Standup ───────────────────────────────────────────────────────
export const runStandup = (post_to_teams = true) =>
  request("/api/standup/run", {
    method: "POST",
    body: JSON.stringify({ post_to_teams }),
  });

export const getRecentRuns = (limit = 10) =>
  request(`/api/standup/runs?limit=${limit}`);

export const getFailedRuns = (limit = 5) =>
  request(`/api/standup/failed-runs?limit=${limit}`);

// ── Pain 2: Memory ────────────────────────────────────────────────────────
export const searchMemory = (query, top_k = 5) =>
  request("/api/memory/search", {
    method: "POST",
    body: JSON.stringify({ query, top_k }),
  });

export const indexDocument = (title, content, doc_type = "runbook") =>
  request("/api/memory/index-doc", {
    method: "POST",
    body: JSON.stringify({ title, content, doc_type }),
  });

export const getMemoryStats = () => request("/api/memory/stats");

// ── Pain 3: Reporter ──────────────────────────────────────────────────────
export const generateReport = (report_type = "weekly", post_to_teams = false) =>
  request("/api/report/generate", {
    method: "POST",
    body: JSON.stringify({ report_type, post_to_teams }),
  });

// ── Pain 4: Knowledge ─────────────────────────────────────────────────────
export const knowledgeChat = (message, history = []) =>
  request("/api/knowledge/chat", {
    method: "POST",
    body: JSON.stringify({ message, history: history.map(h => ({ content: h.content })) }),
  });
