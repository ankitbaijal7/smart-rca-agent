*** Settings ***
Documentation       Network Validation Tests — BGP, MPLS, SD-WAN, Routing
...                 Simulates network health checks on the CI runner VM.
...                 Failures map to: infra_flake, env_issue, real_bug.
Library             OperatingSystem
Library             Process
Library             String
Library             Collections
Library             RequestsLibrary

*** Variables ***
${LOCAL_GW}             192.168.1.1
${DNS_SERVER}           8.8.8.8
${OLLAMA_HOST}          localhost
${OLLAMA_PORT}          11434
${BACKEND_HOST}         localhost
${BACKEND_PORT}         8000
${CHROMA_HOST}          localhost
${CHROMA_PORT}          8001
# Simulated SD-WAN / VeloCloud endpoints (not real — triggers env_issue failure)
${VELOCLOUD_MGMT}       10.100.0.1
${BGP_PEER_1}           10.45.0.1
${BGP_PEER_2}           172.16.0.254
${MPLS_PE_ROUTER}       10.200.1.1

*** Test Cases ***

# ── Infrastructure Connectivity ───────────────────────────────────────────────

TC_NET_001 DNS Resolution Check
    [Documentation]    Verify DNS is resolving correctly from runner host.
    ...                Failure = env_issue (DNS misconfiguration)
    [Tags]    network    infra    dns    P1
    ${result}=    Run Process    nslookup    github.com    ${DNS_SERVER}    timeout=10s
    Should Be Equal As Integers    ${result.rc}    0
    Should Contain    ${result.stdout}    Address
    Log    DNS OK: ${result.stdout}

TC_NET_002 Internet Connectivity — GitHub Reachable
    [Documentation]    Verify outbound HTTPS to GitHub is not blocked.
    [Tags]    network    infra    P1
    ${result}=    Run Process    curl    -s    -o    /dev/null    -w    %{http_code}
    ...    --max-time    10    https://github.com    timeout=15s
    Should Be Equal    ${result.stdout}    200
    Log    GitHub reachable: HTTP ${result.stdout}

TC_NET_003 Ollama LLM Service Port Check
    [Documentation]    Verify Ollama inference server is listening on port 11434.
    ...                Failure = infra_flake (local LLM service down)
    [Tags]    network    infra    llm    P1
    ${result}=    Run Process    nc    -z    -w3    ${OLLAMA_HOST}    ${OLLAMA_PORT}    timeout=10s
    Should Be Equal As Integers    ${result.rc}    0
    Log    Ollama port ${OLLAMA_PORT} is open

TC_NET_004 ChromaDB Vector Store Port Check
    [Documentation]    Verify ChromaDB is listening on port 8001 (Docker container).
    ...                Failure = infra_flake (vector store down — all RAG queries will fail)
    [Tags]    network    infra    chromadb    P1
    ${result}=    Run Process    nc    -z    -w3    ${CHROMA_HOST}    ${CHROMA_PORT}    timeout=10s
    Should Be Equal As Integers    ${result.rc}    0
    Log    ChromaDB port ${CHROMA_PORT} is open

TC_NET_005 Backend API Port Check
    [Documentation]    Verify FastAPI backend is listening on port 8000.
    [Tags]    network    infra    backend    P1
    ${result}=    Run Process    nc    -z    -w3    ${BACKEND_HOST}    ${BACKEND_PORT}    timeout=10s
    Should Be Equal As Integers    ${result.rc}    0
    Log    Backend port ${BACKEND_PORT} is open

# ── BGP Validation (Simulated) ────────────────────────────────────────────────

TC_NET_006 BGP Peer Reachability — Peer 1
    [Documentation]    Validates reachability to BGP peer 10.45.0.1 (VeloCloud edge).
    ...                EXPECTED TO FAIL — real_bug: BGP route missing from routing table.
    ...                In production: checks 'show bgp summary' on Nokia TiMOS via SSH.
    [Tags]    network    bgp    intentional_failure    P1
    ${result}=    Run Process    ping    -c    3    -W    2    ${BGP_PEER_1}    timeout=15s
    ${rc}=    Set Variable    ${result.rc}
    Run Keyword If    ${rc} != 0    Fail
    ...    BGP peer ${BGP_PEER_1} unreachable — route 10.45.0.0/16 missing from VeloCloud edge routing table. Check business policy on port 80. Real bug: OMP route not redistributed.

TC_NET_007 BGP Peer Reachability — Peer 2 (MPLS PE)
    [Documentation]    Validates reachability to MPLS PE router 172.16.0.254.
    ...                EXPECTED TO FAIL — infra_flake: MPLS label stack misconfigured.
    [Tags]    network    bgp    mpls    intentional_failure    P1
    ${result}=    Run Process    ping    -c    3    -W    2    ${BGP_PEER_2}    timeout=15s
    ${rc}=    Set Variable    ${result.rc}
    Run Keyword If    ${rc} != 0    Fail
    ...    MPLS PE router ${BGP_PEER_2} unreachable — label switching failure on ens160. Check VRF binding and MPLS label stack. Possible dual-default-gateway conflict causing route lookup failure.

TC_NET_008 SD-WAN VeloCloud Management Plane
    [Documentation]    Checks reachability to VeloCloud orchestrator management IP.
    ...                EXPECTED TO FAIL — env_issue: SD-WAN overlay tunnel down.
    [Tags]    network    sdwan    velocloud    intentional_failure    P1
    ${result}=    Run Process    ping    -c    3    -W    2    ${VELOCLOUD_MGMT}    timeout=15s
    ${rc}=    Set Variable    ${result.rc}
    Run Keyword If    ${rc} != 0    Fail
    ...    VeloCloud management plane ${VELOCLOUD_MGMT} unreachable — SD-WAN overlay tunnel down. Check VeloCloud Edge status in orchestrator. Possible: underlay routing issue or certificate expiry.

TC_NET_009 MPLS PE Router SSH Connectivity
    [Documentation]    Tests SSH reachability to MPLS PE router (Nokia TiMOS).
    ...                EXPECTED TO FAIL — infra_flake: MaxSessions limit hit.
    [Tags]    network    mpls    ssh    intentional_failure    P1
    ${result}=    Run Process    nc    -z    -w3    ${MPLS_PE_ROUTER}    22    timeout=10s
    ${rc}=    Set Variable    ${result.rc}
    Run Keyword If    ${rc} != 0    Fail
    ...    SSH to MPLS PE ${MPLS_PE_ROUTER}:22 failed — ConnectionResetError errno 104. MaxSessions limit reached on Nokia TiMOS. Fix: increase MaxSessions in /etc/ssh/sshd_config to 15. infra_flake type.

# ── Routing Table Validation ──────────────────────────────────────────────────

TC_NET_010 Default Route Present
    [Documentation]    Verify a default route exists on the runner host.
    [Tags]    network    routing    P1
    ${result}=    Run Process    netstat    -rn    timeout=10s
    Should Contain    ${result.stdout}    default
    Log    Routing table OK — default route present

TC_NET_011 Loopback Interface Up
    [Documentation]    Verify loopback interface is up (basic sanity check).
    [Tags]    network    infra    P1
    ${result}=    Run Process    ping    -c    1    -W    2    127.0.0.1    timeout=5s
    Should Be Equal As Integers    ${result.rc}    0
    Log    Loopback OK

TC_NET_012 SD-WAN API Endpoint Validation
    [Documentation]    Tests SD-WAN REST API reachability (Viptela vManage).
    ...                EXPECTED TO FAIL — env_issue: vManage certificate expired.
    [Tags]    network    sdwan    viptela    intentional_failure    P2
    ${result}=    Run Process    curl    -s    -o    /dev/null    -w    %{http_code}
    ...    --max-time    5    --insecure
    ...    https://10.200.200.1/dataservice/auth/token    timeout=10s
    ${code}=    Set Variable    ${result.stdout}
    Run Keyword If    '${code}' != '200'    Fail
    ...    vManage API at 10.200.200.1 returned HTTP ${code} — certificate may be expired or management VPN unreachable. env_issue: check vManage TLS cert validity.
