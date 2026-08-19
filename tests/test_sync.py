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
