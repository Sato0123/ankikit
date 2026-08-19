"""`ankikit stage` — デッキ用の作業ブランチ staging/<slug> に切り替える。

ここで書いたカードは、`ankikit approve` で main にマージするまで Anki に入らない。
"""

from __future__ import annotations

import argparse

from .. import approval
from ..deck import find_deck, load_decks
from . import common

NAME = "stage"
HELP = "デッキ用の staging ブランチに切り替える"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug", help="デッキの slug")


def run(args: argparse.Namespace) -> int:
    if not common.require_repo():
        return 1
    if find_deck(args.slug) is None:
        available = ", ".join(d.slug for d in load_decks()) or "(なし)"
        common.error(f"デッキ '{args.slug}' が見つかりません。利用可能: {available}")
        return 1

    branch = approval.stage_branch(args.slug)
    dirty = approval.dirty_paths()
    if dirty:
        print(f"注意: decks/ に未コミットの変更があります: {', '.join(dirty)}")

    if not approval.git("branch", "--list", branch):
        approval.git("switch", "-c", branch, args.ref)
        print(f"{branch} を {args.ref} から作成して切り替えました")
        return 0

    approval.git("switch", branch)
    try:
        approval.git("merge", "--ff-only", args.ref)
    except approval.GitError:
        print(f"{branch} に切り替えました（{args.ref} を早送りできないので手で整理してください）")
        return 0

    ahead = approval.git("rev-list", "--count", f"{args.ref}..{branch}")
    note = f"（{args.ref} より {ahead} コミット先行 = 未承認）" if ahead != "0" else ""
    print(f"{branch} に切り替えました{note}")
    return 0
