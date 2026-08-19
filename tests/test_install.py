"""`ankikit install` — 同梱スキルをカード側のリポジトリに配る。"""

from __future__ import annotations

import argparse

from ankikit.commands import install


def _args(**overrides) -> argparse.Namespace:
    base = dict(agent="claude-code", target=None, list=False, force=False)
    return argparse.Namespace(**{**base, **overrides})


def test_スキルがパッケージに同梱されている():
    assert install.bundled_skills() == ["anki-grill", "anki-initialize"]


def test_空のリポジトリに配置する(tmp_path):
    assert install.run(_args(target=tmp_path)) == 0
    for name in install.bundled_skills():
        skill = tmp_path / ".claude" / "skills" / name / "SKILL.md"
        assert skill.is_file()
        assert skill.read_text(encoding="utf-8").startswith("---")


def test_二度目は上書きしない(tmp_path, capsys):
    install.run(_args(target=tmp_path))
    capsys.readouterr()
    assert install.run(_args(target=tmp_path)) == 0
    assert "そのまま" in capsys.readouterr().out


def test_手で直したスキルはforceが無ければ残る(tmp_path):
    install.run(_args(target=tmp_path))
    skill = tmp_path / ".claude" / "skills" / "anki-grill" / "SKILL.md"
    skill.write_text("手で書き換えた", encoding="utf-8")

    install.run(_args(target=tmp_path))
    assert skill.read_text(encoding="utf-8") == "手で書き換えた"

    install.run(_args(target=tmp_path, force=True))
    assert skill.read_text(encoding="utf-8") != "手で書き換えた"


def test_listは何も書かない(tmp_path, capsys):
    assert install.run(_args(target=tmp_path, list=True)) == 0
    assert not (tmp_path / ".claude").exists()
    assert "anki-grill" in capsys.readouterr().out


def test_無い場所を指したらエラー(tmp_path):
    assert install.run(_args(target=tmp_path / "missing")) == 1


def test_decksが無くても走る():
    """カード置き場を作る前に叩くコマンドなので、decks/ を要求してはいけない。"""
    assert install.NEEDS_DECKS is False
