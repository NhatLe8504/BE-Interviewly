from __future__ import annotations

import ast
import pathlib

APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"

STDLIB_HINT = {
    "__future__", "abc", "asyncio", "collections", "copy", "dataclasses", "datetime",
    "decimal", "enum", "functools", "inspect", "itertools", "json", "math", "os",
    "pathlib", "re", "sys", "typing", "uuid",
}

THIRD_PARTY = {"fastapi", "pydantic", "starlette"}


def iter_imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                target = path.parent
                for _ in range(node.level - 1):
                    target = target.parent
                try:
                    rel = target.relative_to(APP_ROOT).parts
                except ValueError:
                    found.add("app")
                    continue
                if node.module:
                    found.add(".".join(("app", *rel, node.module.split(".")[0])))
                else:
                    found.add(".".join(("app", *rel)) if rel else "app")
            elif node.module:
                found.add(node.module.split(".")[0])
    return found


def layer_of(path: pathlib.Path) -> str:
    rel = path.relative_to(APP_ROOT).parts
    if rel[0] in ("bootstrap.py", "main.py"):
        return "composition"
    return rel[0]


def check() -> list[str]:
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        layer = layer_of(path)
        for module in iter_imports(path):
            if module in STDLIB_HINT or module in ("app",):
                continue
            if layer == "domain":
                if module != "app.domain" and not module.startswith("app.domain."):
                    violations.append(f"{path.name}: domain must not import {module}")
            elif layer == "application":
                if module.split(".")[0] != "app" or module.split(".")[1:2] not in ([], ["domain"], ["application"]):
                    if module.startswith("app.") and module.split(".")[1] not in ("domain", "application"):
                        violations.append(f"{path.name}: application must not import {module}")
                    elif not module.startswith("app."):
                        violations.append(f"{path.name}: application must not import {module}")
            elif layer == "infrastructure":
                if module in THIRD_PARTY or module.startswith("app.presentation"):
                    violations.append(f"{path.name}: infrastructure must not import {module}")
            elif layer == "presentation":
                if module.startswith("app.infrastructure"):
                    violations.append(f"{path.name}: presentation must not import {module}")
    return violations


def test_dependency_rule_holds() -> None:
    assert check() == []


