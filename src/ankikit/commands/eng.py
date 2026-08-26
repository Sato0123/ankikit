"""`ankikit eng` — `ankikit word` の別名。既定デッキが `english-vocab` になるだけ。

英単語デッキを先に作ったのでこの名前が残っている。中身は `word.py` にあり、
**挙動の違いはデッキが決まらなかったときの最後の砦だけ**。

`--deck` も JSON の `"deck"` もこの既定より強いので、`eng` と打っても行き先を上書きできる。

    uv run ankikit eng words.json          # 行き先が他で決まらなければ english-vocab
"""

from __future__ import annotations

import argparse

from . import word

NAME = "eng"
HELP = "`ankikit word` の別名（既定デッキ english-vocab）"

DEFAULT_DECK = "english-vocab"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    word.add_arguments(parser)
    parser.set_defaults(fallback_deck=DEFAULT_DECK)


def run(args: argparse.Namespace) -> int:
    return word.run(args)
