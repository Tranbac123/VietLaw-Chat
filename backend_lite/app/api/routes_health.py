from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..constants import CONTRACT_VERSION, SERVICE_NAME
from ..dependencies import AppContainer, get_container
from ..schemas.api import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(response: Response, container: AppContainer = Depends(get_container)) -> HealthResponse:
    """Readiness check for a Railway health-check target: only local,
    already-loaded-in-process conditions (curated data files parsed, the
    SQLite chat store's schema bootstrapped) -- never a live LLM call, the
    official-search provider, or any other network dependency, so a slow or
    unavailable third party can never fail this check.

    Returns HTTP 503 when degraded, not 200, so Railway (or any
    orchestrator polling this path) can tell a genuinely unready instance
    apart from a healthy one -- the JSON body alone doesn't drive that
    signal, the status code does.

    Deployment Correction Round 1 (MEDIUM-01) also factors in
    `container.traffic_pack_status`: when the traffic-pack feature flag is
    enabled (`required=True`), a load/construction failure (`loaded=False`)
    degrades this endpoint the same way a missing curated data file does.
    When the flag is disabled (`required=False`), the traffic pack's
    absence is an intentional, healthy configuration and never affects this
    check -- only the flag's own on/off state and whether it in fact loaded
    are exposed, never a filesystem path or exception detail.

    Deployment Correction Round 2 (MEDIUM-01): loading successfully is no
    longer sufficient when the flag is on -- the pack must additionally
    match the frozen 15-total/3-enabled/12-disabled inventory with exactly
    the three expected enabled rule IDs
    (`traffic_pack_status.exact_inventory_valid`). A pack that parses but
    has been mutated (wrong count, an unexpected enabled ID, a wrong
    total/disabled row count) now degrades this endpoint exactly like a
    pack that failed to load at all -- neither the mismatch details nor any
    rule ID are exposed in the response body, only the boolean gate.
    """

    rag_loaded = container.snippet_store.loaded
    safety_loaded = container.unsafe_store.loaded
    chat_store_ready = container.chat_store.ready
    traffic_pack_status = container.traffic_pack_status
    traffic_pack_ok = not traffic_pack_status.required or (
        traffic_pack_status.loaded and traffic_pack_status.exact_inventory_valid
    )
    healthy = rag_loaded and safety_loaded and chat_store_ready and traffic_pack_ok
    response.status_code = 200 if healthy else 503
    return HealthResponse(
        status="ok" if healthy else "degraded",
        service=SERVICE_NAME,
        contract_version=CONTRACT_VERSION,
        rag_loaded=rag_loaded,
        safety_loaded=safety_loaded,
        chat_store_ready=chat_store_ready,
        traffic_pack_required=traffic_pack_status.required,
        traffic_pack_loaded=traffic_pack_status.loaded,
        traffic_enabled_rule_count=traffic_pack_status.enabled_rule_count,
        traffic_pack_exact_inventory_valid=traffic_pack_status.exact_inventory_valid,
    )
