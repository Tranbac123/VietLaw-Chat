import copy
import json
import shutil
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_TRAFFIC_RULES_PATH = REPO_ROOT / "data" / "traffic_rules.json"


def _isolated_settings_with_mutated_pack(
    settings: Settings, tmp_path: Path, mutate_rules: Callable[[list[dict]], list[dict]]
) -> Settings:
    """Deployment Correction Round 2 (MEDIUM-01): builds an isolated data
    directory containing the real `legal_snippets.json` (so RAG loading is
    unaffected) alongside a MUTATED copy of `traffic_rules.json` -- never
    touches the real curated data files on disk."""

    isolated_dir = tmp_path / "mutated_pack"
    isolated_dir.mkdir()
    shutil.copy(REPO_ROOT / "data" / "legal_snippets.json", isolated_dir / "legal_snippets.json")

    raw = json.loads(REAL_TRAFFIC_RULES_PATH.read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    raw["rules"] = mutate_rules(raw["rules"])
    (isolated_dir / "traffic_rules.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return settings.model_copy(update={"legal_snippets_path": isolated_dir / "legal_snippets.json"})


def test_health_all_ready(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "vietlaw-chat-backend",
        "contract_version": "v1",
        "rag_loaded": True,
        "safety_loaded": True,
        "chat_store_ready": True,
        "traffic_pack_required": True,
        "traffic_pack_loaded": True,
        "traffic_enabled_rule_count": 3,
        "traffic_pack_exact_inventory_valid": True,
    }


def test_health_degraded_when_snippets_missing(settings: Settings, tmp_path: Path):
    degraded = settings.model_copy(update={"legal_snippets_path": tmp_path / "missing.json"})
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    # A Railway (or any orchestrator) health-check target must fail the
    # check via status code, not just a "degraded" string in the body a
    # naive prober might not parse.
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["rag_loaded"] is False
    assert body["safety_loaded"] is True


def test_health_503_when_traffic_pack_required_but_missing(settings: Settings, tmp_path: Path):
    """Deployment Correction Round 1 (MEDIUM-01): the traffic-pack flag is
    enabled (the test suite's ambient default -- see `traffic_pack_enabled`),
    but `traffic_rules.json` is absent next to `legal_snippets.json`, so the
    orchestrator fails to construct. Health must fail closed (503), not
    report healthy just because the unrelated RAG/safety stores loaded."""

    isolated_snippets_dir = tmp_path / "snippets_only"
    isolated_snippets_dir.mkdir()
    shutil.copy(REPO_ROOT / "data" / "legal_snippets.json", isolated_snippets_dir / "legal_snippets.json")
    degraded = settings.model_copy(
        update={"legal_snippets_path": isolated_snippets_dir / "legal_snippets.json"}
    )
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["traffic_pack_required"] is True
    assert body["traffic_pack_loaded"] is False
    assert body["traffic_enabled_rule_count"] is None
    # No internal filesystem path or exception text ever appears in the body.
    assert "traffic_rules.json" not in response.text
    assert str(isolated_snippets_dir) not in response.text


def test_health_ok_when_traffic_pack_disabled_intentionally(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """Deployment Correction Round 1 (MEDIUM-01): when the traffic-pack flag
    is deliberately off, the pack's absence must never fail health -- only a
    flag-on-but-broken pack should."""

    monkeypatch.setenv("VIETLAW_TRAFFIC_PACK_ENABLED", "0")
    with TestClient(create_app(settings)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["traffic_pack_required"] is False
    assert body["traffic_pack_loaded"] is False
    assert body["traffic_enabled_rule_count"] is None


# =============================================================================
# Deployment Correction Round 2 (MEDIUM-01): exact traffic-pack inventory
# gate. `loaded=True` alone is not enough -- the pack must additionally
# match the frozen 15-total/3-enabled/12-disabled inventory with exactly
# the three expected enabled rule IDs. Every mutation below leaves the pack
# structurally VALID (it still loads -- `TrafficSourcePack.from_file`
# accepts it) but wrong in exactly one inventory dimension.
# =============================================================================


def _disable(rule: dict) -> dict:
    rule = dict(rule)
    rule["status"] = "disabled_pending_legal_correction"
    return rule


def test_health_503_when_only_two_rules_enabled(settings: Settings, tmp_path: Path):
    def mutate(rules: list[dict]) -> list[dict]:
        out = []
        disabled_one = False
        for rule in rules:
            if (
                not disabled_one
                and rule["status"] == "enabled"
                and rule["rule_id"] == "traffic_no_helmet__motorcycle__driver_safe_v1"
            ):
                out.append(_disable(rule))
                disabled_one = True
            else:
                out.append(rule)
        return out

    degraded = _isolated_settings_with_mutated_pack(settings, tmp_path, mutate)
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["traffic_pack_loaded"] is True
    assert body["traffic_enabled_rule_count"] == 2
    assert body["traffic_pack_exact_inventory_valid"] is False


def test_health_503_when_four_rules_enabled(settings: Settings, tmp_path: Path):
    def mutate(rules: list[dict]) -> list[dict]:
        template = next(
            r for r in rules if r["rule_id"] == "traffic_no_helmet__motorcycle__driver_safe_v1"
        )
        extra = copy.deepcopy(template)
        extra["rule_id"] = "traffic_no_helmet__car__mutated_test_v1"
        extra["vehicle_type"] = "car"
        return [*rules, extra]

    degraded = _isolated_settings_with_mutated_pack(settings, tmp_path, mutate)
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["traffic_pack_loaded"] is True
    assert body["traffic_enabled_rule_count"] == 4
    assert body["traffic_pack_exact_inventory_valid"] is False


def test_health_503_when_enabled_ids_dont_match_expected_set(settings: Settings, tmp_path: Path):
    def mutate(rules: list[dict]) -> list[dict]:
        out = []
        for rule in rules:
            if rule["rule_id"] == "traffic_no_helmet__motorcycle__driver_safe_v1":
                rule = dict(rule)
                rule["rule_id"] = "traffic_no_helmet__motorcycle__renamed_test_v1"
            out.append(rule)
        return out

    degraded = _isolated_settings_with_mutated_pack(settings, tmp_path, mutate)
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["traffic_pack_loaded"] is True
    assert body["traffic_enabled_rule_count"] == 3
    assert body["traffic_pack_exact_inventory_valid"] is False


def test_health_503_when_total_rows_is_fourteen(settings: Settings, tmp_path: Path):
    def mutate(rules: list[dict]) -> list[dict]:
        disabled_index = next(
            i for i, r in enumerate(rules) if r["status"] != "enabled"
        )
        return [r for i, r in enumerate(rules) if i != disabled_index]

    degraded = _isolated_settings_with_mutated_pack(settings, tmp_path, mutate)
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["traffic_pack_loaded"] is True
    assert body["traffic_pack_exact_inventory_valid"] is False


def test_health_503_when_total_rows_is_sixteen_wrong_disabled_count(
    settings: Settings, tmp_path: Path
):
    def mutate(rules: list[dict]) -> list[dict]:
        template = next(r for r in rules if r["status"] != "enabled")
        extra = copy.deepcopy(template)
        extra["rule_id"] = template["rule_id"] + "__duplicate_test"
        return [*rules, extra]

    degraded = _isolated_settings_with_mutated_pack(settings, tmp_path, mutate)
    with TestClient(create_app(degraded)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["traffic_pack_loaded"] is True
    assert body["traffic_enabled_rule_count"] == 3
    assert body["traffic_pack_exact_inventory_valid"] is False


def test_health_200_with_unmutated_real_pack_via_isolated_copy(settings: Settings, tmp_path: Path):
    """Control case: an untouched copy of the real pack, routed through the
    same isolation helper, must still pass -- proving the mutation helpers
    above are what fail the gate, not the isolation mechanism itself."""

    ok = _isolated_settings_with_mutated_pack(settings, tmp_path, lambda rules: rules)
    with TestClient(create_app(ok)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["traffic_pack_exact_inventory_valid"] is True
    assert body["traffic_enabled_rule_count"] == 3
