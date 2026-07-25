from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).parents[2] / "app" / "application"
_MODULES = ("analysis_state.py", "normalization.py", "context_resolution.py", "domain_policy.py", "safety_registry.py", "safety_grammar.py", "safety_intent.py", "safety_policy.py", "safety_containment.py", "response_decision_policy.py", "evidence_policy.py", "answer_plan.py", "confidence.py", "deterministic_pipeline.py", "social_intent_detector.py", "conversation_router.py", "response_templates.py")
_FORBIDDEN_IMPORTS = ("sqlite3", "fastapi", "sqlalchemy", "requests", "httpx", "openai", "anthropic", "backend_lite.app.adapters", "backend_lite.app.api", "backend_lite.app.runtime")
_FORBIDDEN_CALLS = {"open", "now", "utcnow", "time", "monotonic", "random", "uuid4"}


def test_a3a_kernel_has_no_framework_adapter_database_network_or_model_imports() -> None:
    for name in _MODULES:
        tree = ast.parse((_ROOT / name).read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not [item for item in imports if item.startswith(_FORBIDDEN_IMPORTS)]


def test_a3a_kernel_has_no_direct_filesystem_network_time_or_random_calls() -> None:
    for name in _MODULES:
        tree = ast.parse((_ROOT / name).read_text(encoding="utf-8"))
        calls: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                calls.append(function.id if isinstance(function, ast.Name) else getattr(function, "attr", ""))
        assert not set(calls) & _FORBIDDEN_CALLS


def test_a3a_runtime_has_no_evaluation_fixture_or_reviewer_dependency() -> None:
    forbidden_fragments = (
        "experiments",
        "blind_fixture",
        "evaluation_manifest",
        "held_out",
        "reviewer_file",
        "expected_harmful",
        "benchmark_category",
    )
    for name in _MODULES:
        source = (_ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not [
            item
            for item in imports
            if any(fragment in item.casefold() for fragment in forbidden_fragments)
        ]
        assert not any(
            fragment in source.casefold()
            for fragment in ("expected_harmful", "benchmark_category")
        )
