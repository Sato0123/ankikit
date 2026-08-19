"""`uv run ankikit <command>` のエントリポイント。

ここは argparse の配線とエラーの受け止めだけ。各コマンドの中身は commands/ にある。
"""

from __future__ import annotations

import argparse
import sys

from . import approval, commands, config, connect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ankikit",
        description="decks/ の Markdown を Anki に反映する",
    )
    parser.add_argument(
        "--ref",
        default=approval.APPROVED_REF,
        help=f"承認済みとみなす git リファレンス（既定 {approval.APPROVED_REF}）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for module in commands.ALL:
        child = sub.add_parser(module.NAME, help=module.HELP, description=module.__doc__)
        module.add_arguments(child)
        child.set_defaults(run=module.run, needs_decks=getattr(module, "NEEDS_DECKS", True))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # decks/ が見つからないまま走ると「0 件」としか出ず、場所を間違えたことに気づけない。
    # 黙って 0 件で終わらせず、どこを見たのかを言う。
    if args.needs_decks and not config.DECKS_DIR.is_dir():
        print(f"ERROR decks/ が見つかりません（{config.root_hint()}）", file=sys.stderr)
        print(
            "カードのあるリポジトリで実行するか、ANKI_REPO_ROOT でその場所を指してください。",
            file=sys.stderr,
        )
        return 2

    try:
        return args.run(args)
    except (approval.GitError, connect.AnkiConnectError, config.ConfigError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
