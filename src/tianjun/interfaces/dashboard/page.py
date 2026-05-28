from __future__ import annotations

from pathlib import Path


STATIC_DASHBOARD_PATH = Path(__file__).resolve().parent / "static" / "dashboard.html"


def render_dashboard_html() -> str:
    return STATIC_DASHBOARD_PATH.read_text(encoding="utf-8")
