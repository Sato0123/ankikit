"""英単語 JSON（`ankikit eng` の入力）の読み込みと検証。

手打ち前提の形式なので、**壊れた入力でどう転ぶか**のテストが本体。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ankikit.parser import parse_text
from ankikit.vocab import (
    BLANK,
    Entry,
    VocabError,
    blank_out,
    dedupe,
    load_file,
    load_text,
    render,
    to_markdown,
    word_key,
)


def levels(loaded, level: str) -> list[str]:
    return [i.message for i in loaded.issues if i.level == level]


# --------------------------------------------------------------------------- 空欄化


def test_例文の単語が空欄になる():
    entry = load_text('[{"word": "anyway", "sentence": "Let\'s try anyway."}]').entries[0]
    assert entry.front == "Let's try ____."
    assert entry.sentence == "Let's try anyway."


def test_明示された空欄はそのまま使う():
    entry = load_text('[{"word": "wake", "sentence": "I ____ up early."}]').entries[0]
    assert entry.front == "I ____ up early."
    assert entry.sentence == "I wake up early."  # 裏面では埋め戻す


def test_アンダースコアの本数は揃えられる():
    assert blank_out("I ___________ up.", "wake").front == f"I {BLANK} up."


def test_語形変化を追って空欄にする():
    entry = load_text('[{"word": "circle back", "sentence": "She circled back to me."}]').entries[0]
    assert entry.front == "She ____ to me."
    assert entry.sentence == "She circled back to me."  # 裏面は実際の語形


@pytest.mark.parametrize(
    "word,sentence,surface",
    [
        ("try", "He tries hard.", "tries"),
        ("stop", "The bus stopped there.", "stopped"),
        ("use", "I am using it.", "using"),
        ("study", "She studied all night.", "studied"),
    ],
)
def test_素直な語形変化はカバーする(word, sentence, surface):
    assert blank_out(sentence, word).surface == surface


def test_大文字小文字は無視して探す():
    assert blank_out("Anyway, let's go.", "anyway").surface == "Anyway"


def test_部分一致では空欄にしない():
    # "try" が "country" の中に埋まっているだけなら見つけてはいけない
    assert blank_out("I love this country.", "try") is None


def test_複数回出てくる語は全部空欄にする():
    front = blank_out("Anyway, anyway, anyway.", "anyway").front
    assert "anyway" not in front.lower()


def test_見つからない語はエラーになって他は通る():
    loaded = load_text(
        '[{"word": "woke", "sentence": "I get up early."},'
        ' {"word": "anyway", "sentence": "Let\'s try anyway."}]'
    )
    assert [e.word for e in loaded.entries] == ["anyway"]
    assert "空欄にできません" in levels(loaded, "error")[0]


def test_明示空欄の外に答えが残っていたら警告する():
    loaded = load_text('[{"word": "try", "sentence": "I ____ to try again."}]')
    assert loaded.entries  # カード自体は作る
    assert "答えが見えます" in levels(loaded, "warn")[0]


# --------------------------------------------------------------------------- 入力の不備


def test_JSONが壊れていたら行と桁を出す():
    with pytest.raises(VocabError) as exc:
        load_text('[{"word": "a", "sentence": "b"},]')
    assert ":1:" in str(exc.value)
    assert "余分なカンマ" in str(exc.value)


def test_全角記号が混ざっていたらヒントを出す():
    with pytest.raises(VocabError) as exc:
        load_text('[{"word"： "a"}]')
    assert "全角" in str(exc.value)


def test_トップレベルが配列でもオブジェクトでもなければ落とす():
    with pytest.raises(VocabError, match="トップレベル"):
        load_text('"anyway"')


def test_オブジェクトなのに単語の配列が無ければ落とす():
    with pytest.raises(VocabError, match="配列が見つかりません"):
        load_text('{"deck": "english-vocab"}')


def test_空の入力は落とす():
    with pytest.raises(VocabError, match="1 件もありません"):
        load_text("[]")


def test_必須項目が欠けた行だけ落ちる():
    loaded = load_text('[{"word": "anyway"}, {"word": "any", "sentence": "any way"}]')
    assert [e.word for e in loaded.entries] == ["any"]
    assert "sentence が空です" in levels(loaded, "error")[0]


def test_エントリがオブジェクトでなければその行だけ落ちる():
    loaded = load_text('["anyway", {"word": "any", "sentence": "any way"}]')
    assert len(loaded.entries) == 1
    assert "オブジェクト" in levels(loaded, "error")[0]


def test_知らないキーは警告して無視する():
    loaded = load_text('[{"word": "anyway", "sentence": "try anyway", "meening": "とにかく"}]')
    assert loaded.entries[0].meaning == ""
    assert "meening" in levels(loaded, "warn")[0]


def test_値が配列なら文字列で書けと言う():
    loaded = load_text('[{"word": "anyway", "sentence": ["try", "anyway"]}]')
    assert not loaded.entries
    assert "文字列で書いてください" in levels(loaded, "error")[0]


def test_日本語のキーでも書ける():
    entry = load_text('[{"単語": "anyway", "例文": "try anyway", "意味": "とにかく"}]').entries[0]
    assert (entry.word, entry.meaning) == ("anyway", "とにかく")


def test_数値が来ても文字列として扱う():
    entry = load_text('[{"word": "anyway", "sentence": "try anyway", "note": 42}]').entries[0]
    assert entry.note == "42"


def test_改行はカード記法を壊さないよう潰す():
    entry = load_text('[{"word": "anyway", "sentence": "try anyway", "meaning": "とに\\nかく"}]').entries[0]
    assert entry.meaning == "とに かく"


def test_BOM付きでも読める():
    assert load_text('﻿[{"word": "anyway", "sentence": "try anyway"}]').entries


def test_ファイルが無ければ落とす(tmp_path: Path):
    with pytest.raises(VocabError, match="見つかりません"):
        load_file(tmp_path / "nope.json")


# --------------------------------------------------------------------------- 重複


def test_単語キーは大小と記号の揺れを吸収する():
    assert word_key("Circle Back") == word_key("circle-back") == "circle-back"


def test_既にデッキにある単語は飛ばして残りは通す():
    loaded = load_text(
        '[{"word": "anyway", "sentence": "try anyway"},'
        ' {"word": "however", "sentence": "however, it works"}]'
    )
    kept, issues = dedupe(loaded.entries, {"anyway"})
    assert [e.word for e in kept] == ["however"]
    assert issues[0].level == "skip"


def test_ファイル内の重複も飛ばす():
    loaded = load_text(
        '[{"word": "anyway", "sentence": "try anyway"},'
        ' {"word": "Anyway", "sentence": "anyway, go"}]'
    )
    kept, issues = dedupe(loaded.entries, set())
    assert len(kept) == 1
    assert "ファイル内の [1]" in issues[0].message


# --------------------------------------------------------------------------- Markdown 出力


def test_出力したMarkdownはparserがそのまま読める():
    loaded = load_text(
        '{"tags": ["duo3"], "words": [{"word": "anyway", "sentence": "Let\'s try anyway.",'
        ' "meaning": "とにかく", "note": "p.42"}]}'
    )
    parsed = parse_text(render(loaded.entries, loaded.tags, "words.json"))
    assert parsed.errors == []
    card = parsed.cards[0]
    assert card.front == "Let's try ____."
    assert card.back == "anyway\nとにかく\nLet's try anyway.\np.42"
    assert card.tags == ["word::anyway", "duo3"]


def test_意味とメモが無ければ裏面は単語と例文だけ():
    entry = Entry(word="anyway", front="try ____.", sentence="try anyway.")
    assert to_markdown(entry) == "## try ____.\nA: anyway\ntry anyway.\ntags: word::anyway"


def test_HTMLコメントは無害化されてparserに消されない():
    entry = load_text('[{"word": "anyway", "sentence": "try anyway", "note": "<!-- x -->"}]').entries[0]
    assert parse_text(render([entry])).cards[0].back.endswith("&lt;!-- x --&gt;")
