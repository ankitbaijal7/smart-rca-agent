import { useState, useEffect, useRef } from "react";
import {
  getHealth, runStandup, getRecentRuns, searchMemory,
  generateReport, knowledgeChat, getMemoryStats, indexDocument
} from "./hooks/useApi.js";

// ── Design tokens ─────────────────────────────────────────────────────────
const T = {
  bg:      "#080b0f",
  surface: "#0d1117",
  card:    "#161b22",
  border:  "#21262d",
  accent:  "#00d9a3",
  purple:  "#7c6af7",
  amber:   "#f7a23e",
  red:     "#f85149",
  text:    "#e6edf3",
  muted:   "#7d8590",
  green:   "#3fb950",
};

const TABS = [
  { id: "standup",   icon: "🌅", label: "Standup Bot",      color: T.accent,  pain: 1 },
  { id: "memory",    icon: "🧠", label: "Failure Memory",   color: T.purple,  pain: 2 },
  { id: "reporter",  icon: "📊", label: "Status Reporter",  color: T.amber,   pain: 3 },
  { id: "knowledge", icon: "💬", label: "Knowledge Assist", color: T.red,     pain: 4 },
];

// ── Shared components ─────────────────────────────────────────────────────
function Spinner({ color = T.accent }) {
  return <span style={{ display:"inline-block", width:14, height:14, border:`2px solid ${T.border}`, borderTopColor:color, borderRadius:"50%", animation:"spin 0.7s linear infinite" }} />;
}
function Badge({ label, color }) {
  return <span style={{ background:color+"22", color, border:`1px solid ${color}44`, borderRadius:4, padding:"2px 8px", fontSize:11, fontWeight:700, whiteSpace:"nowrap" }}>{label}</span>;
}
function Card({ children, style, accent }) {
  return <div style={{ background:T.card, border:`1px solid ${accent ? accent+"44" : T.border}`, borderRadius:10, padding:20, ...style }}>{children}</div>;
}
function SectionTitle({ icon, title, sub, color = T.accent }) {
  return (
    <div style={{ marginBottom:20 }}>
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:4 }}>
        <span style={{ fontSize:22 }}>{icon}</span>
        <h2 style={{ margin:0, fontSize:17, fontWeight:700, color:T.text }}>{title}</h2>
      </div>
      <p style={{ margin:"0 0 10px 32px", fontSize:12, color:T.muted }}>{sub}</p>
      <div style={{ height:2, background:`linear-gradient(90deg,${color},transparent)`, borderRadius:2 }} />
    </div>
  );
}
function Btn({ children, onClick, disabled, color = T.accent, style }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      background: disabled ? T.surface : color, color: disabled ? T.muted : (color === T.accent ? T.bg : "#fff"),
      border:`1px solid ${disabled ? T.border : color}`, borderRadius:8,
      padding:"9px 22px", fontWeight:700, fontSize:13, cursor:disabled?"not-allowed":"pointer",
      display:"flex", alignItems:"center", gap:8, transition:"filter 0.15s", fontFamily:"inherit", ...style
    }}>{children}</button>
  );
}
function StatusDot({ ok }) {
  return <span style={{ width:8, height:8, borderRadius:"50%", background: ok ? T.green : T.red, display:"inline-block", boxShadow:`0 0 6px ${ok ? T.green : T.red}` }} />;
}

// ── Pain 1: Standup ───────────────────────────────────────────────────────
function StandupTab() {
  const [runs, setRuns]       = useState([]);
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [postTeams, setPost]  = useState(true);
  const [loadingRuns, setLR]  = useState(true);

  useEffect(() => {
    getRecentRuns(8).then(d => { setRuns(d.runs || []); setLR(false); }).catch(() => setLR(false));
  }, []);

  async function analyse() {
    setLoading(true); setResult(null);
    try { setResult(await runStandup(postTeams)); }
    catch(e) { setResult({ error: e.message }); }
    setLoading(false);
  }

  const typeColor = { infra_flake:"#d29922", ui_locator:T.amber, env_issue:T.red, real_bug:T.red, script_error:T.purple, unknown:T.muted };

  return (
    <div>
      <SectionTitle icon="🌅" title="Morning Standup Bot" color={T.accent}
        sub="Fetches overnight CI failures → RAG retrieves past fixes → LLM generates Teams standup + auto-raises Jira bugs" />

      {/* Runs grid */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))", gap:12, marginBottom:20 }}>
        {loadingRuns ? <Card><Spinner /> Loading runs…</Card> : runs.map(r => (
          <Card key={r.id} style={{ borderLeft:`3px solid ${r.conclusion==="success"?T.green:T.red}` }}>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:8 }}>
              <div>
                <div style={{ fontSize:13, fontWeight:700, color:T.text, fontFamily:"monospace" }}>{r.name}</div>
                <div style={{ fontSize:11, color:T.muted }}>#{r.run_number} · {r.branch} · {r.commit}</div>
              </div>
              <Badge label={r.conclusion?.toUpperCase() || r.status} color={r.conclusion==="success"?T.green:T.red} />
            </div>
            <a href={r.html_url} target="_blank" rel="noreferrer" style={{ fontSize:11, color:T.accent }}>View run →</a>
          </Card>
        ))}
        {!loadingRuns && runs.length === 0 && (
          <Card><span style={{ color:T.muted, fontSize:13 }}>No runs found — check GitHub token in .env</span></Card>
        )}
      </div>

      <div style={{ display:"flex", gap:12, alignItems:"center", marginBottom:20, flexWrap:"wrap" }}>
        <Btn onClick={analyse} disabled={loading} color={T.accent}>
          {loading ? <><Spinner />Analysing with RAG + LLM…</> : "▶ Run Morning Analysis"}
        </Btn>
        <label style={{ display:"flex", gap:8, alignItems:"center", cursor:"pointer", fontSize:13, color:T.muted }}>
          <input type="checkbox" checked={postTeams} onChange={e=>setPost(e.target.checked)} />
          Post to Teams
        </label>
      </div>

      {result?.error && <Card accent={T.red}><span style={{ color:T.red, fontSize:13 }}>{result.error}</span></Card>}

      {result && !result.error && (
        <div style={{ display:"grid", gap:14 }}>
          {result.standup && (
            <Card accent={T.accent} style={{ background:"#0a1a12" }}>
              <div style={{ fontSize:11, color:T.accent, fontWeight:700, marginBottom:8, fontFamily:"monospace" }}>📢 TEAMS MESSAGE — READY TO POST</div>
              <div style={{ fontSize:13, color:T.text, lineHeight:1.8, whiteSpace:"pre-wrap" }}>{result.standup}</div>
            </Card>
          )}
          {(result.failures || []).map((f,i) => (
            <Card key={i} style={{ borderLeft:`3px solid ${typeColor[f.type]||T.muted}` }}>
              <div style={{ display:"flex", flexWrap:"wrap", gap:8, justifyContent:"space-between", marginBottom:8 }}>
                <span style={{ fontFamily:"monospace", fontSize:13, color:T.text, fontWeight:600 }}>{f.test}</span>
                <div style={{ display:"flex", gap:6 }}>
                  <Badge label={f.type} color={typeColor[f.type]||T.muted} />
                  <Badge label={`→ ${f.assignee}`} color={T.purple} />
                  {f.jira_key && <Badge label={f.jira_key} color={T.amber} />}
                  {f.confidence && <Badge label={`${Math.round(f.confidence*100)}% conf`} color={T.muted} />}
                </div>
              </div>
              <div style={{ fontSize:12, color:T.muted, marginBottom:6 }}>🔍 {f.root_cause}</div>
              <div style={{ fontSize:12, color:T.accent, background:T.accent+"11", borderRadius:6, padding:"5px 10px" }}>💡 {f.fix}</div>
            </Card>
          ))}
          {result.run_stats && (
            <div style={{ display:"flex", gap:16, fontSize:12, color:T.muted }}>
              {Object.entries(result.run_stats).map(([k,v]) => (
                <span key={k}><span style={{ color:T.text, fontWeight:600 }}>{v}</span> {k.replace("_"," ")}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Pain 2: Memory ────────────────────────────────────────────────────────
function MemoryTab() {
  const [query, setQuery]   = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stats, setStats]   = useState(null);
  const [indexForm, setIF]  = useState({ show:false, title:"", content:"", doc_type:"runbook" });
  const [indexing, setIndexing] = useState(false);

  useEffect(() => { getMemoryStats().then(setStats).catch(() => {}); }, []);

  async function search() {
    if (!query.trim()) return;
    setLoading(true); setResult(null);
    try { setResult(await searchMemory(query)); }
    catch(e) { setResult({ error:e.message }); }
    setLoading(false);
  }

  async function doIndex() {
    setIndexing(true);
    try {
      await indexDocument(indexForm.title, indexForm.content, indexForm.doc_type);
      setIF(f => ({ ...f, show:false, title:"", content:"" }));
      setStats(await getMemoryStats());
    } catch(e) { alert("Index error: "+e.message); }
    setIndexing(false);
  }

  const QUICK = ["SSH maxsessions vm-16","BGP BFD Nokia TiMOS hang","DNS resolution ens160","ElementClickInterceptedException Angular","VeloCloud routing conflict"];

  return (
    <div>
      <SectionTitle icon="🧠" title="Recurring Failure Memory" color={T.purple}
        sub="Vector DB (ChromaDB) + semantic search + RAG-augmented answers. Instant fix retrieval — no more re-investigating." />

      {stats && (
        <div style={{ display:"flex", gap:16, marginBottom:20, flexWrap:"wrap" }}>
          <Card style={{ textAlign:"center", padding:"12px 20px" }}>
            <div style={{ fontSize:24, fontWeight:800, color:T.purple, fontFamily:"monospace" }}>{stats.failures_indexed}</div>
            <div style={{ fontSize:11, color:T.muted }}>Failures Indexed</div>
          </Card>
          <Card style={{ textAlign:"center", padding:"12px 20px" }}>
            <div style={{ fontSize:24, fontWeight:800, color:T.accent, fontFamily:"monospace" }}>{stats.docs_indexed}</div>
            <div style={{ fontSize:11, color:T.muted }}>Runbooks Indexed</div>
          </Card>
          <Btn onClick={() => setIF(f=>({...f,show:!f.show}))} color={T.purple} style={{ alignSelf:"center" }}>
            + Index Document
          </Btn>
        </div>
      )}

      {indexForm.show && (
        <Card accent={T.purple} style={{ marginBottom:20 }}>
          <div style={{ fontSize:12, color:T.purple, fontWeight:700, marginBottom:10 }}>ADD TO VECTOR DB</div>
          <input value={indexForm.title} onChange={e=>setIF(f=>({...f,title:e.target.value}))} placeholder="Document title" style={inputStyle} />
          <textarea value={indexForm.content} onChange={e=>setIF(f=>({...f,content:e.target.value}))} placeholder="Document content / runbook text..." rows={4} style={{ ...inputStyle, marginTop:8, resize:"vertical" }} />
          <div style={{ display:"flex", gap:8, marginTop:8 }}>
            {["runbook","architecture","guide","known-fix"].map(t => (
              <button key={t} onClick={()=>setIF(f=>({...f,doc_type:t}))} style={{ background:indexForm.doc_type===t?T.purple:T.surface, color:indexForm.doc_type===t?"#fff":T.muted, border:`1px solid ${T.border}`, borderRadius:6, padding:"4px 10px", fontSize:11, cursor:"pointer" }}>{t}</button>
            ))}
            <Btn onClick={doIndex} disabled={indexing} color={T.purple} style={{ marginLeft:"auto" }}>
              {indexing ? <Spinner color={T.purple}/> : "Index"}
            </Btn>
          </div>
        </Card>
      )}

      <div style={{ display:"flex", gap:8, marginBottom:12, flexWrap:"wrap" }}>
        {QUICK.map(q => (
          <button key={q} onClick={() => setQuery(q)} style={{ background:T.surface, border:`1px solid ${T.border}`, color:T.muted, borderRadius:20, padding:"4px 12px", fontSize:11, cursor:"pointer" }}>{q}</button>
        ))}
      </div>

      <div style={{ display:"flex", gap:10, marginBottom:20 }}>
        <input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==="Enter"&&search()}
          placeholder="Describe a failure or ask a question…" style={{ ...inputStyle, flex:1 }} />
        <Btn onClick={search} disabled={loading} color={T.purple}>
          {loading ? <Spinner color={T.purple}/> : "🔍"} Search
        </Btn>
      </div>

      {result?.error && <Card accent={T.red}><span style={{ color:T.red }}>{result.error}</span></Card>}

      {result && !result.error && (
        <div style={{ display:"grid", gap:12 }}>
          {/* LLM Answer */}
          {result.llm_answer?.answer && (
            <Card accent={T.purple} style={{ background:"#0f0f1a" }}>
              <div style={{ fontSize:11, color:T.purple, fontWeight:700, marginBottom:8, fontFamily:"monospace" }}>🤖 RAG-AUGMENTED ANSWER</div>
              {result.llm_answer.fix_command && (
                <div style={{ background:"#000", borderRadius:6, padding:"8px 12px", fontFamily:"monospace", fontSize:12, color:T.green, marginBottom:10 }}>
                  $ {result.llm_answer.fix_command}
                </div>
              )}
              <div style={{ fontSize:13, color:T.text, lineHeight:1.8, whiteSpace:"pre-wrap" }}>{result.llm_answer.answer}</div>
              {result.llm_answer.seen_before && (
                <div style={{ marginTop:10, fontSize:12, color:T.amber }}>⚠️ Seen {result.llm_answer.occurrence_count || "multiple"} times before. Recurring issue.</div>
              )}
            </Card>
          )}
          {/* Vector hits */}
          {(result.vector_hits || []).map((h,i) => (
            <Card key={i} style={{ borderLeft:`3px solid ${T.purple}` }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6, flexWrap:"wrap", gap:6 }}>
                <span style={{ fontSize:12, color:T.text, fontWeight:600 }}>{h.suite} — {h.failure_type}</span>
                <Badge label={`${Math.round(h.score*100)}% match`} color={T.purple} />
              </div>
              <div style={{ fontSize:12, color:T.muted, marginBottom:6 }}>{h.date?.slice(0,10)}</div>
              <div style={{ fontSize:12, color:T.green, background:T.green+"11", borderRadius:4, padding:"4px 8px" }}>✓ {h.fix}</div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Pain 3: Reporter ──────────────────────────────────────────────────────
function ReporterTab() {
  const [type, setType]   = useState("weekly");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [postTeams, setPost] = useState(false);

  async function generate() {
    setLoading(true); setResult(null);
    try { setResult(await generateReport(type, postTeams)); }
    catch(e) { setResult({ error:e.message }); }
    setLoading(false);
  }

  return (
    <div>
      <SectionTitle icon="📊" title="Auto Status Reporter" color={T.amber}
        sub="Reads GitHub CI history + RAG recurring issues → generates Capgemini-style status report for Srinath & Nihit. 1-click." />

      <div style={{ display:"flex", gap:10, marginBottom:20, flexWrap:"wrap", alignItems:"center" }}>
        {["daily","weekly","sprint"].map(t => (
          <button key={t} onClick={()=>setType(t)} style={{
            background: type===t?T.amber:T.surface, color:type===t?T.bg:T.muted,
            border:`1px solid ${type===t?T.amber:T.border}`, borderRadius:6,
            padding:"7px 18px", fontSize:12, fontWeight:600, cursor:"pointer", textTransform:"capitalize"
          }}>{t}</button>
        ))}
        <label style={{ display:"flex", gap:8, alignItems:"center", fontSize:13, color:T.muted, cursor:"pointer", marginLeft:8 }}>
          <input type="checkbox" checked={postTeams} onChange={e=>setPost(e.target.checked)} />
          Post to Teams
        </label>
        <Btn onClick={generate} disabled={loading} color={T.amber} style={{ marginLeft:"auto" }}>
          {loading ? <><Spinner color={T.amber}/>Generating…</> : "📝 Generate Report"}
        </Btn>
      </div>

      {result?.error && <Card accent={T.red}><span style={{ color:T.red }}>{result.error}</span></Card>}

      {result && !result.error && (
        <Card accent={T.amber} style={{ background:"#14100a" }}>
          <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12, flexWrap:"wrap", gap:8 }}>
            <div style={{ fontSize:11, color:T.amber, fontWeight:700, fontFamily:"monospace" }}>
              📄 {type.toUpperCase()} STATUS REPORT — READY TO SEND
            </div>
            <button onClick={() => navigator.clipboard?.writeText(result.report_markdown||"")}
              style={{ background:"transparent", border:`1px solid ${T.border}`, color:T.muted, borderRadius:4, padding:"3px 10px", fontSize:11, cursor:"pointer" }}>
              Copy
            </button>
          </div>
          {result.summary_one_liner && (
            <div style={{ background:T.amber+"15", borderRadius:6, padding:"6px 12px", fontSize:12, color:T.amber, marginBottom:12 }}>
              📌 Subject: {result.summary_one_liner}
            </div>
          )}
          <div style={{ fontSize:13, color:T.text, lineHeight:1.9, whiteSpace:"pre-wrap" }}>{result.report_markdown}</div>
        </Card>
      )}
    </div>
  );
}

// ── Pain 4: Knowledge ─────────────────────────────────────────────────────
function KnowledgeTab() {
  const [messages, setMessages] = useState([{
    role:"assistant",
    content:"Hi! I'm the Smart RCA Knowledge Assistant — I have access to all runbooks, past RCAs, keyword guides, and architecture docs via RAG. Ask me anything about VeloCloud, Viptela, Meraki, Robot Framework, or the CI/CD pipeline.",
    sources:[]
  }]);
  const [input, setInput]   = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef();

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [messages]);

  async function send() {
    if (!input.trim() || loading) return;
    const msg = input.trim(); setInput("");
    setMessages(m => [...m, { role:"user", content:msg }]);
    setLoading(true);
    const history = messages.slice(-6).map(m => ({ content:m.content }));
    try {
      const r = await knowledgeChat(msg, history);
      setMessages(m => [...m, { role:"assistant", content:r.answer, sources:r.sources||[], rag:r.rag_used }]);
    } catch(e) {
      setMessages(m => [...m, { role:"assistant", content:`Error: ${e.message}`, sources:[] }]);
    }
    setLoading(false);
  }

  const SUGGESTED = ["How do I fix SSH maxsessions on vm-16?","Nokia TiMOS BFD session hang fix","Onboard to Meraki KTLO from scratch","Fix ElementClickInterceptedException Angular","CI/CD pipeline routing conflict explanation","Viptela vManage certificate expiry fix"];

  return (
    <div style={{ display:"flex", flexDirection:"column", height:580 }}>
      <SectionTitle icon="💬" title="Team Knowledge Assistant" color={T.red}
        sub="RAG chatbot over all runbooks + past RCAs. Junior engineers self-serve — cuts interruptions to senior team." />

      <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:12 }}>
        {SUGGESTED.map(q => (
          <button key={q} onClick={()=>setInput(q)} style={{ background:T.surface, border:`1px solid ${T.border}`, color:T.muted, borderRadius:20, padding:"3px 12px", fontSize:11, cursor:"pointer" }}>{q}</button>
        ))}
      </div>

      <div style={{ flex:1, overflowY:"auto", background:T.surface, borderRadius:10, border:`1px solid ${T.border}`, padding:16, display:"flex", flexDirection:"column", gap:12, marginBottom:12 }}>
        {messages.map((m,i) => (
          <div key={i} style={{ display:"flex", justifyContent:m.role==="user"?"flex-end":"flex-start" }}>
            <div style={{ maxWidth:"82%", background:m.role==="user"?T.red+"22":T.card, border:`1px solid ${m.role==="user"?T.red+"44":T.border}`, borderRadius:10, padding:"10px 14px" }}>
              {m.role==="assistant" && (
                <div style={{ fontSize:10, color:T.red, fontWeight:700, marginBottom:4, fontFamily:"monospace", display:"flex", gap:8, alignItems:"center" }}>
                  🤖 SMART RCA {m.rag && <Badge label="RAG" color={T.accent}/>}
                </div>
              )}
              <div style={{ fontSize:13, color:T.text, lineHeight:1.8, whiteSpace:"pre-wrap" }}>{m.content}</div>
              {m.sources?.length > 0 && (
                <div style={{ marginTop:8, display:"flex", gap:6, flexWrap:"wrap" }}>
                  {m.sources.map((s,si) => <Badge key={si} label={`📄 ${s.title}`} color={T.muted}/>)}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display:"flex", gap:8, alignItems:"center" }}>
            <Spinner color={T.red}/> <span style={{ fontSize:12, color:T.muted }}>Searching vector DB + generating answer…</span>
          </div>
        )}
        <div ref={bottomRef}/>
      </div>

      <div style={{ display:"flex", gap:10 }}>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()}
          placeholder="Ask about CI failures, Robot Framework, VeloCloud, Meraki…"
          style={{ ...inputStyle, flex:1 }} />
        <Btn onClick={send} disabled={loading} color={T.red} style={{ padding:"9px 18px", fontSize:18 }}>↑</Btn>
      </div>
    </div>
  );
}

const inputStyle = {
  background:T.card, border:`1px solid ${T.border}`, borderRadius:8,
  padding:"10px 14px", color:T.text, fontSize:13, fontFamily:"monospace",
  outline:"none", width:"100%"
};

// ═══════════════════════════════════════════════════════════════════════════
// ROOT APP
// ═══════════════════════════════════════════════════════════════════════════
export default function App() {
  const [tab, setTab]         = useState("standup");
  const [health, setHealth]   = useState(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth({ status:"offline" }));
  }, []);

  const activeTab = TABS.find(t => t.id === tab);

  return (
    <div style={{ minHeight:"100vh", background:T.bg, color:T.text, fontFamily:"'IBM Plex Mono','Courier New',monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');
        *{box-sizing:border-box;} ::-webkit-scrollbar{width:5px;} ::-webkit-scrollbar-thumb{background:${T.border};border-radius:3px;}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes fadein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        input,textarea{color:${T.text}!important;} input::placeholder,textarea::placeholder{color:${T.muted}!important;}
        input:focus,textarea:focus{border-color:${T.accent}!important;}
        button:hover:not(:disabled){filter:brightness(1.12);}
      `}</style>

      {/* Header */}
      <div style={{ background:T.surface, borderBottom:`1px solid ${T.border}`, padding:"14px 28px", display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
        <div style={{ width:38, height:38, borderRadius:8, background:`linear-gradient(135deg,${T.accent},${T.purple})`, display:"flex", alignItems:"center", justifyContent:"center", fontSize:20, flexShrink:0 }}>⚡</div>
        <div>
          <div style={{ fontSize:15, fontWeight:700, color:T.text }}>Smart RCA Agent <span style={{ color:T.accent, fontSize:11, fontWeight:400 }}>v2.0</span></div>
          <div style={{ fontSize:11, color:T.muted }}>LangChain · RAG · ChromaDB · Ollama — Vodafone Ready Networks</div>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:10, alignItems:"center", flexWrap:"wrap" }}>
          {health && (
            <div style={{ display:"flex", gap:8, alignItems:"center", fontSize:11, color:T.muted }}>
              <StatusDot ok={health.status==="ok"} />
              <span>API {health.status}</span>
              {health.llm && <><span>·</span><span style={{ color:T.accent }}>{health.llm.active} LLM</span></>}
              {health.vector_store && <><span>·</span><span style={{ color:T.purple }}>{health.vector_store.failures_indexed} failures</span></>}
            </div>
          )}
          {["LangChain","RAG","ChromaDB","Ollama","all-MiniLM-L6-v2"].map(l => (
            <span key={l} style={{ background:T.accent+"15", border:`1px solid ${T.accent}30`, color:T.accent, borderRadius:4, padding:"2px 7px", fontSize:10, fontWeight:600 }}>{l}</span>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display:"flex", background:T.surface, borderBottom:`1px solid ${T.border}`, padding:"0 28px", overflowX:"auto" }}>
        {TABS.map(t => (
          <button key={t.id} onClick={()=>setTab(t.id)} style={{
            background:"none", border:"none",
            borderBottom: tab===t.id?`2px solid ${t.color}`:"2px solid transparent",
            color: tab===t.id?t.color:T.muted,
            padding:"13px 20px", cursor:"pointer", fontSize:13,
            fontWeight: tab===t.id?700:400, fontFamily:"inherit",
            display:"flex", alignItems:"center", gap:8, whiteSpace:"nowrap", transition:"all 0.2s"
          }}>
            {t.icon} Pain {t.pain}: {t.label}
          </button>
        ))}
      </div>

      {/* Page */}
      <div style={{ padding:"28px 32px", maxWidth:1120, margin:"0 auto", animation:"fadein 0.3s ease" }}>
        {tab==="standup"   && <StandupTab />}
        {tab==="memory"    && <MemoryTab />}
        {tab==="reporter"  && <ReporterTab />}
        {tab==="knowledge" && <KnowledgeTab />}
      </div>

      {/* Footer */}
      <div style={{ borderTop:`1px solid ${T.border}`, padding:"10px 28px", background:T.surface, display:"flex", gap:20, flexWrap:"wrap" }}>
        {[
          ["Vector Store","ChromaDB (on-prem)",T.accent],
          ["Primary LLM","Ollama deepseek-r1:8b",T.purple],
          ["Fallback LLM","Capgemini Cloud LLM",T.amber],
          ["Embeddings","all-MiniLM-L6-v2",T.red],
          ["Orchestration","LangChain + LangGraph",T.green],
          ["Integrations","GitHub · Jira · Teams",T.muted],
        ].map(([k,v,c]) => (
          <div key={k} style={{ fontSize:11 }}>
            <span style={{ color:T.muted }}>{k}: </span><span style={{ color:c, fontWeight:600 }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
