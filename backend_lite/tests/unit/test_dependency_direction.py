from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]
APP_ROOT = ROOT / "app"


def _python_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_new_pure_layers_do_not_import_web_sql_or_concrete_adapters() -> None:
    files = _python_files(APP_ROOT / "application") + _python_files(APP_ROOT / "contracts")
    forbidden = ("fastapi", "sqlite3", "backend_lite.app.adapters", "backend_lite.app.stores")
    violations = {
        f"{path}: {module}"
        for path in files
        for module in _imports(path)
        if module == "fastapi" or module == "sqlite3" or module.startswith(forbidden[2:])
    }
    assert not violations


def test_new_pure_layers_do_not_import_the_primary_backend() -> None:
    files = _python_files(APP_ROOT / "application") + _python_files(APP_ROOT / "contracts")
    violations = {
        f"{path}: {module}"
        for path in files
        for module in _imports(path)
        if module == "backend" or module.startswith("backend.")
    }
    assert not violations


def test_cross_backend_business_imports_are_absent() -> None:
    source_roots = [Path("backend_lite/app"), Path("backend")]
    violations: list[str] = []
    for root in source_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            for module in _imports(path):
                if root.parts[0] == "backend_lite" and (module == "backend" or module.startswith("backend.")):
                    violations.append(f"{path}: {module}")
                if root.parts[0] == "backend" and (
                    module == "backend_lite" or module.startswith("backend_lite.")
                ):
                    violations.append(f"{path}: {module}")
    assert not violations
