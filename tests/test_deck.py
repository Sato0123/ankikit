"""decks/<slug>/ の読み込み（README のフロントマターが設定になる）のテスト。"""

from __future__ import annotations

from ankikit.deck import load_deck, load_decks

README = """---
anki_deck: "英語::語彙"
note_type: cloze
tags: [english]
---

# english
"""


def test_READMEのフロントマターが設定になる(deck_dir):
    deck = load_deck(deck_dir("english", readme=README))
    assert deck.slug == "english"
    assert deck.anki_deck == "英語::語彙"
    assert deck.note_type == "cloze"
    assert deck.tags == ["english"]


def test_READMEが無ければディレクトリ名が既定値(deck_dir):
    deck = load_deck(deck_dir("sre"))
    assert deck.anki_deck == "sre"
    assert deck.note_type == "basic"


def test_デッキのタグが全カードに付く(deck_dir):
    deck = load_deck(
        deck_dir("english", readme=README, cards={"2026-08-20.md": "## front\nA: back\ntags: idiom\n"})
    )
    cards, errors = deck.load_cards()
    assert errors == []
    assert cards[0].tags == ["english", "idiom"]


def test_複数ファイルを日付順に読む(deck_dir):
    deck = load_deck(
        deck_dir(
            "english",
            cards={"2026-08-21.md": "## b\nA: b\n", "2026-08-20.md": "## a\nA: a\n"},
        )
    )
    cards, _ = deck.load_cards()
    assert [c.front for c in cards] == ["a", "b"]


def test_ファイルをまたぐ表面重複はエラーになり片方だけ残る(deck_dir):
    deck = load_deck(
        deck_dir(
            "english",
            cards={"2026-08-20.md": "## same\nA: a\n", "2026-08-21.md": "## same\nA: b\n"},
        )
    )
    cards, errors = deck.load_cards()
    assert len(cards) == 1
    assert len(errors) == 1
    assert "重複" in str(errors[0])


def test_ドット始まりのディレクトリは無視する(deck_dir):
    root = deck_dir("english").parent
    (root / ".scratch").mkdir()
    (root / "_wip").mkdir()
    assert [d.slug for d in load_decks(root)] == ["english"]
