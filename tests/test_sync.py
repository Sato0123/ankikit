"""push の差分判定（追加 / 更新 / 変更なし）のテスト。AnkiConnect は差し替える。"""

from __future__ import annotations

import pytest

from ankikit import config, sync
from ankikit.deck import load_deck


class FakeAnki:
    """connect モジュールの代わり。呼ばれた内容を記録するだけ。"""

    def __init__(self, notes: list[dict] | None = None):
        self.notes = notes or []
        self.added: list[dict] = []
        self.updated: list[tuple[int, dict]] = []
        self.created_decks: list[str] = []
        self.due_dates: list[tuple[list[int], int]] = []
        self.tagged: list[tuple[list[int], str]] = []
        # note_id -> そのノートのカードの type（0=新規）。既定は新規 1 枚。
        self.card_types: dict[int, list[int]] = {}

    def create_deck(self, name):
        self.created_decks.append(name)

    def find_notes(self, query):
        return [n["noteId"] for n in self.notes]

    def notes_info(self, note_ids):
        return self.notes

    def add_note(self, note):
        self.added.append(note)
        return len(self.added)

    def update_note_fields(self, note_id, fields):
        self.updated.append((note_id, fields))

    def find_cards(self, query):
        note_id = int(query.split(":")[1])
        return [note_id * 100 + i for i in range(len(self.card_types.get(note_id, [0])))]

    def cards_info(self, card_ids):
        return [
            {"cardId": cid, "type": self.card_types.get(cid // 100, [0])[cid % 100]}
            for cid in card_ids
        ]

    def set_due_date(self, card_ids, days):
        self.due_dates.append((list(card_ids), days))

    def add_tags(self, note_ids, tags):
        self.tagged.append((list(note_ids), tags))


def note(uid: str, front: str, back: str, note_id: int = 1) -> dict:
    """AnkiConnect の notesInfo が返す形。"""
    return {
        "noteId": note_id,
        "tags": [config.TOOL_TAG, f"{config.UID_TAG_PREFIX}::{uid}"],
        "fields": {"表面": {"value": front}, "裏面": {"value": back}},
    }


@pytest.fixture
def fake(monkeypatch):
    anki = FakeAnki()
    monkeypatch.setattr(sync.connect, "create_deck", anki.create_deck)
    monkeypatch.setattr(sync.connect, "find_notes", anki.find_notes)
    monkeypatch.setattr(sync.connect, "notes_info", anki.notes_info)
    monkeypatch.setattr(sync.connect, "add_note", anki.add_note)
    monkeypatch.setattr(sync.connect, "update_note_fields", anki.update_note_fields)
    monkeypatch.setattr(sync.connect, "find_cards", anki.find_cards)
    monkeypatch.setattr(sync.connect, "cards_info", anki.cards_info)
    monkeypatch.setattr(sync.connect, "set_due_date", anki.set_due_date)
    monkeypatch.setattr(sync.connect, "add_tags", anki.add_tags)
    return anki


def make_deck(deck_dir, body: str):
    return load_deck(deck_dir("english", cards={"2026-08-20.md": body}))


def test_Ankiに無いカードは追加される(deck_dir, fake):
    report = sync.push_deck(make_deck(deck_dir, "## front\nA: back\n"))
    assert report.count("added") == 1
    assert fake.added[0]["fields"] == {"表面": "front", "裏面": "back"}
    assert fake.created_decks == ["english"]


def test_uidタグと共通タグが付く(deck_dir, fake):
    deck = make_deck(deck_dir, "## front\nA: back\ntags: idiom\n")
    card = deck.load_cards()[0][0]
    sync.push_deck(deck)
    assert fake.added[0]["tags"] == sorted(
        {config.TOOL_TAG, f"{config.UID_TAG_PREFIX}::{card.uid}", "idiom"}
    )


def test_裏面だけ変わったら更新(deck_dir, fake):
    deck = make_deck(deck_dir, "## front\nA: 新しい裏面\n")
    fake.notes = [note(deck.load_cards()[0][0].uid, "front", "古い裏面")]
    report = sync.push_deck(deck)
    assert report.count("updated") == 1
    assert fake.updated == [(1, {"裏面": "新しい裏面"})]


def test_同じ内容なら変更なし(deck_dir, fake):
    deck = make_deck(deck_dir, "## front\nA: back\n")
    fake.notes = [note(deck.load_cards()[0][0].uid, "front", "back")]
    report = sync.push_deck(deck)
    assert report.count("unchanged") == 1
    assert fake.updated == [] and fake.added == []


def test_表面を変えると別カードとして追加される(deck_dir, fake):
    deck = make_deck(deck_dir, "## 新しい表面\nA: back\n")
    fake.notes = [note("古いuid", "古い表面", "back")]
    report = sync.push_deck(deck)
    assert report.count("added") == 1


def test_複数行の裏面はbrになる(deck_dir, fake):
    sync.push_deck(make_deck(deck_dir, "## front\nA: 一行目\n二行目\n"))
    assert fake.added[0]["fields"]["裏面"] == "一行目<br>二行目"


def test_dry_runでは何も送らない(deck_dir, fake):
    report = sync.push_deck(make_deck(deck_dir, "## front\nA: back\n"), dry_run=True)
    assert report.count("added") == 1
    assert fake.added == [] and fake.created_decks == []


def test_パースエラーがあれば送らない(deck_dir, fake):
    report = sync.push_deck(make_deck(deck_dir, "## A行が無い\n"))
    assert report.errors and report.total == 0
    assert fake.added == []


def test_forceならエラーがあっても送る(deck_dir, fake):
    deck = make_deck(deck_dir, "## 壊れてる\n\n## front\nA: back\n")
    report = sync.push_deck(deck, force=True)
    assert report.errors
    assert report.count("added") == 1


# --- known:（既に答えられたカード）---------------------------------------


def test_known付きは既習タグと初期間隔が付く(deck_dir, fake):
    report = sync.push_deck(make_deck(deck_dir, "## front\nA: back\nknown: 3\n"))
    assert f"{config.KNOWN_TAG_PREFIX}::3" in fake.added[0]["tags"]
    # 追加された note_id は 1 → カードは 100 番台
    assert fake.due_dates == [([100], config.KNOWN_INTERVALS[3])]
    assert report.count_known() == 1


def test_known無しならスケジュールに触らない(deck_dir, fake):
    sync.push_deck(make_deck(deck_dir, "## front\nA: back\n"))
    assert fake.due_dates == []


def test_理解度が高いほど初期間隔が長い():
    levels = sorted(config.KNOWN_INTERVALS)
    days = [config.KNOWN_INTERVALS[lv] for lv in levels]
    assert days == sorted(days) and days[0] >= 1


def test_復習が始まったカードの間隔は書き換えない(deck_dir, fake):
    deck = make_deck(deck_dir, "## front\nA: back\nknown: 3\n")
    fake.notes = [note(deck.load_cards()[0][0].uid, "front", "back", note_id=7)]
    fake.card_types = {7: [2]}  # 2 = 復習カード
    report = sync.push_deck(deck)
    assert fake.due_dates == []
    assert report.count_known() == 0


def test_あとからknownを足すとまだ新規のカードには効く(deck_dir, fake):
    deck = make_deck(deck_dir, "## front\nA: back\nknown: 2\n")
    fake.notes = [note(deck.load_cards()[0][0].uid, "front", "back", note_id=7)]
    fake.card_types = {7: [0]}
    sync.push_deck(deck)
    assert fake.due_dates == [([700], config.KNOWN_INTERVALS[2])]
    assert fake.tagged == [([7], f"{config.KNOWN_TAG_PREFIX}::2")]


def test_間隔設定に失敗してもカード自体は成功扱い(deck_dir, fake, monkeypatch):
    def boom(card_ids, days):
        raise sync.connect.AnkiConnectError("setDueDate: なにか失敗")

    monkeypatch.setattr(sync.connect, "set_due_date", boom)
    report = sync.push_deck(make_deck(deck_dir, "## front\nA: back\nknown: 1\n"))
    assert report.count("added") == 1 and report.count("failed") == 0
    assert "既習の初期間隔" in report.results[0].detail
