#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from product_profile import EDITIONS, PRODUCT_EXE_BASENAME, PRODUCT_LINES


EXE_NAME_ENV = "APP_EXE_NAME"
RUNTIME_HOOK_ENV = "APP_RUNTIME_HOOK"
PROJECT_DIR = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_DIR / "VERSION.txt"
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
RUNTIME_HOOK_DIR = BUILD_DIR / "runtime_hooks"
CHANGELOG_FILE = PROJECT_DIR / "docs" / "CHANGELOG_CUSTOMER.md"
PLAYWRIGHT_BUNDLE_DIR_PREFIXES = (
    "chromium-",
    "chromium_headless_shell-",
    "ffmpeg-",
    "winldd-",
)


def read_version(version_file: Path) -> str:
    if not version_file.exists():
        raise FileNotFoundError(f"VERSION.txt が見つかりません: {version_file}")
    ver = version_file.read_text(encoding="utf-8").strip()
    if not ver:
        raise ValueError(f"{version_file.name} が空です")
    return ver


def sanitize_version(ver: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", ver)
    return safe.strip("._-") or "0"


def find_spec_file(spec_arg: str) -> Path:
    if spec_arg:
        p = Path(spec_arg)
        if not p.is_absolute():
            p = PROJECT_DIR / p
        p = p.resolve()
        if not p.exists():
            raise FileNotFoundError(f"spec が見つかりません: {p}")
        return p

    specs = sorted(PROJECT_DIR.glob("*.spec"))
    if not specs:
        raise FileNotFoundError(f"spec が見つかりません: {PROJECT_DIR}")
    if len(specs) == 1:
        return specs[0]

    preferred = PROJECT_DIR / f"{PROJECT_DIR.name}.spec"
    if preferred in specs:
        return preferred

    names = ", ".join([p.name for p in specs])
    raise ValueError(
        "spec が複数あります。--spec <file> で指定してください: "
        f"{names}"
    )


def _default_playwright_cache_dir() -> Path:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / "ms-playwright"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg:
        return Path(xdg) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _candidate_playwright_browser_roots(playwright_module) -> list[Path]:
    roots = [Path(playwright_module.__file__).resolve().parent / "driver" / "package" / ".local-browsers"]
    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_root and env_root != "0":
        roots.append(Path(env_root))
    roots.append(_default_playwright_cache_dir())
    uniq: list[Path] = []
    for p in roots:
        if p not in uniq:
            uniq.append(p)
    return uniq


def should_bundle_playwright_browser_dir_name(name: str) -> bool:
    text = str(name or "").strip()
    return any(text.startswith(prefix) for prefix in PLAYWRIGHT_BUNDLE_DIR_PREFIXES)


def ensure_playwright_chromium_ready() -> None:
    try:
        import playwright
    except Exception:
        raise RuntimeError(
            "playwright が見つかりません。pip install playwright を実行してください。"
        )

    roots = _candidate_playwright_browser_roots(playwright)
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            has_chromium = any(p.is_dir() and p.name.startswith("chromium") for p in root.iterdir())
        except Exception:
            has_chromium = False
        if has_chromium:
            return

    checked = ", ".join(str(p) for p in roots)
    raise RuntimeError(
        "Playwright Chromium が見つかりません。"
        "python -m playwright install chromium を実行してからビルドしてください。"
        " うまくいかない場合は PLAYWRIGHT_BROWSERS_PATH=0 を設定して再インストールしてください。"
        f" (checked: {checked})"
    )


def infer_app_basename(spec_file: Path, app_name_arg: str) -> str:
    if app_name_arg and app_name_arg.strip():
        name = app_name_arg.strip()
        if name.lower().endswith(".exe"):
            name = name[:-4]
        return name
    return PRODUCT_EXE_BASENAME or spec_file.stem


def build_exe_name(app_basename: str, version: str, *, include_version: bool = True) -> str:
    if not include_version:
        return app_basename
    return f"{app_basename}_v{sanitize_version(version)}"


def normalize_line_arg(line_arg: str) -> str:
    line = str(line_arg or "").strip().lower()
    if not line:
        return ""
    if line not in PRODUCT_LINES:
        names = ", ".join(sorted(PRODUCT_LINES.keys()))
        raise ValueError(f"--line は次のいずれかで指定してください: {names}")
    return line


def normalize_edition_arg(edition_arg: str) -> str:
    edition = str(edition_arg or "").strip().upper()
    if not edition:
        return ""
    if edition not in EDITIONS:
        names = ", ".join(sorted(EDITIONS.keys()))
        raise ValueError(f"--edition は次のいずれかで指定してください: {names}")
    return edition


def infer_line_from_app_basename(app_basename: str) -> str:
    text = str(app_basename or "").upper()
    if "CLEARISM" in text:
        return "clearism"
    return "aqua"


def infer_edition_from_app_basename(app_basename: str) -> str:
    text = str(app_basename or "").upper()
    if "KYOUTEI" in text:
        return "DEMO"
    for edition in ("GOLD", "SILVER", "BRONZE"):
        if edition in text:
            return edition
    return "GOLD"


def select_auth_module(line: str, edition: str, auth_module_arg: str) -> str:
    auth_module = str(auth_module_arg or "").strip()
    if auth_module:
        return auth_module
    if edition == "DEMO":
        return "auth_master"
    if line == "clearism":
        return "auth_clear"
    return "auth_master"


def sanitize_hook_name(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", value)
    return safe.strip("._-") or "runtime_profile"


def write_runtime_profile_hook(
    *,
    exe_name: str,
    version: str,
    line: str,
    edition: str,
    auth_module: str,
    dry_run: bool,
) -> Path:
    hook_path = RUNTIME_HOOK_DIR / f"{sanitize_hook_name(exe_name)}_runtime_profile.py"
    print(
        "[build] runtime profile: "
        f"line={line} edition={edition} auth={auth_module} version={version}"
    )
    if dry_run:
        print(f"[build] runtime hook: {hook_path}")
        return hook_path

    RUNTIME_HOOK_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "import os",
        f"os.environ['APP_LINE'] = {json.dumps(line, ensure_ascii=True)}",
        f"os.environ['APP_EDITION'] = {json.dumps(edition, ensure_ascii=True)}",
        f"os.environ['APP_AUTH_MODULE'] = {json.dumps(auth_module, ensure_ascii=True)}",
        f"os.environ['APP_VERSION'] = {json.dumps(version, ensure_ascii=True)}",
        "",
    ]
    hook_path.write_text("\n".join(lines), encoding="utf-8")
    return hook_path


def run_pyinstaller(
    spec_file: Path,
    exe_name: str,
    *,
    version: str,
    line: str,
    edition: str,
    auth_module: str,
    clean: bool,
    dry_run: bool,
    bundle_browser: bool,
    runtime_hook: Path,
) -> float:
    env = os.environ.copy()
    env[EXE_NAME_ENV] = exe_name
    env["APP_VERSION"] = version
    env["APP_LINE"] = line
    env["APP_EDITION"] = edition
    env["APP_AUTH_MODULE"] = auth_module
    env["BUNDLE_PLAYWRIGHT_BROWSER"] = "1" if bundle_browser else "0"
    env[RUNTIME_HOOK_ENV] = str(runtime_hook)

    base_cmd = ["pyinstaller", "--noconfirm", spec_file.name]
    cmd = ["pyinstaller", "--noconfirm"]
    if clean:
        cmd.append("--clean")
    cmd.append(spec_file.name)

    print(f"[build] spec: {spec_file.name}")
    print(f"[build] exe名: {exe_name}")
    print(f"[build] playwright browser同梱: {'ON' if bundle_browser else 'OFF'}")
    print(f"[build] runtime hook: {runtime_hook}")
    print(f"[build] command: {' '.join(cmd)}")
    if dry_run:
        return time.time()

    started_at = time.time()
    try:
        subprocess.run(cmd, cwd=PROJECT_DIR, env=env, check=True)
    except subprocess.CalledProcessError:
        if clean:
            print("[build] clean build failed. retrying once without --clean...")
            started_at = time.time()
            subprocess.run(base_cmd, cwd=PROJECT_DIR, env=env, check=True)
        else:
            raise
    return started_at


def find_built_binary(spec_file: Path, exe_name: str, started_at: float) -> Path:
    direct_candidates = [
        DIST_DIR / f"{exe_name}.exe",
        DIST_DIR / exe_name,
        DIST_DIR / f"{spec_file.stem}.exe",
        DIST_DIR / spec_file.stem,
    ]
    for c in direct_candidates:
        if c.exists() and c.is_file():
            return c

    if not DIST_DIR.exists():
        raise FileNotFoundError(f"dist が見つかりません: {DIST_DIR}")

    wildcard_candidates = []
    for p in DIST_DIR.iterdir():
        if not p.is_file():
            continue
        if p.name.endswith("_VERSION.txt") or p.name.endswith("_CHANGELOG.md"):
            continue
        if p.suffix not in (".exe", ""):
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= (started_at - 2.0):
            wildcard_candidates.append((mtime, p))

    if wildcard_candidates:
        wildcard_candidates.sort(key=lambda x: x[0], reverse=True)
        return wildcard_candidates[0][1]

    tried = ", ".join([c.name for c in direct_candidates])
    raise FileNotFoundError(
        "ビルド成果物が見つかりません。候補を確認してください: "
        f"{tried}"
    )


def determine_artifact_suffix(built_binary: Path) -> str:
    name = built_binary.name.lower()
    if name.endswith(".exe"):
        return ".exe"

    if os.name == "nt":
        return ".exe"

    suffix = built_binary.suffix
    if not suffix:
        return ""
    if suffix[1:].isdigit():
        return ""
    return suffix


def ensure_versioned_artifact(built_binary: Path, exe_name: str, *, dry_run: bool) -> Path:
    suffix = determine_artifact_suffix(built_binary)
    dst = DIST_DIR / f"{exe_name}{suffix}"
    if built_binary == dst:
        print(f"[release] 成果物名OK: {dst.name}")
        return dst

    print(f"[release] rename: {built_binary.name} -> {dst.name}")
    if dry_run:
        return dst

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.move(str(built_binary), str(dst))
    return dst


def copy_release_notes(exe_name: str, version_file: Path, changelog_file: Path, *, dry_run: bool) -> None:
    version_dst = DIST_DIR / f"{exe_name}_VERSION.txt"
    changelog_dst = DIST_DIR / f"{exe_name}_CHANGELOG.md"

    print(f"[release] {version_file.name} -> {version_dst.name}")
    if changelog_file.exists():
        print(f"[release] {changelog_file.name} -> {changelog_dst.name}")
    else:
        print("[release] CHANGELOG_CUSTOMER.md が無いためスキップ")

    if dry_run:
        return

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(version_file, version_dst)
    if changelog_file.exists():
        shutil.copy2(changelog_file, changelog_dst)


def build_release(
    *,
    spec_file: Path,
    version_file: Path,
    changelog_file: Path,
    clean: bool,
    dry_run: bool,
    bundle_browser: bool,
    app_name_arg: str = "",
    line_arg: str = "",
    edition_arg: str = "",
    auth_module_arg: str = "",
    include_version_suffix: bool = True,
) -> Path:
    app_basename = infer_app_basename(spec_file, app_name_arg)
    version = read_version(version_file)
    exe_name = build_exe_name(app_basename, version, include_version=include_version_suffix)
    line = normalize_line_arg(line_arg) or infer_line_from_app_basename(app_basename)
    edition = normalize_edition_arg(edition_arg) or infer_edition_from_app_basename(app_basename)
    auth_module = select_auth_module(line, edition, auth_module_arg)
    runtime_hook = write_runtime_profile_hook(
        exe_name=exe_name,
        version=version,
        line=line,
        edition=edition,
        auth_module=auth_module,
        dry_run=dry_run,
    )
    if bundle_browser and (not dry_run):
        ensure_playwright_chromium_ready()
    started_at = run_pyinstaller(
        spec_file,
        exe_name,
        version=version,
        line=line,
        edition=edition,
        auth_module=auth_module,
        clean=clean,
        dry_run=dry_run,
        bundle_browser=bundle_browser,
        runtime_hook=runtime_hook,
    )

    final_artifact = DIST_DIR / f"{exe_name}.exe"
    if not dry_run:
        built = find_built_binary(spec_file, exe_name, started_at)
        final_artifact = ensure_versioned_artifact(built, exe_name, dry_run=False)
    else:
        print(f"[release] (dry-run) expected artifact: {final_artifact.name}")

    copy_release_notes(exe_name, version_file, changelog_file, dry_run=dry_run)
    print(f"[done] version={version} exe={final_artifact.name}")
    if not dry_run:
        print(f"[done] outputs: {DIST_DIR}")
    return final_artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "PyInstaller spec から案件名を判定し、"
            "バージョン付き名称でビルドする"
        )
    )
    parser.add_argument("--spec", default="", help="対象spec（未指定時は自動判定）")
    parser.add_argument("--app-name", default="", help="成果物ベース名（未指定時は商品名）")
    parser.add_argument("--line", default="", help="製品ライン（aqua / clearism）")
    parser.add_argument("--edition", default="", help="エディション（GOLD / SILVER / BRONZE / DEMO）")
    parser.add_argument("--auth-module", default="", help="認証モジュール（auth_clear / auth_master）")
    parser.add_argument("--no-version-suffix", action="store_true", help="成果物名に _vX.Y.Z を付けない")
    parser.add_argument("--version-file", default=str(VERSION_FILE), help="VERSION.txt のパス")
    parser.add_argument("--changelog", default=str(CHANGELOG_FILE), help="CHANGELOG のパス")
    parser.add_argument("--clean", action="store_true", help="PyInstaller を clean build で実行する")
    parser.add_argument("--bundle-browser", action="store_true", help="Playwright Chromium をEXEへ同梱する")
    parser.add_argument("--dry-run", action="store_true", help="実行せずコマンドのみ表示する")
    args = parser.parse_args()

    try:
        if os.name != "nt":
            print(
                "[warn] 非Windows環境では Windows向け .exe は生成されません。"
                " 実配布用ビルドは Windows 上で実行してください。"
            )

        spec_file = find_spec_file(args.spec)
        version_file = Path(args.version_file).resolve()
        changelog_file = Path(args.changelog).resolve()

        build_release(
            spec_file=spec_file,
            version_file=version_file,
            changelog_file=changelog_file,
            clean=args.clean,
            dry_run=args.dry_run,
            bundle_browser=bool(args.bundle_browser),
            app_name_arg=args.app_name,
            line_arg=args.line,
            edition_arg=args.edition,
            auth_module_arg=args.auth_module,
            include_version_suffix=(not args.no_version_suffix),
        )
        return 0
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
