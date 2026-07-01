# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

APP_EXE_NAME = os.environ.get("APP_EXE_NAME", "AQUA EDGE AI")
APP_RUNTIME_HOOK = os.environ.get("APP_RUNTIME_HOOK", "").strip()
BUNDLE_PLAYWRIGHT_BROWSER = os.environ.get("BUNDLE_PLAYWRIGHT_BROWSER", "0").strip().lower() in {"1", "true", "yes", "on"}
PLAYWRIGHT_BUNDLE_DIR_PREFIXES = (
    "chromium-",
    "chromium_headless_shell-",
    "ffmpeg-",
    "winldd-",
)

_spec_ref = globals().get("__file__", globals().get("SPEC", ""))
if _spec_ref:
    _spec_path = Path(_spec_ref).resolve()
    _spec_dir = _spec_path if _spec_path.is_dir() else _spec_path.parent
else:
    _spec_dir = Path.cwd().resolve()

if str(_spec_dir) not in sys.path:
    sys.path.insert(0, str(_spec_dir))

try:
    from spec_helpers import apply_localpycs_guard, apply_pyz_bootstrap_guard
except ModuleNotFoundError:
    _helper_path = _spec_dir / "spec_helpers.py"
    if not _helper_path.exists():
        raise
    _helper_spec = importlib.util.spec_from_file_location("project_spec_helpers", _helper_path)
    if _helper_spec is None or _helper_spec.loader is None:
        raise
    _helper_mod = importlib.util.module_from_spec(_helper_spec)
    _helper_spec.loader.exec_module(_helper_mod)
    apply_localpycs_guard = _helper_mod.apply_localpycs_guard
    apply_pyz_bootstrap_guard = _helper_mod.apply_pyz_bootstrap_guard

def _default_playwright_cache_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "ms-playwright"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    if xdg:
        return Path(xdg) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _candidate_browser_roots() -> List[Path]:
    roots: List[Path] = []
    try:
        import playwright
    except Exception:
        return roots

    package_root = Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    roots.append(package_root)

    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_root and env_root != "0":
        roots.append(Path(env_root))

    roots.append(_default_playwright_cache_dir())

    out: List[Path] = []
    for p in roots:
        if p not in out:
            out.append(p)
    return out


def _collect_playwright_browser_datas() -> List[Tuple[str, str]]:
    if not BUNDLE_PLAYWRIGHT_BROWSER:
        print("[spec] playwright browser bundling: disabled")
        return []
    roots = _candidate_browser_roots()
    if not roots:
        print("[spec] warn: playwright package not available. skip browser bundling.")
        return []

    datas: List[Tuple[str, str]] = []
    selected_root = None
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        subdirs = [p for p in root.iterdir() if p.is_dir()]
        if not any(p.name.startswith("chromium") for p in subdirs):
            continue
        selected_root = root
        break

    if selected_root is None:
        locations = ", ".join(str(p) for p in roots)
        print(
            "[spec] warn: chromium browser folder not found. "
            "run `python -m playwright install chromium` before build. "
            f"checked: {locations}"
        )
        return []

    for browser_dir in selected_root.iterdir():
        if not browser_dir.is_dir():
            continue
        if not any(browser_dir.name.startswith(prefix) for prefix in PLAYWRIGHT_BUNDLE_DIR_PREFIXES):
            continue
        for src in browser_dir.rglob("*"):
            if not src.is_file():
                continue
            rel_parent = src.relative_to(selected_root).parent
            dst = Path("playwright") / "driver" / "package" / ".local-browsers" / rel_parent
            datas.append((str(src), dst.as_posix()))

    print(f"[spec] playwright browser datas: {len(datas)} files from {selected_root}")
    return datas


_playwright_datas = _collect_playwright_browser_datas()


def _write_runtime_profile_hook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "APP_LINE": os.environ.get("APP_LINE", ""),
        "APP_EDITION": os.environ.get("APP_EDITION", ""),
        "APP_AUTH_MODULE": os.environ.get("APP_AUTH_MODULE", ""),
        "APP_VERSION": os.environ.get("APP_VERSION", ""),
    }
    lines = ["import os"]
    for key, value in profile.items():
        if value:
            lines.append(f"os.environ[{json.dumps(key)}] = {json.dumps(value)}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


_runtime_hooks = []
if APP_RUNTIME_HOOK:
    _runtime_hook_path = Path(APP_RUNTIME_HOOK).resolve()
    if not _runtime_hook_path.exists():
        _write_runtime_profile_hook(_runtime_hook_path)
    _runtime_hooks.append(str(_runtime_hook_path))
    print(f"[spec] runtime hook: {_runtime_hook_path}")


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=_playwright_datas,
    hiddenimports=["auth_clear", "auth_master"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=_runtime_hooks,
    excludes=[],
    noarchive=False,
    optimize=0,
)

a = apply_localpycs_guard(a)
pyz = PYZ(a.pure)
pyz = apply_pyz_bootstrap_guard(pyz)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
