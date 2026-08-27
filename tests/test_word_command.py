"""`ankikit word` と別名 `ankikit eng` の配線。

中身（検証・空欄化・重複）は test_vocab.py が見ている。ここで固定するのは
**どのデッキに入るか**だけ。ここがずれると、黙って別のデッキにカードが入る。
"""

from __future__ import annotations

import pytest

from ankikit import config
from ankikit.cli import build_parser
from ankikit.deck import find_deck
from ankikit.sync import DeckReport
from ankikit.commands import eng, new, word


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


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """decks/ だけがある空のカード置き場。git も Anki も無い状態で走らせる。"""
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config, "DECKS_DIR", tmp_path / "decks")
    monkeypatch.setattr(word.approval, "is_repo", lambda: False)
    return tmp_path


def terms(path, *words):
    body = ", ".join(f'{{"word": "{w}", "meaning": "{w}の意味"}}' for w in words)
    src = path / "terms.json"
    src.write_text(f"[{body}]", encoding="utf-8")
    return str(src)


def test_デッキが無ければ作ってそこに入れる(repo, capsys):
    assert word.run(parse(["word", terms(repo, "冪等性"), "--deck", "sre", "--no-push"])) == 0
    assert (repo / "decks" / "sre" / "README.md").exists()
    assert (repo / "decks" / "sre" / "cards").is_dir()
    written = next((repo / "decks" / "sre" / "cards").glob("*.md")).read_text(encoding="utf-8")
    assert "冪等性" in written and "word::冪等性" in written
    assert "が無かったので作りました" in capsys.readouterr().out


def test_デッキがあればそれを使う(repo):
    new.create("sre", anki_deck="SRE::用語")
    word.run(parse(["word", terms(repo, "冪等性"), "--deck", "sre", "--no-push"]))
    assert len(list((repo / "decks").iterdir())) == 1


def test_dry_runならデッキを作らない(repo):
    assert word.run(parse(["word", terms(repo, "冪等性"), "--deck", "sre", "--dry-run"])) == 0
    assert not (repo / "decks" / "sre").exists()


def test_pushするのは今書いた分だけ(repo, monkeypatch):
    """同じブランチに承認前のカードが置いてあっても、Anki へ行くのは新しい語だけ。"""
    new.create("sre")
    (repo / "decks" / "sre" / "cards" / "2020-01-01.md").write_text(
        "## 承認前の表面\nA: 裏\n", encoding="utf-8"
    )
    sent = []

    def fake_push(deck, cards=None):
        sent.append(cards)
        return DeckReport(deck=deck)

    monkeypatch.setattr(word.sync, "push_deck", fake_push)
    word.run(parse(["word", terms(repo, "冪等性"), "--deck", "sre"]))
    assert [c.front for c in sent[0]] == ["冪等性 とは？"]


def test_表裏で書けばそのままカードになる(repo):
    """`type` の出力のような「語 → その中身」は front/back で入れる。"""
    src = repo / "commands.json"
    src.write_text(
        '[{"front": "awk", "back": "/usr/bin/awk"}, {"front": "sed", "back": "/usr/bin/sed"}]',
        encoding="utf-8",
    )
    assert word.run(parse(["word", str(src), "--deck", "shell", "--no-push"])) == 0
    written = next((repo / "decks" / "shell" / "cards").glob("*.md")).read_text(encoding="utf-8")
    assert "## awk\nA: /usr/bin/awk" in written
    assert "____" not in written


def test_表面がぶつかっても残りは書き込む(repo, capsys):
    """例文に説明を入れて表面が潰れた行だけ落とす。**ファイルごと書けなくならない。**"""
    src = repo / "terms.json"
    src.write_text(
        '[{"word": "awk", "sentence": "/usr/bin/awk"},'
        ' {"word": "sed", "sentence": "/usr/bin/sed"},'
        ' {"word": "冪等性", "meaning": "何度やっても同じ"}]',
        encoding="utf-8",
    )
    assert word.run(parse(["word", str(src), "--deck", "sre", "--no-push"])) == 1
    written = next((repo / "decks" / "sre" / "cards").glob("*.md")).read_text(encoding="utf-8")
    assert "冪等性 とは？" in written
    assert written.count("## /usr/bin/____") == 1
    assert "表面が [1] awk と同じ" in capsys.readouterr().out


# --------------------------------------------------------------------- サブデッキ


def test_slugの区切りがAnkiのサブデッキになる():
    assert new.anki_deck_name("english.duo") == "english::duo"
    assert new.anki_deck_name("english") == "english"
    assert new.normalize_slug("english::duo") == "english.duo"


@pytest.mark.parametrize("slug", ["english.", ".english", "a..b", "a/b"])
def test_ディレクトリ名にできないslugは断る(slug):
    assert new.slug_problem(slug)


def test_ドット区切りで指定するとサブデッキとして作られる(repo, capsys):
    assert word.run(parse(["word", terms(repo, "anyway"), "--deck", "english.duo", "--no-push"])) == 0
    deck = find_deck("english.duo")
    assert deck.path == repo / "decks" / "english.duo"
    assert deck.anki_deck == "english::duo"
    assert "english::duo" in capsys.readouterr().out


def test_コロンで書いても同じデッキを指す(repo):
    """`english::duo` は Anki 側の書き方。同じデッキとして扱い、2 つ目を作らない。"""
    word.run(parse(["word", terms(repo, "anyway"), "--deck", "english.duo", "--no-push"]))
    word.run(parse(["word", terms(repo, "circle back"), "--deck", "english::duo", "--no-push"]))
    assert [p.name for p in (repo / "decks").iterdir()] == ["english.duo"]


def test_作れないslugなら何も書かずに止まる(repo, capsys):
    assert word.run(parse(["word", terms(repo, "anyway"), "--deck", "english.", "--no-push"])) == 2
    assert not (repo / "decks").exists()
    assert "'.' の前後が空です" in capsys.readouterr().err
