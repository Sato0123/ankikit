"""`ankikit status` の集計と README への書き戻しのテスト。Anki 側は差し替える。"""

from __future__ import annotations

from ankikit.commands import status
from ankikit.deck import load_deck

README = """---
tags: [tcp]
---

# tcp

## 目的
手が止まらないようにする。
"""

CARDS = """## a
A: x
known: 3

## b
A: y
"""


def make(deck_dir):
    return load_deck(deck_dir("tcp", readme=README, cards={"2026-08-20.md": CARDS}))


def test_既習の枚数を理解度ごとに数える(deck_dir):
    st = status.collect(make(deck_dir), pending=0, live=False)
    assert st.cards == 2 and st.known == {3: 1}
    assert st.anki is None


def test_notesの一覧を拾う(deck_dir):
    deck = make(deck_dir)
    deck.notes_dir.mkdir()
    (deck.notes_dir / "2026-08-20-handshake.md").write_text("メモ", encoding="utf-8")
    st = status.collect(deck, pending=0, live=False)
    assert st.notes == ["2026-08-20-handshake.md"]


def test_readmeのブロックだけ差し替える(deck_dir):
    deck = make(deck_dir)
    deck.readme.write_text(
        README + "\n## 学習状況\n\n<!-- ankikit:status -->\n古い内容\n<!-- /ankikit:status -->\n",
        encoding="utf-8",
    )
    status.write_readme(status.collect(deck, pending=0, live=False))
    text = deck.readme.read_text(encoding="utf-8")
    assert "古い内容" not in text
    assert "手が止まらないようにする。" in text  # 手で書いた方針は残る
    assert text.count(status.START) == 1


def test_ブロックが無ければ末尾に足す(deck_dir):
    deck = make(deck_dir)
    status.write_readme(status.collect(deck, pending=0, live=False))
    text = deck.readme.read_text(encoding="utf-8")
    assert text.strip().endswith(status.END)
    assert "## 学習状況" in text


def test_二回書いてもブロックは増えない(deck_dir):
    deck = make(deck_dir)
    for _ in range(2):
        status.write_readme(status.collect(deck, pending=0, live=False))
    assert deck.readme.read_text(encoding="utf-8").count(status.START) == 1
