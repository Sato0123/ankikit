"""`ankikit update` — カード側で使っている ankikit を最新にする。

道具（このリポジトリ）を直しても、カード側は依存として固めた時点のままなので古い。
このコマンドを**カード側で**叩くと、取得元の最新を取り直してスキルも配り直す。

    uv run ankikit update             # 最新にしてスキルも配り直す
    uv run ankikit update --dry-run   # 何を叩くかだけ見る
    uv run ankikit update --force     # 手で直したスキルも上書きする
    uv run ankikit update --no-install # パッケージだけ入れ替える

バージョンを固定してあるとき（`tag` / `rev`）は最新にしようがないので、
`ankikit change-version latest` を案内して止まる。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import config, selfupdate
from . import common

NAME = "update"
HELP = "ankikit 自身を最新にする（カード側で叩く）"
# 道具の入れ替えなので decks/ は要らない。
NEEDS_DECKS = False


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", type=Path, help="カード側のリポジトリ（既定はカードの置き場）")
    parser.add_argument("--dry-run", action="store_true", help="叩くコマンドを出すだけ")
    parser.add_argument("--force", action="store_true", help="手で直したスキルも上書きする")
    parser.add_argument("--no-install", action="store_true", help="スキルの配り直しをしない")


def run(args: argparse.Namespace) -> int:
    try:
        project = selfupdate.find_project(args.target or config.REPO_ROOT)
        source = selfupdate.read_source(project)
        print(f"対象: {project}")
        print(f"いまの取得元: {source.describe()}")

        if source.kind == "path":
            # editable な path 参照は直したそばから反映されるので、入れ替えるものが無い。
            print("path 参照なので入れ替えは要りません。")
        elif source.pinned:
            common.error(
                f"{source.pin_kind}={source.pin} に固定されているので update では動きません。"
            )
            print("最新に戻すなら: uv run ankikit change-version latest", flush=True)
            return 1
        else:
            before = selfupdate.locked_commit(project)
            selfupdate.run_uv(
                project, ["lock", "--upgrade-package", selfupdate.PACKAGE], dry_run=args.dry_run
            )
            selfupdate.run_uv(project, ["sync"], dry_run=args.dry_run)
            if not args.dry_run:
                selfupdate.report_move(before, selfupdate.locked_commit(project))

        if not args.no_install:
            selfupdate.reinstall_skills(project, force=args.force, dry_run=args.dry_run)
    except selfupdate.UpdateError as exc:
        common.error(str(exc))
        return 2
    return 0
