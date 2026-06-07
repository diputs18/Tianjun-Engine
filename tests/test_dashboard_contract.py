from __future__ import annotations

from pathlib import Path


def test_dashboard_does_not_call_legacy_chat_routes() -> None:
    static = Path("src/tianjun/interfaces/dashboard/static/js")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in static.rglob("*.js"))

    assert '"/intent"' not in combined
    assert '"/chat"' not in combined
    assert '"/hermes/' not in combined
