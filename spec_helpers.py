"""Reusable helpers for PyInstaller spec files.

Usage in *.spec:
    from spec_helpers import apply_localpycs_guard, apply_pyz_bootstrap_guard
    a = Analysis(...)
    a = apply_localpycs_guard(a)
    pyz = PYZ(a.pure)
    pyz = apply_pyz_bootstrap_guard(pyz)
"""

from __future__ import annotations

import importlib.util
import os
import py_compile
from pathlib import Path
import sysconfig
from typing import Any, Iterable, Tuple


def _resolve_module_source(module_name: str) -> str | None:
    """Return source .py path for a module if available."""
    if not module_name:
        return None
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception:
        return None
    origin = getattr(spec, "origin", None) if spec else None
    if isinstance(origin, str) and origin.endswith(".py") and os.path.exists(origin):
        return origin
    return None


def _resolve_stdlib_source(module_name: str) -> str | None:
    """Best-effort resolver from stdlib path."""
    if not module_name:
        return None
    stdlib = sysconfig.get_paths().get("stdlib")
    if not stdlib:
        return None

    base = Path(stdlib)
    module_path = base.joinpath(*module_name.split("."))
    candidates = [
        module_path.with_suffix(".py"),
        module_path / "__init__.py",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return str(c)
    return None


def _resolve_any_source(module_name: str, src_name: str) -> str | None:
    """Resolve source using module name and fallback heuristics."""
    candidates = []
    if module_name:
        candidates.append(module_name)

    # Fallback from pyc basename (e.g. .../localpycs/struct.pyc -> struct)
    stem = Path(src_name).stem
    if stem and stem not in candidates:
        candidates.append(stem)

    for mod in candidates:
        src = _resolve_module_source(mod)
        if src:
            return src
        src = _resolve_stdlib_source(mod)
        if src:
            return src
    return None


def _resolve_pyinstaller_loader_source(module_name: str) -> str | None:
    """Resolve source from PyInstaller.loader for bootstrap modules."""
    if not module_name:
        return None

    qualified = f"PyInstaller.loader.{module_name}"
    src = _resolve_module_source(qualified)
    if src:
        return src

    try:
        import PyInstaller  # type: ignore
    except Exception:
        return None

    candidate = Path(PyInstaller.__file__).resolve().parent / "loader" / f"{module_name}.py"
    if candidate.exists() and candidate.is_file():
        return str(candidate)
    return None


def _resolve_source_for_missing_pyc(module_name: str, src_name: str) -> str | None:
    """Resolve source path for missing .pyc, including PyInstaller bootstrap modules."""
    src = _resolve_any_source(module_name, src_name)
    if src:
        return src
    return _resolve_pyinstaller_loader_source(module_name)


def _repair_missing_pyc_entries(
    entries: Iterable[Tuple[Any, ...]],
    *,
    only_localpycs: bool,
    label: str,
) -> Any:
    """Rebuild missing .pyc entries referenced by a PyInstaller TOC-like iterable."""
    repaired = []
    for entry in entries:
        if not isinstance(entry, tuple) or len(entry) < 2:
            repaired.append(entry)
            continue

        src_raw = entry[1]
        try:
            src_name = os.fspath(src_raw)
        except TypeError:
            repaired.append(entry)
            continue

        normalized_src = src_name.lower().replace("\\", "/")
        if not (
            isinstance(src_name, str)
            and src_name.endswith(".pyc")
            and not os.path.exists(src_name)
        ):
            repaired.append(entry)
            continue

        if only_localpycs and "localpycs" not in normalized_src:
            repaired.append(entry)
            continue

        module_name = entry[0] if len(entry) > 0 and isinstance(entry[0], str) else ""
        src_py = _resolve_source_for_missing_pyc(module_name, src_name)
        if src_py is None:
            print(
                f"[spec_helpers] warn: {label}: no source found for missing pyc: "
                f"{src_name} (module={module_name})"
            )
            repaired.append(entry)
            continue

        try:
            os.makedirs(os.path.dirname(src_name), exist_ok=True)
            py_compile.compile(src_py, cfile=src_name, doraise=True)
            print(f"[spec_helpers] {label}: rebuilt missing pyc: {src_name}")
        except Exception as exc:
            print(f"[spec_helpers] warn: {label}: failed to rebuild {src_name}: {exc}")

        repaired.append(entry)

    try:
        return entries.__class__(repaired)
    except Exception:
        return repaired


def repair_missing_localpycs(pure_toc: Iterable[Tuple[Any, ...]]) -> Any:
    """Rebuild missing localpycs/*.pyc entries referenced by Analysis().pure."""
    return _repair_missing_pyc_entries(
        pure_toc,
        only_localpycs=True,
        label="analysis",
    )


def repair_missing_bootstrap_pycs(dependencies: Iterable[Tuple[Any, ...]]) -> Any:
    """Rebuild missing bootstrap .pyc entries referenced by PYZ().dependencies."""
    return _repair_missing_pyc_entries(
        dependencies,
        only_localpycs=False,
        label="pyz",
    )


def apply_localpycs_guard(analysis: Any) -> Any:
    """Apply missing-localpycs guard to Analysis()."""
    pure = getattr(analysis, "pure", None)
    if pure is None:
        return analysis

    repaired = repair_missing_localpycs(pure)
    if repaired is pure:
        return analysis

    try:
        pure[:] = list(repaired)
        analysis.pure = pure
    except Exception:
        analysis.pure = repaired
    return analysis


def apply_pyz_bootstrap_guard(pyz: Any) -> Any:
    """Apply missing-bootstrap-pyc guard to PYZ()."""
    deps = getattr(pyz, "dependencies", None)
    if deps is None:
        return pyz

    repaired = repair_missing_bootstrap_pycs(deps)
    if repaired is deps:
        return pyz

    try:
        deps[:] = list(repaired)
        pyz.dependencies = deps
    except Exception:
        pyz.dependencies = repaired
    return pyz
