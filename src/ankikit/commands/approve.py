"""`ankikit approve` — staging ブランチを main にマージする ＝ 承認。

マージした時点で `ankikit push` の対象になる。
"""

from __future__ import annotations

import argparse

from .. import approval
from . import common

NAME = "approve"
HELP = "staging ブランチを main にマージする（＝承認）"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug", nargs="?", help="デッキの slug（staging/<slug> をマージ）")
    parser.add_argument("--branch", help="ブランチ名を直接指定")


def run(args: argparse.Namespace) -> int:
    if not common.require_repo():
        return 1
    if not args.slug and not args.branch:
        common.error("slug か --branch のどちらかを指定してください")
        return 1

    branch = args.branch or approval.stage_branch(args.slug)
    if not approval.ref_exists(branch):
        common.error(f"ブランチ '{branch}' がありません")
        return 1
    if approval.dirty_paths():
        common.error("decks/ に未コミットの変更があります。先にコミットしてください。")
        return 1
    if approval.is_merged(branch, args.ref):
        print(f"{branch} は既に {args.ref} にマージ済みです")
        return 0

    original = approval.current_branch()
    try:
        approval.git("switch", args.ref)
        approval.git("merge", "--no-ff", "-m", f"cards: merge {branch}", branch)
    except approval.GitError as exc:
        common.error(f"マージに失敗しました: {exc}")
        common.error(f"（{original} に戻すには `git switch {original}`）")
        return 1

    target = f" --deck {args.slug}" if args.slug else ""
    print(f"{branch} を {args.ref} にマージしました。`uv run ankikit push{target}` で Anki に反映できます。")
    return 0
