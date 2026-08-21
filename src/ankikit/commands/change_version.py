"""`ankikit change-version` — カード側が使う ankikit のバージョンを差し替える。

タグ・ブランチ・コミットのどれでも渡せる。`latest` を渡すと固定をやめて既定ブランチに追従する
（＝`ankikit update` で最新を追える状態に戻る）。

    uv run ankikit change-version --list      # 取得元にあるタグとブランチを見る
    uv run ankikit change-version v0.2.0      # そのタグに固定する
    uv run ankikit change-version 3e3a566     # そのコミットに固定する
    uv run ankikit change-version latest      # 固定をやめて最新に追従する

**固定した状態で `ankikit update` は動かない**（動かせないものを黙って動かさないため）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import config, selfupdate
from . import common

NAME = "change-version"
HELP = "ankikit のバージョンを指定して入れ替える（カード側で叩く）"
# 道具の入れ替えなので decks/ は要らない。
NEEDS_DECKS = False


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "version",
        nargs="?",
        help=f"タグ / ブランチ / コミット、または {selfupdate.LATEST[0]}（固定をやめる）",
    )
    parser.add_argument("--list", action="store_true", help="取得元にあるタグとブランチを出す")
    parser.add_argument("--target", type=Path, help="カード側のリポジトリ（既定はカードの置き場）")
    parser.add_argument("--dry-run", action="store_true", help="叩くコマンドを出すだけ")
    parser.add_argument("--force", action="store_true", help="手で直したスキルも上書きする")
    parser.add_argument("--no-install", action="store_true", help="スキルの配り直しをしない")


def run(args: argparse.Namespace) -> int:
    try:
        project = selfupdate.find_project(args.target or config.REPO_ROOT)
        source = selfupdate.read_source(project)
        url = selfupdate.git_url(project)

        if args.list:
            return _list(url, source)
        if not args.version:
            common.error("バージョンを指定してください（一覧は --list）")
            return 1
        if source.kind == "path":
            common.error(f"path 参照（{source.url}）なのでバージョンを選べません。")
            print("git から取るように戻すなら: uv run ankikit change-version latest")
            return 1

        print(f"対象: {project}")
        print(f"いまの取得元: {source.describe()}")

        before = selfupdate.locked_commit(project)
        # uv 0.11 の `uv add` は要件そのものに git+ を書き、ピンは --tag / --rev / --branch で渡す。
        add = ["add", f"{selfupdate.PACKAGE} @ git+{url}"]
        if args.version in selfupdate.LATEST:
            # ピンを外すだけでは古いコミットに解決したままなので、明示的に取り直す。
            selfupdate.run_uv(project, add, dry_run=args.dry_run)
            selfupdate.run_uv(
                project, ["lock", "--upgrade-package", selfupdate.PACKAGE], dry_run=args.dry_run
            )
            selfupdate.run_uv(project, ["sync"], dry_run=args.dry_run)
        else:
            tags, branches = selfupdate.remote_refs(url)
            option = selfupdate.pin_option(args.version, tags, branches)
            selfupdate.run_uv(project, [*add, option, args.version], dry_run=args.dry_run)

        if not args.dry_run:
            print(f"いまの取得元: {selfupdate.read_source(project).describe()}")
            selfupdate.report_move(before, selfupdate.locked_commit(project))

        if not args.no_install:
            selfupdate.reinstall_skills(project, force=args.force, dry_run=args.dry_run)
    except selfupdate.UpdateError as exc:
        common.error(str(exc))
        return 2
    return 0


def _list(url: str, source: selfupdate.Source) -> int:
    tags, branches = selfupdate.remote_refs(url)
    print(f"取得元: {url}")
    print(f"いまの指定: {source.describe()}")
    if not tags and not branches:
        common.warn("取得元を読めませんでした（ネットワークか URL を確認してください）")
        return 1
    print(f"  タグ: {', '.join(tags) if tags else '(なし)'}")
    print(f"  ブランチ: {', '.join(branches) if branches else '(なし)'}")
    print("コミットのハッシュもそのまま渡せます。")
    return 0
