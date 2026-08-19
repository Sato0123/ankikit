from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def deck_dir(tmp_path: Path):
    """decks/<slug>/ を組み立てるヘルパを返す。

        path = deck_dir("english", readme="---\\ntags: [english]\\n---", cards={"2026-08-20.md": "..."})
    """

    def build(slug: str, readme: str | None = None, cards: dict[str, str] | None = None) -> Path:
        root = tmp_path / "decks" / slug
        (root / "cards").mkdir(parents=True)
        if readme is not None:
            (root / "README.md").write_text(readme, encoding="utf-8")
        for name, text in (cards or {}).items():
            (root / "cards" / name).write_text(text, encoding="utf-8")
        return root

    return build
