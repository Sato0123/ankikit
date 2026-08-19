"""`ankikit pending` — 作業ツリーにあって ref にまだ無い（＝未承認の）カードを一覧する。"""

from __future__ import annotations

import argparse

from ..deck import load_decks
from . import common

NAME = "pending"
HELP = "まだ承認（マージ）されていないカードを一覧"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--deck", help="対象デッキの slug")


def run(args: argparse.Namespace) -> int:
    if not common.require_repo():
        return 1

    decks = common.select(load_decks(), args.deck)
    if decks is None:
        return 1
    pending = common.pending_uids(args.ref)

    total = 0
    for deck in decks:
        cards, _ = deck.load_cards()
        new = [c for c in cards if c.uid in pending.get(deck.slug, set())]
        if not new:
            continue
        total += len(new)
        print(f"{common.describe(deck)}: {args.ref} 未マージ {len(new)} 枚")
        for card in new:
            print(f"  {card.front[:60]}")

    if total == 0:
        print(f"未マージのカードはありません（{args.ref} と一致）")
    else:
        print(f"\n合計 {total} 枚。{args.ref} にマージすると `uv run ankikit push` の対象になります。")
    return 0
