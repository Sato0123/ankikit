"""`ankikit word` と別名 `ankikit eng` の配線。

中身（検証・空欄化・重複）は test_vocab.py が見ている。ここで固定するのは
**どのデッキに入るか**だけ。ここがずれると、黙って別のデッキにカードが入る。
"""

from __future__ import annotations

import pytest

from ankikit import config
from ankikit.cli import build_parser
from ankikit.commands import eng, word


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


def test_wordとengの両方が生えている():
    assert parse(["word", "a.json"]).run is word.run
    assert parse(["eng", "a.json"]).run is eng.run


def test_engだけが既定デッキを持つ():
    # `word` は入れ先を勝手に決めない。`eng` と打ったときだけ english-vocab に落ちる。
    assert parse(["word", "a.json"]).fallback_deck is None
    assert parse(["eng", "a.json"]).fallback_deck == eng.DEFAULT_DECK == "english-vocab"


def test_engも他のオプションはwordと同じ():
    args = parse(["eng", "a.json", "--deck", "sre", "--dry-run", "--tag", "duo3"])
    assert (args.deck, args.dry_run, args.tag) == ("sre", True, ["duo3"])


@pytest.mark.parametrize("argv", [["word"], ["eng"]])
def test_ファイルを渡さなければ落ちる(argv):
    with pytest.raises(SystemExit):
        parse(argv)


def test_デッキが決まらなければ止まる(tmp_path, monkeypatch, capsys):
    """--deck も JSON の deck も [word] deck も無いとき。黙って既定に入れない。"""
    monkeypatch.setattr(config, "word_default_deck", lambda: None)
    src = tmp_path / "terms.json"
    src.write_text('[{"word": "冪等性", "meaning": "何度やっても同じ"}]', encoding="utf-8")
    assert word.run(parse(["word", str(src)])) == 2
    assert "どのデッキに入れるか決まりません" in capsys.readouterr().err
