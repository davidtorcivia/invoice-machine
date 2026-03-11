"""Skill manifest rendering helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

TEMPLATE_TOKEN = "__BASE_URL__"
TEMPLATE_PATH = Path(__file__).with_name("skill_manifest_template.md")


@lru_cache(maxsize=1)
def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_skill_manifest(base_url: str) -> str:
    """Render the bot skill manifest with the request base URL."""
    return _load_template().replace(TEMPLATE_TOKEN, base_url.rstrip("/"))
