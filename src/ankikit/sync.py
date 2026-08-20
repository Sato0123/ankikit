"""decks/ の内容を Anki へ反映する（ファイル → Anki の一方向）。

同一カードかどうかは表面（front）のハッシュで判定し、`ankikit-uid::<hash>` タグで
Anki 側を照合する。裏面だけ変えた場合は更新、表面を変えた場合は別カードとして追加される
（古いカードは Anki 側に残るので、必要なら手で消す）。

`known:` 付きのカード（＝面談で答えられたもの）は、Anki が**まだ新規と見なしている間だけ**
初期間隔の下駄を履かせる。復習が始まったカードには二度と触らないので、
何度 push しても学習履歴は壊れない。
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
    known_days: int | None = None  # 既習として初期間隔を与えたときだけ入る


@dataclass
class DeckReport:
    deck: Deck
    results: list[CardResult] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    dry_run: bool = False

    def count(self, action: str) -> int:
        return sum(1 for r in self.results if r.action == action)

    def count_known(self) -> int:
        """このセッションで「既習」として初期間隔を与えた枚数。"""
        return sum(1 for r in self.results if r.known_days is not None)

    @property
    def total(self) -> int:
        return len(self.results)


def _uid_tag(uid: str) -> str:
    return f"{config.UID_TAG_PREFIX}::{uid}"


def _known_tag(level: int) -> str:
    return f"{config.KNOWN_TAG_PREFIX}::{level}"


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
        "tags": sorted(
            {
                config.TOOL_TAG,
                _uid_tag(card.uid),
                *([_known_tag(card.known)] if card.known else []),
                *card.tags,
            }
        ),
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
                report.results.append(
                    CardResult(card, "added", known_days=config.KNOWN_INTERVALS.get(card.known or 0))
                )
                continue
            try:
                note_id = connect.add_note(payload)
                result = CardResult(card, "added")
                _apply_known(card, note_id, result)
                report.results.append(result)
            except connect.AnkiConnectError as exc:
                report.results.append(CardResult(card, "failed", str(exc)))
            continue

        wanted = payload["fields"]
        actual = {name: value.get("value", "") for name, value in current.get("fields", {}).items()}
        changed = {k: v for k, v in wanted.items() if actual.get(k) != v}
        action = "unchanged" if not changed else "updated"
        if dry_run:
            report.results.append(
                CardResult(card, action, "裏面が変更されています" if changed else "")
            )
            continue
        try:
            if changed:
                connect.update_note_fields(int(current["noteId"]), changed)
            result = CardResult(card, action)
            # 後から known: を足した場合を拾う。まだ手を付けていないカードにしか効かない。
            _apply_known(card, int(current["noteId"]), result, tags=current.get("tags", []))
            report.results.append(result)
        except connect.AnkiConnectError as exc:
            report.results.append(CardResult(card, "failed", str(exc)))

    return report


def _apply_known(card: Card, note_id: int, result: CardResult, tags: list[str] | None = None) -> None:
    """既習カードに初期間隔の下駄を履かせる。**Anki 側でまだ新規のカードだけ**が対象。

    復習が始まったカードを触ると間隔を書き換えてしまうので、type == 0 で絞る。
    ここでの失敗はカード自体の失敗ではない（ノートは入っている）ので、detail に残すだけにする。
    """
    if not card.known:
        return
    days = config.KNOWN_INTERVALS[card.known]
    try:
        infos = connect.cards_info(connect.find_cards(f"nid:{note_id}"))
        new_cards = [int(info["cardId"]) for info in infos if info.get("type", 0) == 0]
        if not new_cards:
            return  # 既に復習が始まっている。履歴を尊重して何もしない。
        connect.set_due_date(new_cards, days)
        if tags is not None and _known_tag(card.known) not in tags:
            connect.add_tags([note_id], _known_tag(card.known))
        result.known_days = days
    except connect.AnkiConnectError as exc:
        result.detail = f"既習の初期間隔を設定できませんでした: {exc}"
