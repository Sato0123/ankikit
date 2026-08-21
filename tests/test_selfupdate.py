"""`ankikit update` / `ankikit change-version` — カード側の ankikit を入れ替える。

uv を実際に呼ぶ部分は差し替えて、**どんなコマンドを組み立てたか**だけを見る。
"""

from __future__ import annotations

import argparse

import pytest

from ankikit import selfupdate
from ankikit.commands import change_version, update

GIT_SOURCE = """\
[project]
name = "anki-decks"
dependencies = ["ankikit"]

[tool.uv.sources]
ankikit = { git = "https://github.com/Sato0123/ankikit" }
"""

LOCK = """\
[[package]]
name = "ankikit"
version = "0.1.0"
source = { git = "https://github.com/Sato0123/ankikit#3e3a566437edf221ad903360da59edf9c4859715" }
"""


@pytest.fixture
def project(tmp_path):
    """カード側のリポジトリを模したディレクトリを返す（pyproject を差し替えられる）。"""

    def build(pyproject: str = GIT_SOURCE, lock: str | None = LOCK):
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        if lock is not None:
            (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")
        return tmp_path

    return build


@pytest.fixture
def uv_calls(monkeypatch):
    """uv の呼び出しを記録するだけにする（ネットワークもファイルも触らせない）。"""
    calls: list[list[str]] = []
    monkeypatch.setattr(selfupdate, "run_uv", lambda project, args, **kw: calls.append(args))
    return calls


def _update_args(**overrides) -> argparse.Namespace:
    base = dict(target=None, dry_run=False, force=False, no_install=False)
    return argparse.Namespace(**{**base, **overrides})


def _change_args(**overrides) -> argparse.Namespace:
    base = dict(version=None, list=False, target=None, dry_run=False, force=False, no_install=False)
    return argparse.Namespace(**{**base, **overrides})


# --- 読み取り ---------------------------------------------------------------


def test_pyprojectを上へ探す(project):
    root = project()
    nested = root / "decks" / "english"
    nested.mkdir(parents=True)
    assert selfupdate.find_project(nested) == root


def test_pyprojectが無ければ止まる(tmp_path):
    with pytest.raises(selfupdate.UpdateError):
        selfupdate.find_project(tmp_path)


def test_git依存を読む(project):
    source = selfupdate.read_source(project())
    assert (source.kind, source.pin_kind, source.pinned) == ("git", None, False)


@pytest.mark.parametrize(
    ("pin", "pinned"),
    [('tag = "v0.2.0"', True), ('rev = "3e3a566"', True), ('branch = "main"', False)],
)
def test_固定の種類で更新できるかが変わる(project, pin, pinned):
    text = GIT_SOURCE.replace(
        '{ git = "https://github.com/Sato0123/ankikit" }',
        f'{{ git = "https://github.com/Sato0123/ankikit", {pin} }}',
    )
    source = selfupdate.read_source(project(text))
    assert source.kind == "git"
    assert source.pinned is pinned


def test_path参照を見分ける(project):
    text = GIT_SOURCE.replace(
        '{ git = "https://github.com/Sato0123/ankikit" }', '{ path = "../Anki", editable = true }'
    )
    assert selfupdate.read_source(project(text)).kind == "path"


def test_ロックから解決済みのコミットを読む(project):
    assert selfupdate.locked_commit(project()) == "3e3a566437edf221ad903360da59edf9c4859715"


def test_ロックが無ければコミットは分からない(project):
    assert selfupdate.locked_commit(project(lock=None)) is None


def test_取得元が無ければ既定のURLを使う(project):
    text = "[project]\nname = 'anki-decks'\ndependencies = ['ankikit']\n"
    assert selfupdate.git_url(project(text)) == selfupdate.DEFAULT_GIT_URL


@pytest.mark.parametrize(
    ("version", "option"),
    [("v0.2.0", "--tag"), ("main", "--branch"), ("3e3a566", "--rev")],
)
def test_タグかブランチかコミットかでピンの渡し方が変わる(version, option):
    assert selfupdate.pin_option(version, ["v0.2.0"], ["main"]) == option


# --- update -----------------------------------------------------------------


def test_updateは取り直してスキルも配り直す(project, uv_calls):
    assert update.run(_update_args(target=project())) == 0
    assert uv_calls == [
        ["lock", "--upgrade-package", "ankikit"],
        ["sync"],
        ["run", "ankikit", "install"],
    ]


def test_updateはバージョン固定なら何もせず案内する(project, uv_calls):
    text = GIT_SOURCE.replace(
        '{ git = "https://github.com/Sato0123/ankikit" }',
        '{ git = "https://github.com/Sato0123/ankikit", tag = "v0.2.0" }',
    )
    assert update.run(_update_args(target=project(text))) == 1
    assert uv_calls == []


def test_updateはpath参照なら入れ替えずスキルだけ配り直す(project, uv_calls):
    text = GIT_SOURCE.replace(
        '{ git = "https://github.com/Sato0123/ankikit" }', '{ path = "../Anki", editable = true }'
    )
    assert update.run(_update_args(target=project(text))) == 0
    assert uv_calls == [["run", "ankikit", "install"]]


def test_updateのforceはinstallまで届く(project, uv_calls):
    update.run(_update_args(target=project(), force=True))
    assert uv_calls[-1] == ["run", "ankikit", "install", "--force"]


def test_updateはno_installならスキルを触らない(project, uv_calls):
    update.run(_update_args(target=project(), no_install=True))
    assert ["run", "ankikit", "install"] not in uv_calls


# --- change-version ---------------------------------------------------------


def test_バージョンを指定して固定する(project, uv_calls, monkeypatch):
    monkeypatch.setattr(selfupdate, "remote_refs", lambda url: (["v0.2.0"], ["main"]))
    assert change_version.run(_change_args(version="v0.2.0", target=project())) == 0
    assert uv_calls == [
        ["add", "ankikit @ git+https://github.com/Sato0123/ankikit", "--tag", "v0.2.0"],
        ["run", "ankikit", "install"],
    ]


def test_latestは固定を外して取り直す(project, uv_calls):
    assert change_version.run(_change_args(version="latest", target=project())) == 0
    assert uv_calls[:3] == [
        ["add", "ankikit @ git+https://github.com/Sato0123/ankikit"],
        ["lock", "--upgrade-package", "ankikit"],
        ["sync"],
    ]


def test_バージョン無しは何もしない(project, uv_calls):
    assert change_version.run(_change_args(target=project())) == 1
    assert uv_calls == []


def test_path参照ではバージョンを選べない(project, uv_calls):
    text = GIT_SOURCE.replace(
        '{ git = "https://github.com/Sato0123/ankikit" }', '{ path = "../Anki", editable = true }'
    )
    assert change_version.run(_change_args(version="v0.2.0", target=project(text))) == 1
    assert uv_calls == []


def test_listは取得元のタグとブランチを出す(project, uv_calls, monkeypatch, capsys):
    monkeypatch.setattr(selfupdate, "remote_refs", lambda url: (["v0.1.0", "v0.2.0"], ["main"]))
    assert change_version.run(_change_args(list=True, target=project())) == 0
    out = capsys.readouterr().out
    assert "v0.2.0" in out and "main" in out
    assert uv_calls == []
