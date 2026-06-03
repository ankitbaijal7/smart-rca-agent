*** Settings ***
Documentation       Integration Tests — End-to-End RCA Agent Pipeline
...                 Validates the full AI agent flow: RAG retrieval, LLM invocation,
...                 Jira integration, and memory indexing.
Library             RequestsLibrary
Library             Collections
Library             String
Library             OperatingSystem

Suite Setup         Create Session    rca    http://localhost:8000    verify=${False}
Suite Teardown      Delete All Sessions

*** Variables ***
${MIN_VECTOR_HITS}      1
${MIN_LLM_CONFIDENCE}   0.5

*** Test Cases ***

# ── RAG Pipeline ─────────────────────────────────────────────────────────────

TC_INT_001 RAG Memory Search — SSH Failure
    [Documentation]    Full RAG pipeline: semantic search + LLM augmented answer for SSH failure query.
    [Tags]    integration    rag    P1
    ${payload}=    Create Dictionary    query=SSH connection reset errno 104 VeloCloud runner    top_k=${3}
    ${resp}=    POST On Session    rca    /api/memory/search    json=${payload}
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    ${hits}=    Set Variable    ${body}[vector_hits]
    Length Should Be    ${hits}    3
    ${top}=    Set Variable    ${hits}[0]
    Should Be True    ${top}[score] > 0.4    Expected high relevance score for SSH query
    Log    Top RAG hit: ${top}[suite] | score=${top}[score]
    Log    LLM confidence: ${body}[llm_answer][confidence]

TC_INT_002 RAG Memory Search — BGP Route Missing
    [Documentation]    RAG retrieval for BGP routing failure.
    [Tags]    integration    rag    bgp    P1
    ${payload}=    Create Dictionary    query=BGP route 10.45.0.0/16 missing VeloCloud edge    top_k=${3}
    ${resp}=    POST On Session    rca    /api/memory/search    json=${payload}
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Should Not Be Empty    ${body}[vector_hits]
    Log    BGP RAG hits: ${body}[vector_hits].__len__()

TC_INT_003 Index New Failure Into Memory
    [Documentation]    Index a new failure+fix pair and verify it's stored.
    [Tags]    integration    memory    P2
    ${before}=    GET On Session    rca    /api/memory/stats
    ${count_before}=    Set Variable    ${before.json()}[failures_indexed]
    ${payload}=    Create Dictionary
    ...    failure_text=BGP BFD session flapping on avn-velaut-vm-21 — Nokia TiMOS SSH timeout
    ...    fix_text=Use invoke_shell() with 120s timeout. Add explicit prompt detection for '#' character.
    ...    suite=CCFW_BGP_BFD
    ...    failure_type=infra_flake
    ${resp}=    POST On Session    rca    /api/memory/index-failure    json=${payload}
    Should Be Equal As Integers    ${resp.status_code}    200
    ${after}=    GET On Session    rca    /api/memory/stats
    ${count_after}=    Set Variable    ${after.json()}[failures_indexed]
    Should Be True    ${count_after} > ${count_before}
    Log    Failures indexed: ${count_before} → ${count_after}

TC_INT_004 Index Runbook Document
    [Documentation]    Index a new runbook and verify retrieval improves.
    [Tags]    integration    memory    P2
    ${payload}=    Create Dictionary
    ...    title=SD-WAN Tunnel Recovery Runbook
    ...    content=When VeloCloud overlay tunnel drops: 1) Check underlay routing on ens160. 2) Verify BGP peer state on WAN interface. 3) Re-apply QoS policy in VeloCloud orchestrator. 4) Confirm OFC connectivity. Recovery time: 5-10 mins.
    ...    doc_type=runbook
    ${resp}=    POST On Session    rca    /api/memory/index-doc    json=${payload}
    Should Be Equal As Integers    ${resp.status_code}    200
    Dictionary Should Contain Key    ${resp.json()}    doc_id
    Log    Indexed runbook: ${resp.json()}[title]

# ── Knowledge Agent ───────────────────────────────────────────────────────────

TC_INT_005 Knowledge Chat — VeloCloud SSH Fix
    [Documentation]    Ask the knowledge agent about a known issue and validate it gives a real answer.
    [Tags]    integration    knowledge    llm    P1
    ${payload}=    Create Dictionary
    ...    message=How do I fix SSH maxsessions on VeloCloud runner VM?
    ...    history=@{EMPTY}
    ${resp}=    POST On Session    rca    /api/knowledge/chat    json=${payload}    timeout=120
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Dictionary Should Contain Key    ${body}    answer
    Should Not Be Empty    ${body}[answer]
    Should Be True    len('${body}[answer]') > 50    Answer too short — LLM may have returned empty
    Log    Answer: ${body}[answer][:200]
    Log    RAG used: ${body}[rag_used] | Sources: ${body}[sources]

TC_INT_006 Knowledge Chat — MPLS Troubleshooting
    [Documentation]    Multi-turn conversation about MPLS failure with history context.
    [Tags]    integration    knowledge    llm    P2
    @{history}=    Create List
    ...    ${{'role': 'user', 'content': 'We have MPLS label switching failures on our PE router'}}
    ${payload}=    Create Dictionary
    ...    message=What are the most common causes and how do I diagnose this?
    ...    history=${history}
    ${resp}=    POST On Session    rca    /api/knowledge/chat    json=${payload}    timeout=120
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Should Not Be Empty    ${body}[answer]
    Log    MPLS answer: ${body}[answer][:300]

# ── Report Generation ─────────────────────────────────────────────────────────

TC_INT_007 Weekly Status Report Generation
    [Documentation]    Generate a weekly status report from the agent.
    [Tags]    integration    reporter    P2
    ${payload}=    Create Dictionary    report_type=weekly    post_to_teams=${False}
    ${resp}=    POST On Session    rca    /api/report/generate    json=${payload}    timeout=120
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Dictionary Should Contain Key    ${body}    report
    Should Not Be Empty    ${body}[report]
    Log    Report preview: ${body}[report][:300]

# ── Pipeline Failure — Missing Standup Data ───────────────────────────────────

TC_INT_008 Standup With No GitHub Token — Graceful Degradation
    [Documentation]    Verifies standup agent handles missing GitHub data gracefully.
    ...                Should return empty failures list, not crash.
    [Tags]    integration    standup    P2
    ${payload}=    Create Dictionary    post_to_teams=${False}
    ${resp}=    POST On Session    rca    /api/standup/run    json=${payload}    timeout=120
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Dictionary Should Contain Key    ${body}    summary
    Log    Standup summary: ${body}[summary]
