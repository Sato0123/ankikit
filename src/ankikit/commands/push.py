"""`ankikit push` — 承認済み（= main にマージ済み）のカードを Anki へ反映する。"""

from __future__ import annotations

import argparse

from .. import approval, connect, sync
from ..deck import Deck, load_decks
from . import common

NAME = "push"
HELP = "承認済みのカードを Anki へ反映"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--deck", help="対象デッキの slug（省略時は全デッキ）")
    parser.add_argument("--dry-run", action="store_true", help="送信せず差分だけ表示")
    parser.add_argument("--worktree", action="store_true", help="未承認でも作業ツリーの内容を送る")
    parser.add_argument("--force", action="store_true", help="パースエラーがあっても push する")
    parser.add_argument("-v", "--verbose", action="store_true", help="1 枚ずつ表示")


def run(args: argparse.Namespace) -> int:
    if args.worktree:
        common.warn("--worktree 指定のため未承認のカードも送ります")
        return _push(load_decks(), args, ref_label="作業ツリー")

    # decks_at は一時ディレクトリを使うので、読み込みは with の中で終わらせる。
    with common.approved_decks(args.ref) as merged:
        return _push(merged, args, ref_label=args.ref)


def _push(source: list[Deck], args: argparse.Namespace, ref_label: str) -> int:
    decks = common.select(source, args.deck)
    if decks is None:
        return 1
    if not decks:
        print(f"{ref_label} に承認済みのデッキがありません。カードをコミットして {ref_label} にマージしてください。")
        return 0

    exit_code = 0
    for deck in decks:
        try:
            report = sync.push_deck(deck, dry_run=args.dry_run, force=args.force)
        except connect.AnkiUnavailable as exc:
            common.error(str(exc))
            return 2

        for err in report.errors:
            common.error(str(err))
        if report.errors and not args.force:
            common.error(f"{common.describe(deck)}: パースエラーのため push しません（--force で強行）")
            exit_code = 1
            continue

        exit_code = _report(report, args, ref_label) or exit_code

    if not args.worktree:
        _hint_pending(args.ref)
    return exit_code


def _report(report: sync.DeckReport, args: argparse.Namespace, ref_label: str) -> int:
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}{common.describe(report.deck)} [{ref_label}]: 追加 {report.count('added')}"
        f" / 更新 {report.count('updated')} / 変更なし {report.count('unchanged')}"
        f" / 失敗 {report.count('failed')}"
    )
    exit_code = 0
    for result in report.results:
        if args.verbose and result.action in ("added", "updated"):
            print(f"  {result.action:8} {result.card.front[:50]}")
        if result.action == "failed":
            common.error(f"失敗 {result.card.location()} {result.card.front[:40]}: {result.detail}")
            exit_code = 1
    return exit_code


def _hint_pending(ref: str) -> None:
    """まだマージしていないカードが作業ツリーに残っていたら教える。"""
    if not approval.is_repo():
        return
    try:
        total = sum(len(uids) for uids in common.pending_uids(ref).values())
    except approval.GitError:
        return
    if total:
        print(f"\n未マージのカードが {total} 枚あります（`uv run ankikit pending` で確認）")
