"""Deployment Correction Round 1 (MEDIUM-03): `railway.toml` must use only
fields Railway's config-as-code schema actually supports. `numReplicas` is
not one of them and is silently ignored if present -- a static check here
is the only thing that would catch its reintroduction, since Railway
itself gives no build-time error for an unsupported field."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SUPPORTED_BUILD_FIELDS = {"builder", "dockerfilePath"}
_SUPPORTED_DEPLOY_FIELDS = {
    "healthCheckPath",
    "healthCheckTimeout",
    "restartPolicyType",
    "restartPolicyMaxRetries",
}


def _load_config() -> dict:
    with (REPO_ROOT / "railway.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_railway_toml_parses_as_valid_toml():
    config = _load_config()
    assert "build" in config
    assert "deploy" in config


def test_railway_toml_has_no_unsupported_fields():
    config = _load_config()
    unsupported = (set(config.get("build", {})) - _SUPPORTED_BUILD_FIELDS) | (
        set(config.get("deploy", {})) - _SUPPORTED_DEPLOY_FIELDS
    )
    assert unsupported == set()


def test_railway_toml_has_no_num_replicas():
    config = _load_config()
    assert "numReplicas" not in config.get("deploy", {})


def test_railway_toml_dockerfile_path_correct():
    config = _load_config()
    assert config["build"]["dockerfilePath"] == "Dockerfile.backend"
    assert (REPO_ROOT / config["build"]["dockerfilePath"]).exists()


def test_railway_toml_health_check_path_correct():
    config = _load_config()
    assert config["deploy"]["healthCheckPath"] == "/api/health"


def test_railway_toml_has_no_multi_region_config():
    config = _load_config()
    assert "multiRegionConfig" not in config
    assert "multiRegionConfig" not in config.get("deploy", {})
