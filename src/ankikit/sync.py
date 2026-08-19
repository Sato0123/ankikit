"""decks/ の内容を Anki へ反映する（ファイル → Anki の一方向）。

同一カードかどうかは表面（front）のハッシュで判定し、`ankikit-uid::<hash>` タグで
Anki 側を照合する。裏面だけ変えた場合は更新、表面を変えた場合は別カードとして追加される
（古いカードは Anki 側に残るので、必要なら手で消す）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config, connect
from .deck import Deck
from .parser import Card, ParseError, to_html


@dataclass
class CardResult:
    card: Card
    action: str  # added / updated / unchanged / failed
    detail: str = ""


@dataclass
class DeckReport:
    deck: Deck
    results: list[CardResult] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    dry_run: bool = False

    def count(self, action: str) -> int:
        return sum(1 for r in self.results if r.action == action)

    @property
    def total(self) -> int:
        return len(self.results)


def _uid_tag(uid: str) -> str:
    return f"{config.UID_TAG_PREFIX}::{uid}"


def _note_payload(card: Card, deck: Deck) -> dict:
    # 表面に {{c1::}} があればカード側の判定が優先。無ければデッキの既定。
    kind = card.note_type if card.is_cloze else deck.note_type
    spec = config.note_type(kind)
    return {
        "deckName": deck.anki_deck,
        "modelName": spec.model,
        "fields": {
            spec.front: to_html(card.front),
            spec.back: to_html(card.back),
        },
        "tags": sorted({config.TOOL_TAG, _uid_tag(card.uid), *card.tags}),
        "options": {"allowDuplicate": False},
    }


def _existing_by_uid(deck: Deck) -> dict[str, dict]:
    """このデッキに既にある ankikit 製ノートを uid でひける形にする。"""
    query = f'deck:"{deck.anki_deck}" tag:{config.UID_TAG_PREFIX}::*'
    note_ids = connect.find_notes(query)
    existing: dict[str, dict] = {}
    for info in connect.notes_info(note_ids):
        for tag in info.get("tags", []):
            if tag.startswith(f"{config.UID_TAG_PREFIX}::"):
                existing[tag.split("::", 1)[1]] = info
                break
    return existing


def push_deck(deck: Deck, dry_run: bool = False, force: bool = False) -> DeckReport:
    cards, errors = deck.load_cards()
    report = DeckReport(deck=deck, errors=errors, dry_run=dry_run)
    if errors and not force:
        return report
    if not cards:
        return report

    if not dry_run:
        connect.create_deck(deck.anki_deck)

    try:
        existing = _existing_by_uid(deck)
    except connect.AnkiUnavailable:
        if not dry_run:
            raise
        existing = {}

    for card in cards:
        payload = _note_payload(card, deck)
        current = existing.get(card.uid)

        if current is None:
            if dry_run:
                report.results.append(CardResult(card, "added"))
                continue
            try:
                connect.add_note(payload)
                report.results.append(CardResult(card, "added"))
            except connect.AnkiConnectError as exc:
                report.results.append(CardResult(card, "failed", str(exc)))
            continue

        wanted = payload["fields"]
        actual = {name: value.get("value", "") for name, value in current.get("fields", {}).items()}
        changed = {k: v for k, v in wanted.items() if actual.get(k) != v}
        if not changed:
            report.results.append(CardResult(card, "unchanged"))
            continue
        if dry_run:
            report.results.append(CardResult(card, "updated", "裏面が変更されています"))
            continue
        try:
            connect.update_note_fields(int(current["noteId"]), changed)
            report.results.append(CardResult(card, "updated"))
        except connect.AnkiConnectError as exc:
            report.results.append(CardResult(card, "failed", str(exc)))

    return report
