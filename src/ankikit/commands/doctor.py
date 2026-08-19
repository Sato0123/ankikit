"""`ankikit doctor` — Anki 接続と anki.toml のノートタイプ設定が合っているか確認する。"""

from __future__ import annotations

import argparse

from .. import config, connect
from ..deck import load_decks
from . import common

NAME = "doctor"
HELP = "Anki 接続とノートタイプ設定を確認"
# Anki との接続を見るだけなので decks/ は要らない。
NEEDS_DECKS = False


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    print(f"AnkiConnect: {config.ANKI_CONNECT_URL}")
    try:
        print(f"  バージョン: {connect.version()}")
    except connect.AnkiUnavailable as exc:
        common.error(str(exc))
        return 2

    ok = _check_note_types()
    _list_decks()
    return 0 if ok else 1


def _check_note_types() -> bool:
    models = set(connect.model_names())
    ok = True
    print(f"ノートタイプ設定（{config.CONFIG_FILE.name}）:")

    for kind, spec in config.note_types().items():
        if spec.model not in models:
            ok = False
            print(f"  NG {kind}: ノートタイプ '{spec.model}' が Anki にありません")
            print(f"     Anki 側の候補: {', '.join(sorted(models))}")
            continue
        fields = connect.model_field_names(spec.model)
        missing = [f for f in (spec.front, spec.back) if f not in fields]
        if missing:
            ok = False
            print(f"  NG {kind}: '{spec.model}' にフィールド {missing} がありません（実際: {fields}）")
        else:
            print(f"  OK {kind}: {spec.model} [{spec.front} / {spec.back}]")

    if not ok:
        print(f"\n{config.CONFIG_FILE} を実際の名前に合わせてください。例:")
        print('  [note_types.cloze]\n  model = "穴埋め"\n  front = "本文"\n  back  = "追加情報"')
    return ok


def _list_decks() -> None:
    live = set(connect.deck_names())
    for deck in load_decks():
        status = "有" if deck.anki_deck in live else "未作成（push 時に自動作成）"
        print(f"デッキ {common.describe(deck)}: {status}")
