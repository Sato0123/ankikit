"""git を使った「承認」の仕組み。

**承認済み = main にマージ済み**。push は作業ツリーではなく指定リファレンス（既定 main）の
`decks/` を読むので、ブランチ上で書いただけのカードはマージされるまで Anki に入らない。

前半が git コマンドの薄いラッパ、後半が承認の判定。
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from . import config

APPROVED_REF = "main"
STAGE_PREFIX = "staging"


class GitError(RuntimeError):
    pass


# --------------------------------------------------------------------------- git ラッパ


def git(*args: str) -> str:
    """リポジトリ直下で git を実行し、標準出力を返す。失敗したら GitError。"""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=config.REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git コマンドが見つかりません") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise GitError(detail or f"git {' '.join(args)} が失敗しました")
    return (proc.stdout or "").strip()


def is_repo() -> bool:
    try:
        return git("rev-parse", "--is-inside-work-tree") == "true"
    except GitError:
        return False


def ref_exists(ref: str) -> bool:
    try:
        git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return True
    except GitError:
        return False


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def dirty_paths(pathspec: str = "decks") -> list[str]:
    """pathspec 配下の未コミットの変更（追跡外も含む）を返す。"""
    try:
        out = git("status", "--porcelain", "--", pathspec)
    except GitError:
        return []
    return [line[3:] for line in out.splitlines() if line.strip()]


# --------------------------------------------------------------------------- 承認の判定


def stage_branch(slug: str) -> str:
    """デッキ 1 つに対応する作業ブランチ名。"""
    return f"{STAGE_PREFIX}/{slug}"


def is_merged(branch: str, into: str = APPROVED_REF) -> bool:
    """branch の全コミットが into に含まれているか（＝承認済みか）。"""
    try:
        return git("rev-list", "--count", f"{into}..{branch}") == "0"
    except GitError:
        return False


@contextmanager
def decks_at(ref: str) -> Iterator[Path | None]:
    """ref 時点の `decks/` を一時ディレクトリへ展開し、そのパスを返す。

    ref に `decks/` がまだ無ければ None（1 枚もマージされていない状態）。
    """
    try:
        proc = subprocess.run(
            ["git", "archive", "--format=tar", ref, "--", "decks"],
            cwd=config.REPO_ROOT,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git コマンドが見つかりません") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        if "did not match any files" in stderr or "pathspec" in stderr:
            yield None
            return
        raise GitError(stderr or f"git archive {ref} が失敗しました")

    with tempfile.TemporaryDirectory(prefix="ankikit-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        extracted = Path(tmp) / "decks"
        yield extracted if extracted.is_dir() else None
