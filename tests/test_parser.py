"""カードファイルの記法（decks/README.md）が仕様どおり読めているかのテスト。"""

from __future__ import annotations

from ankikit.parser import parse_text, split_frontmatter, to_html


def test_フロントマターを本文と分離する():
    meta, body, offset = split_frontmatter("---\ntags: [a, b]\n---\n## Q: x\nA: y\n")
    assert meta == {"tags": ["a", "b"]}
    assert body.startswith("## Q: x")
    assert offset == 4  # 本文は 4 行目から


def test_フロントマターが無ければそのまま本文():
    meta, body, offset = split_frontmatter("## Q: x\nA: y\n")
    assert meta == {}
    assert offset == 1
    assert body.startswith("## Q: x")


def test_表面のQ接頭辞は取り除かれる():
    parsed = parse_text("## Q: circle back\nA: 後で改めて議論する\n")
    assert [c.front for c in parsed.cards] == ["circle back"]
    assert [c.back for c in parsed.cards] == ["後で改めて議論する"]


def test_裏面は次の見出しまで複数行つづく():
    parsed = parse_text("## front\nA: 一行目\n二行目\n\n## next\nA: b\n")
    assert parsed.cards[0].back == "一行目\n二行目"
    assert len(parsed.cards) == 2


def test_ファイルタグとカードタグが合流する():
    parsed = parse_text("---\ntags: [meeting]\n---\n## front\nA: back\ntags: nuance, idiom\n")
    assert parsed.cards[0].tags == ["meeting", "nuance", "idiom"]


def test_HTMLコメントはAnkiに送られない():
    parsed = parse_text("## front\nA: back\n<!-- 出典: 今日のMTG -->\n")
    assert parsed.cards[0].back == "back"


def test_穴埋め記法があればcloze扱い():
    parsed = parse_text("## {{c1::defer}} to someone\nA: 一任する\n")
    card = parsed.cards[0]
    assert card.is_cloze
    assert card.note_type == "cloze"


def test_通常カードはbasic扱い():
    assert parse_text("## front\nA: back\n").cards[0].note_type == "basic"


def test_uidは表面だけで決まる():
    a = parse_text("## front\nA: back1\n").cards[0]
    b = parse_text("## front\nA: back2\n").cards[0]
    c = parse_text("## ちがう\nA: back1\n").cards[0]
    assert a.uid == b.uid  # 裏面を直しても同じカード → 更新される
    assert a.uid != c.uid  # 表面を直すと別カード


def test_A行が無ければエラー():
    parsed = parse_text("## front だけ\n説明\n")
    assert parsed.cards == []
    assert "'A:' 行がありません" in str(parsed.errors[0])


def test_裏面が空ならエラー():
    parsed = parse_text("## front\nA:\n")
    assert parsed.cards == []
    assert "裏面が空です" in str(parsed.errors[0])


def test_同一ファイル内の表面重複はエラー():
    parsed = parse_text("## front\nA: a\n\n## front\nA: b\n")
    assert len(parsed.errors) == 1
    assert "重複" in str(parsed.errors[0])


def test_エラーには行番号が入る():
    parsed = parse_text("---\ntags: [x]\n---\n\n## front だけ\n")
    assert parsed.errors[0].line == 5


def test_改行はbrに変換される():
    assert to_html("a\nb") == "a<br>b"
