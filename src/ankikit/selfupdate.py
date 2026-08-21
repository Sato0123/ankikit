"""ankikit 自身の入れ替え。**カード側のリポジトリ**の `pyproject.toml` と `uv` を触る。

カード側は ankikit を git 依存として入れているので、道具を直しても向こうは古いまま。
`ankikit update` / `ankikit change-version` はそこを動かすためのもので、
どちらも実体は `uv` の呼び出し + `ankikit install` の叩き直しでしかない。

**更新のあとのスキル配置は必ず子プロセスの `uv run ankikit install` で行う。**
自分自身を入れ替えた直後の Python プロセスには**古いパッケージが読み込まれたまま**なので、
その場で `install.run()` を呼ぶと古いスキルを配ってしまう。
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GIT_URL = "https://github.com/Sato0123/ankikit"
PACKAGE = "ankikit"
# change-version に渡すと「ピン留めをやめて既定ブランチに追従する」の意味になる語。
LATEST = ("latest", "最新")


class UpdateError(Exception):
    """uv が無い・pyproject が無い・コマンドが失敗した、など。"""


@dataclass(frozen=True)
class Source:
    """`[tool.uv.sources].ankikit` の中身。無ければ kind="none"。"""

    kind: str  # "git" | "path" | "none"
    url: str | None = None
    pin_kind: str | None = None  # "tag" | "rev" | "branch"
    pin: str | None = None

    @property
    def pinned(self) -> bool:
        """`update` で動かせない固定か。branch は追従するので固定ではない。"""
        return self.pin_kind in ("tag", "rev")

    def describe(self) -> str:
        if self.kind == "path":
            return f"path {self.url}（editable）"
        if self.kind == "none":
            return "指定なし（PyPI などのレジストリ）"
        if self.pin_kind:
            return f"git {self.url} @ {self.pin_kind}={self.pin}"
        return f"git {self.url}（既定ブランチに追従）"


def find_project(start: Path) -> Path:
    """`pyproject.toml` のあるディレクトリを上へ辿って探す。"""
    start = start.expanduser().resolve()
    for directory in (start, *start.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    raise UpdateError(
        f"pyproject.toml が見つかりません（{start} から上を探しました）。"
        "カードのあるリポジトリで実行してください。"
    )


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UpdateError(f"{path} を読めません: {exc}") from exc


def read_source(project: Path) -> Source:
    """カード側の pyproject が ankikit をどこから取っているか。"""
    sources = _load_toml(project / "pyproject.toml").get("tool", {}).get("uv", {}).get("sources", {})
    entry = sources.get(PACKAGE)
    if not isinstance(entry, dict):
        return Source(kind="none")
    if "path" in entry:
        return Source(kind="path", url=str(entry["path"]))
    if "git" not in entry:
        return Source(kind="none")
    for pin_kind in ("tag", "rev", "branch"):
        if pin_kind in entry:
            return Source(kind="git", url=entry["git"], pin_kind=pin_kind, pin=str(entry[pin_kind]))
    return Source(kind="git", url=entry["git"])


def git_url(project: Path) -> str:
    """取得元の URL。まだ git 依存でなければ既定の URL を使う。"""
    source = read_source(project)
    return source.url if source.kind == "git" and source.url else DEFAULT_GIT_URL


def locked_commit(project: Path) -> str | None:
    """`uv.lock` が記録している ankikit のコミット。

    uv は解決したコミットを `source = { git = "<url>#<sha>" }` の形で残す。
    """
    for package in _load_toml(project / "uv.lock").get("package", []):
        if package.get("name") != PACKAGE:
            continue
        url = package.get("source", {}).get("git", "")
        if "#" in url:
            return url.rsplit("#", 1)[1]
        return None
    return None


def run_uv(project: Path, args: list[str], *, dry_run: bool = False) -> None:
    """`uv <args>` をカード側のリポジトリで走らせる。"""
    uv = shutil.which("uv")
    if uv is None:
        raise UpdateError("uv が見つかりません（https://docs.astral.sh/uv/ で入れてください）")
    print(f"$ uv {' '.join(args)}")
    if dry_run:
        return
    result = subprocess.run([uv, *args], cwd=project)
    if result.returncode != 0:
        raise UpdateError(f"`uv {' '.join(args)}` が失敗しました（終了コード {result.returncode}）")


def reinstall_skills(project: Path, *, force: bool = False, dry_run: bool = False) -> None:
    """入れ替えた**あとの** ankikit でスキルを配り直す（子プロセスなのが肝）。"""
    args = ["run", "ankikit", "install"]
    if force:
        args.append("--force")
    run_uv(project, args, dry_run=dry_run)


def remote_refs(url: str) -> tuple[list[str], list[str]]:
    """取得元のタグとブランチ。取れなければ両方空（オフラインでも止めない）。"""
    git = shutil.which("git")
    if git is None:
        return [], []
    try:
        result = subprocess.run(
            [git, "ls-remote", "--tags", "--heads", "--refs", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return [], []
    if result.returncode != 0:
        return [], []

    tags, branches = [], []
    for line in result.stdout.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith("refs/tags/"):
            tags.append(ref.removeprefix("refs/tags/"))
        elif ref.startswith("refs/heads/"):
            branches.append(ref.removeprefix("refs/heads/"))
    return sorted(tags), sorted(branches)


def pin_option(version: str, tags: list[str], branches: list[str]) -> str:
    """`uv add` に渡すピンの種類。分からなければコミット指定として扱う。"""
    if version in tags:
        return "--tag"
    if version in branches:
        return "--branch"
    return "--rev"


def report_move(before: str | None, after: str | None) -> None:
    """コミットがどこからどこへ動いたかを 1 行で。"""
    if before and after and before == after:
        print(f"変わりません（{before[:12]}）")
    else:
        print(f"{(before or '不明')[:12]} → {(after or '不明')[:12]}")
