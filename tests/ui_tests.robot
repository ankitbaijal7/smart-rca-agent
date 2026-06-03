*** Settings ***
Documentation       UI Validation Tests — Smart RCA Agent Dashboard
...                 Tests the local React dashboard and FastAPI endpoints.
...                 Failures are classified as ui_locator or env_issue.
Library             RequestsLibrary
Library             Collections
Library             String
Library             OperatingSystem

Suite Setup         Create Session    rca_api    http://localhost:8000    verify=${False}
Suite Teardown      Delete All Sessions

*** Variables ***
${BASE_URL}         http://localhost:8000
${FRONTEND_URL}     http://localhost:3000

*** Test Cases ***

# ── Health & Connectivity ─────────────────────────────────────────────────────

TC_UI_001 Dashboard Health Check
    [Documentation]    Verify the API backend is reachable and returns status ok
    [Tags]    ui    smoke    P1
    ${resp}=    GET On Session    rca_api    /health
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Should Be Equal    ${body}[status]    ok
    Log    LLM active: ${body}[llm][active] | Model: ${body}[llm][local_model]

TC_UI_002 Frontend Dashboard Loads
    [Documentation]    Verify React frontend returns HTTP 200
    [Tags]    ui    smoke    P1
    Create Session    frontend    ${FRONTEND_URL}    verify=${False}
    ${resp}=    GET On Session    frontend    /
    Should Be Equal As Integers    ${resp.status_code}    200
    Should Contain    ${resp.text}    Smart RCA Agent
    Delete Session    frontend

TC_UI_003 API Docs Endpoint Reachable
    [Documentation]    Verify Swagger UI is accessible at /docs
    [Tags]    ui    smoke    P1
    ${resp}=    GET On Session    rca_api    /docs
    Should Be Equal As Integers    ${resp.status_code}    200

TC_UI_004 Vector Store Stats Widget
    [Documentation]    Verify memory stats endpoint returns indexed document counts
    [Tags]    ui    data    P2
    ${resp}=    GET On Session    rca_api    /api/memory/stats
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Should Be True    ${body}[failures_indexed] >= 0
    Should Be True    ${body}[docs_indexed] >= 0
    Log    Failures indexed: ${body}[failures_indexed] | Docs: ${body}[docs_indexed]

# ── UI Locator Failures (intentional) ────────────────────────────────────────

TC_UI_005 Nonexistent Dashboard Panel — UI Locator Issue
    [Documentation]    Simulates a missing UI element (Angular overlay / stale locator).
    ...                This is expected to FAIL — classified as ui_locator type.
    [Tags]    ui    ui_locator    intentional_failure    P2
    ${resp}=    GET On Session    rca_api    /api/dashboard/widgets    expected_status=404
    Should Be Equal As Integers    ${resp.status_code}    404
    # This endpoint does not exist — simulates ElementClickInterceptedException
    # where a UI panel fails to render because its backend route is missing.
    Fail    UI locator failure: /api/dashboard/widgets endpoint not found — Angular component may have stale route binding

TC_UI_006 Broken Report Download Link
    [Documentation]    Simulates a broken download button on the Reports page.
    ...                Expected to FAIL — ui_locator type.
    [Tags]    ui    ui_locator    intentional_failure    P2
    ${resp}=    GET On Session    rca_api    /api/report/download/latest    expected_status=404
    Should Be Equal As Integers    ${resp.status_code}    404
    Fail    UI locator failure: report download button points to missing endpoint — CSS selector may have changed after Angular upgrade

# ── API Response Validation ───────────────────────────────────────────────────

TC_UI_007 Knowledge Chat Returns Valid JSON
    [Documentation]    Post a question to the knowledge assistant and validate response structure
    [Tags]    ui    api    P2
    ${payload}=    Create Dictionary    message=What is the fix for SSH maxsessions?    history=@{EMPTY}
    ${resp}=    POST On Session    rca_api    /api/knowledge/chat    json=${payload}
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    Dictionary Should Contain Key    ${body}    answer
    Dictionary Should Contain Key    ${body}    rag_used
    Should Not Be Empty    ${body}[answer]
    Log    RAG used: ${body}[rag_used] | Answer length: ${body}[answer].__len__()

TC_UI_008 Memory Search Returns Ranked Results
    [Documentation]    Verify semantic search returns scored hits in correct order
    [Tags]    ui    api    P2
    ${payload}=    Create Dictionary    query=VeloCloud SSH connection reset    top_k=${3}
    ${resp}=    POST On Session    rca_api    /api/memory/search    json=${payload}
    Should Be Equal As Integers    ${resp.status_code}    200
    ${body}=    Set Variable    ${resp.json()}
    ${hits}=    Set Variable    ${body}[vector_hits]
    Should Not Be Empty    ${hits}
    ${top_score}=    Set Variable    ${hits}[0][score]
    Should Be True    ${top_score} > 0.3    Top hit score too low: ${top_score}
    Log    Top hit: ${hits}[0][suite]} | score=${top_score}
