"""`ankikit decks` — デッキ一覧・枚数・未マージ枚数・Anki 側の有無。"""

from __future__ import annotations

import argparse

from .. import approval, connect
from ..deck import load_decks
from . import common

NAME = "decks"
HELP = "デッキ一覧・枚数・未マージ枚数"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    decks = load_decks()
    if not decks:
        print("decks/ にデッキがありません。`uv run ankikit new <slug>` で作成してください。")
        return 0

    # git / Anki はどちらも欠けていて構わない。分かる範囲だけ表示する。
    pending: dict[str, set[str]] = {}
    if approval.is_repo():
        try:
            pending = common.pending_uids(args.ref)
        except approval.GitError as exc:
            common.warn(str(exc))

    live: set[str] | None = None
    try:
        live = set(connect.deck_names())
    except connect.AnkiUnavailable:
        print("（Anki 未起動のため Anki 側の状態は未確認）\n")

    for deck in decks:
        cards, errors = deck.load_cards()
        bits = [f"カード {len(cards)} 枚"]
        if pending.get(deck.slug):
            bits.append(f"未マージ {len(pending[deck.slug])} 枚")
        if errors:
            bits.append(f"パースエラー {len(errors)} 件")
        if live is not None:
            bits.append("Anki:有" if deck.anki_deck in live else "Anki:未作成")
        print(f"{common.describe(deck)}  " + " / ".join(bits))
    return 0
