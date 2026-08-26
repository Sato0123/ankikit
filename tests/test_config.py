"""anki.toml の読み込みのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ankikit import config


def test_ファイルが無ければ既定値(tmp_path):
    note_types = config.load_note_types(tmp_path / "missing.toml")
    assert note_types == config.DEFAULTS


def test_項目単位で上書きできる(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text('[note_types.basic]\nmodel = "Basic"\nfront = "Front"\nback = "Back"\n', "utf-8")
    note_types = config.load_note_types(path)
    assert note_types["basic"] == config.NoteType("Basic", "Front", "Back")
    assert note_types["cloze"] == config.DEFAULTS["cloze"]  # 書かなかった方は既定のまま


def test_一部のキーだけ書いても残りは既定値(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text('[note_types.cloze]\nmodel = "Cloze"\n', "utf-8")
    cloze = config.load_note_types(path)["cloze"]
    assert cloze.model == "Cloze"
    assert cloze.front == config.DEFAULTS["cloze"].front


def test_独自のノートタイプも足せる(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text('[note_types.code]\nmodel = "Code"\nfront = "Q"\nback = "A"\n', "utf-8")
    assert config.load_note_types(path)["code"].model == "Code"


def test_壊れたtomlはConfigError(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text("[note_types.basic\nmodel =", "utf-8")
    with pytest.raises(config.ConfigError):
        config.load_note_types(path)


def test_未定義のnote_typeはConfigError():
    with pytest.raises(config.ConfigError, match="利用可能"):
        config.note_type("そんなものはない")


def test_リポジトリのanki_tomlが実際に読める():
    """同梱の anki.toml が壊れていないことの確認。"""
    assert set(config.load_note_types()) >= {"basic", "cloze"}


# --------------------------------------------------------------------------- [word]


def test_wordの既定デッキを読める(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text('[word]\ndeck = "sre"\n', "utf-8")
    assert config.word_default_deck(path) == "sre"


def test_wordの既定デッキが無ければNone(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text('[note_types.basic]\nmodel = "Basic"\n', "utf-8")
    assert config.word_default_deck(path) is None
    assert config.word_default_deck(tmp_path / "missing.toml") is None


def test_wordがテーブルでなければConfigError(tmp_path):
    path = tmp_path / "anki.toml"
    path.write_text('word = "sre"\n', "utf-8")
    with pytest.raises(config.ConfigError, match="テーブル"):
        config.word_default_deck(path)


# --------------------------------------------------------------------------- ルート探索


def test_環境変数が最優先(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ROOT_ENV, str(tmp_path))
    assert config.find_repo_root(Path("/")) == tmp_path.resolve()


def test_カレントから上へ目印を探す(tmp_path, monkeypatch):
    monkeypatch.delenv(config.ROOT_ENV, raising=False)
    root = tmp_path / "cards"
    (root / "decks" / "sre" / "cards").mkdir(parents=True)
    assert config.find_repo_root(root / "decks" / "sre") == root


def test_anki_tomlも目印になる(tmp_path, monkeypatch):
    """decks/ をまだ作っていない立ち上げ直後でもルートを見つけられる。"""
    monkeypatch.delenv(config.ROOT_ENV, raising=False)
    (tmp_path / "anki.toml").write_text("", encoding="utf-8")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert config.find_repo_root(sub) == tmp_path


def test_目印が無ければカレントを返す(tmp_path, monkeypatch):
    """ここで site-packages の親などを返すと、黙って 0 件になって気づけない。"""
    monkeypatch.delenv(config.ROOT_ENV, raising=False)
    empty = tmp_path / "empty"
    empty.mkdir()
    found = config.find_repo_root(empty)
    assert found == empty or found == config.REPO_ROOT
