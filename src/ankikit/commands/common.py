"""サブコマンドが共通で使う小道具。表示と「承認済みデッキの取り出し」だけ。"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

from .. import approval
from ..deck import Deck, load_decks


def describe(deck: Deck) -> str:
    return f"{deck.slug} → {deck.anki_deck}"


def warn(message: str) -> None:
    print(f"警告: {message}", file=sys.stderr)


def error(message: str) -> None:
    print(f"ERROR {message}", file=sys.stderr)


def select(decks: list[Deck], slug: str | None) -> list[Deck] | None:
    """--deck の指定で絞り込む。見つからなければ None（呼び出し側は 1 を返す）。"""
    if not slug:
        return decks
    for deck in decks:
        if deck.slug == slug or deck.anki_deck == slug:
            return [deck]
    available = ", ".join(d.slug for d in decks) or "(なし)"
    error(f"デッキ '{slug}' が見つかりません。利用可能: {available}")
    return None


def uids_by_slug(decks: list[Deck]) -> dict[str, set[str]]:
    """デッキごとのカード uid 集合。承認済みと作業ツリーの差分をとるのに使う。"""
    return {deck.slug: {card.uid for card in deck.load_cards()[0]} for deck in decks}


@contextmanager
def approved_decks(ref: str) -> Iterator[list[Deck]]:
    """ref（既定 main）にマージ済みのデッキ一覧。

    一時ディレクトリへの展開なので、カードを読むのは必ず with の中で行うこと。
    """
    if not approval.is_repo():
        warn("git リポジトリではないため作業ツリーの内容を使います")
        yield load_decks()
        return
    if not approval.ref_exists(ref):
        raise approval.GitError(f"リファレンス '{ref}' が見つかりません")
    with approval.decks_at(ref) as root:
        yield [] if root is None else load_decks(root)


def pending_uids(ref: str) -> dict[str, set[str]]:
    """作業ツリーにあって ref にまだ無いカードの uid をデッキごとに返す。"""
    with approved_decks(ref) as merged:
        approved = uids_by_slug(merged)
    return {
        deck.slug: {card.uid for card in deck.load_cards()[0]} - approved.get(deck.slug, set())
        for deck in load_decks()
    }


def require_repo() -> bool:
    if approval.is_repo():
        return True
    error("git リポジトリではありません")
    return False
