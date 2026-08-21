"""サブコマンド 1 つ = モジュール 1 つ。

各モジュールは次の 3 つを持つ:

    NAME                          サブコマンド名
    HELP                          --help に出す 1 行
    add_arguments(parser)         そのコマンド固有の引数
    run(args) -> int              本体。戻り値がそのまま終了コード
    NEEDS_DECKS                   省略時 True。False なら decks/ が無くても走る

**コマンドを足すときは、このディレクトリにファイルを 1 つ作って ALL に並べるだけ。**
"""

from __future__ import annotations

from . import (
    approve,
    change_version,
    decks,
    doctor,
    eng,
    install,
    lint,
    new,
    pending,
    push,
    stage,
    status,
    update,
)

# --help に出る順番でもある。
ALL = [
    decks,
    status,
    lint,
    pending,
    stage,
    approve,
    push,
    eng,
    new,
    install,
    update,
    change_version,
    doctor,
]

__all__ = ["ALL"]
