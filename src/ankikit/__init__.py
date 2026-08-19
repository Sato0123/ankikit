"""decks/ 配下の Markdown を Anki に流し込むための小さなツールキット。

    parser  Markdown → Card
    deck    decks/<slug>/ → Deck（README のフロントマターが設定）
    approval  git の main にマージ済み = 承認済み、の判定
    sync    Deck → Anki（片方向）
    connect AnkiConnect の HTTP クライアント
    cli     `ankikit <command>` の配線。中身は commands/
"""

from .deck import Deck, find_deck, load_decks
from .parser import Card, ParseError, parse_file, parse_text

__all__ = [
    "Card",
    "Deck",
    "ParseError",
    "find_deck",
    "load_decks",
    "parse_file",
    "parse_text",
]
