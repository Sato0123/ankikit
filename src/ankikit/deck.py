"""decks/ 配下のデッキ定義を読み込む。

    decks/
      README.md              ← 運用全体の方針
      english-vocab/
        README.md            ← このデッキの方針（フロントマターに設定）
        cards/2026-08-20.md  ← カード本体

デッキの README.md のフロントマター:

    ---
    anki_deck: "英語::語彙"   # Anki 上の実デッキ名（省略時は slug）
    note_type: basic          # basic | cloze（カード側の {{c1::}} が優先）
    tags: [english]           # このデッキの全カードに付くタグ
    ---
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .parser import Card, ParseError, parse_file, split_frontmatter


@dataclass
class Deck:
    slug: str
    path: Path
    anki_deck: str
    note_type: str = "basic"
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def readme(self) -> Path:
        return self.path / "README.md"

    @property
    def cards_dir(self) -> Path:
        return self.path / "cards"

    def card_files(self) -> list[Path]:
        if not self.cards_dir.is_dir():
            return []
        return sorted(p for p in self.cards_dir.glob("*.md") if p.name != "README.md")

    def load_cards(self) -> tuple[list[Card], list[ParseError]]:
        cards: list[Card] = []
        errors: list[ParseError] = []
        for path in self.card_files():
            parsed = parse_file(path)
            errors.extend(parsed.errors)
            for card in parsed.cards:
                card.tags = list(dict.fromkeys([*self.tags, *card.tags]))
                cards.append(card)

        seen: dict[str, Card] = {}
        unique: list[Card] = []
        for card in cards:
            if card.uid in seen:
                other = seen[card.uid]
                if other.source != card.source:
                    errors.append(
                        ParseError(card.source or self.path, card.line, f"{other.location()} と表面が重複")
                    )
                continue
            seen[card.uid] = card
            unique.append(card)
        return unique, errors


def load_deck(path: Path) -> Deck:
    meta: dict = {}
    readme = path / "README.md"
    if readme.exists():
        meta, _, _ = split_frontmatter(readme.read_text(encoding="utf-8"))

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.replace(",", " ").split() if t]

    return Deck(
        slug=path.name,
        path=path,
        anki_deck=str(meta.get("anki_deck") or path.name),
        note_type=str(meta.get("note_type") or "basic"),
        tags=list(tags),
        meta=meta,
    )


def load_decks(root: Path | None = None) -> list[Deck]:
    root = root or config.DECKS_DIR
    if not root.is_dir():
        return []
    return [load_deck(p) for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith((".", "_"))]


def find_deck(slug: str, root: Path | None = None) -> Deck | None:
    for deck in load_decks(root):
        if deck.slug == slug or deck.anki_deck == slug:
            return deck
    return None
