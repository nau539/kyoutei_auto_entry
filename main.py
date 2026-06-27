from __future__ import annotations

import logging
from pathlib import Path
import re
import sys

from app import AutoEntryApp
from product_profile import runtime_log_basename


def setup_logging() -> None:
    log_dir = Path("runtime_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{runtime_log_basename()}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def resolve_runtime_version() -> str:
    if getattr(sys, "frozen", False):
        exe_name = Path(sys.executable).stem
        match = re.search(r"_v([0-9A-Za-z._-]+)$", exe_name)
        if match:
            return str(match.group(1))
    version_file = Path(__file__).resolve().with_name("VERSION.txt")
    if version_file.exists():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "unknown"


if __name__ == "__main__":
    setup_logging()
    logging.getLogger(__name__).info("起動バージョン: v%s", resolve_runtime_version())
    app = AutoEntryApp()
    app.mainloop()
