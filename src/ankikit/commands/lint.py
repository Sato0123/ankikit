"""`ankikit lint` — 作業ツリーのカードファイルの書式チェック。"""

from __future__ import annotations

import argparse

from ..deck import load_decks
from . import common

NAME = "lint"
HELP = "カードファイルの書式チェック（作業ツリー）"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--deck", help="対象デッキの slug")


def run(args: argparse.Namespace) -> int:
    decks = common.select(load_decks(), args.deck)
    if decks is None:
        return 1

    failed = 0
    for deck in decks:
        cards, errors = deck.load_cards()
        for err in errors:
            common.error(str(err))
        failed += len(errors)
        cloze = sum(1 for c in cards if c.is_cloze)
        known = sum(1 for c in cards if c.known)
        print(
            f"{common.describe(deck)}: {len(cards)} 枚"
            f"（うち穴埋め {cloze} / 既習 {known}）, エラー {len(errors)} 件"
        )
    return 1 if failed else 0
