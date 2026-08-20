"""`ankikit status` — デッキの学習状況をまとめる（ファイル側 + Anki 側）。

「このデッキ、何をどこまで覚えているんだったか」を後から思い出すための一覧。
`--write` を付けると各デッキの README.md の
`<!-- ankikit:status -->` ブロックに書き戻すので、README を開けば状況が分かる。

Anki 側の内訳は検索クエリの件数で数える（`is:new` / `prop:ivl>=21` など）。
自前で期限を計算すると、コレクション作成日や時差でずれる。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from dataclasses import dataclass, field

from .. import approval, config, connect
from ..deck import Deck, load_decks
from . import common

NAME = "status"
HELP = "デッキの学習状況（ファイル側 + Anki 側）"

START = "<!-- ankikit:status -->"
END = "<!-- /ankikit:status -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)

# 「定着した」とみなす間隔。Anki の既定の成熟カード（mature）と同じ 21 日。
MATURE_DAYS = 21
# これ以上忘れ直していたら、カードの作りが悪いか前提が抜けている。
LAPSE_THRESHOLD = 3


@dataclass
class Status:
    deck: Deck
    cards: int = 0
    known: dict[int, int] = field(default_factory=dict)
    pending: int = 0
    notes: list[str] = field(default_factory=list)
    anki: dict[str, int] | None = None
    leeches: list[tuple[str, int]] = field(default_factory=list)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("deck", nargs="?", help="対象デッキの slug（省略時は全デッキ）")
    parser.add_argument("--write", action="store_true", help="各デッキの README.md に書き戻す")


def run(args: argparse.Namespace) -> int:
    decks = common.select(load_decks(), args.deck)
    if decks is None:
        return 1
    if not decks:
        print("decks/ にデッキがありません。")
        return 0

    pending: dict[str, set[str]] = {}
    if approval.is_repo():
        try:
            pending = common.pending_uids(args.ref)
        except approval.GitError as exc:
            common.warn(str(exc))

    live = True
    try:
        connect.version()
    except connect.AnkiUnavailable:
        live = False
        common.warn("Anki が起動していないため、ファイル側の集計だけ表示します")

    for deck in decks:
        status = collect(deck, pending=len(pending.get(deck.slug, ())), live=live)
        print(render_text(status))
        if args.write:
            path = write_readme(status)
            print(f"  → {path} に書き戻しました\n" if path else "  → README.md が無いので書けません\n")
    return 0


def collect(deck: Deck, pending: int, live: bool) -> Status:
    cards, _ = deck.load_cards()
    known: dict[int, int] = {}
    for card in cards:
        if card.known:
            known[card.known] = known.get(card.known, 0) + 1

    status = Status(
        deck=deck,
        cards=len(cards),
        known=known,
        pending=pending,
        notes=[p.name for p in deck.note_files()],
    )
    if live:
        try:
            status.anki = _counts(deck)
            status.leeches = _leeches(deck)
        except connect.AnkiConnectError as exc:
            common.warn(f"{deck.slug}: Anki 側を読めませんでした（{exc}）")
    return status


def _scope(deck: Deck) -> str:
    return f'deck:"{deck.anki_deck}" tag:{config.TOOL_TAG}'


def _counts(deck: Deck) -> dict[str, int]:
    scope = _scope(deck)
    queries = {
        "total": "",
        "new": "is:new",
        "learn": "is:learn",
        "young": f"is:review -is:learn prop:ivl<{MATURE_DAYS}",
        "mature": f"is:review prop:ivl>={MATURE_DAYS}",
        "due": "is:due",
        "suspended": "is:suspended",
    }
    return {key: len(connect.find_cards(f"{scope} {q}".strip())) for key, q in queries.items()}


def _leeches(deck: Deck) -> list[tuple[str, int]]:
    """何度も忘れ直しているカード。多いならカードの作りか前提を疑う。"""
    ids = connect.find_cards(f"{_scope(deck)} prop:lapses>={LAPSE_THRESHOLD}")
    found = []
    for info in connect.cards_info(ids[:20]):
        fields = info.get("fields", {})
        front = next((v.get("value", "") for v in fields.values()), "")
        found.append((re.sub(r"<[^>]+>", " ", front).strip()[:40], int(info.get("lapses", 0))))
    return sorted(found, key=lambda pair: -pair[1])[:5]


def render_text(status: Status) -> str:
    lines = [common.describe(status.deck), f"  {_files_line(status)}"]
    if status.anki is None:
        lines.append("  Anki: 未確認")
    else:
        a = status.anki
        lines.append(
            f"  Anki: 合計 {a['total']} / 新規 {a['new']} / 学習中 {a['learn']}"
            f" / 復習 {a['young']} / 定着 {a['mature']} / 今日出る {a['due']}"
        )
    if status.leeches:
        worst = "、".join(f"「{front}」{n}回" for front, n in status.leeches)
        lines.append(f"  忘れ直し {LAPSE_THRESHOLD} 回以上: {worst}")
    if status.notes:
        lines.append(f"  学習ノート {len(status.notes)} 本: " + ", ".join(status.notes[-3:]))
    return "\n".join(lines)


def _files_line(status: Status) -> str:
    bits = [f"カード {status.cards} 枚"]
    if status.known:
        detail = " ".join(f"{lv}:{n}" for lv, n in sorted(status.known.items()))
        bits.append(f"うち既習 {sum(status.known.values())}（{detail}）")
    if status.pending:
        bits.append(f"未マージ {status.pending} 枚")
    return " / ".join(bits)


def render_markdown(status: Status) -> str:
    today = dt.date.today().isoformat()
    lines = [START, "", f"_{today} 時点_ — {_files_line(status)}", ""]
    if status.anki is not None:
        a = status.anki
        lines += [
            "| 状態 | 枚数 |",
            "|---|---|",
            f"| 新規（まだ一度も出ていない） | {a['new']} |",
            f"| 学習中 | {a['learn']} |",
            f"| 復習中（間隔 {MATURE_DAYS} 日未満） | {a['young']} |",
            f"| 定着（間隔 {MATURE_DAYS} 日以上） | {a['mature']} |",
            f"| 今日出る | {a['due']} |",
            "",
        ]
    if status.leeches:
        worst = "、".join(f"`{front}`（{n} 回）" for front, n in status.leeches)
        lines += [f"**忘れ直しが多い**: {worst}", ""]
    if status.notes:
        lines += ["**学習ノート**", ""]
        lines += [f"- [{name}](notes/{name})" for name in status.notes]
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def write_readme(status: Status) -> str | None:
    """README の status ブロックだけ差し替える。手で書いた方針には触らない。"""
    readme = status.deck.readme
    if not readme.is_file():
        return None
    text = readme.read_text(encoding="utf-8")
    block = render_markdown(status)
    if BLOCK_RE.search(text):
        text = BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n## 学習状況\n\n" + block + "\n"
    readme.write_text(text, encoding="utf-8")
    return str(readme)
