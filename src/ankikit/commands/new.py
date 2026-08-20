"""`ankikit new` — デッキの雛形（README.md + cards/）を作る。"""

from __future__ import annotations

import argparse

from .. import config
from . import common

NAME = "new"
HELP = "デッキの雛形を作成"
# decks/ 自体をこれから作るので、無くても走らせる。
NEEDS_DECKS = False

# フロントマターが設定、本文が方針。本文は /anki-grill が「何をカードにするか」を
# 判断する材料として読むので、基準は具体的に埋めてもらう。
README_TEMPLATE = """---
anki_deck: "{anki_deck}"
note_type: {note_type}
tags: [{slug}]
---

# {slug}

## 目的
<!-- このデッキで何ができるようになりたいか。1〜2文で。 -->

## 入れる基準
<!-- 例: 実際に詰まった／間違えた事実だけ。調べれば済むリファレンスは入れない。 -->

## 入れない基準
<!-- 例: 一覧・手順の丸暗記、文脈なしの用語、明日には使わない知識。 -->

## 要点（この単元は何だったか）
<!-- 後から README を開いて「ああこの単元ね」と分かる粒度で 5〜10 行。詳しくは notes/ に書く。 -->

## 前提（既に押さえていること）
<!-- 棚卸しで即答できた論点。カードには known: 3〜4 で入れてある（＝忘れたころに出る）。 -->

## カードの作り方
<!-- 表面は「思い出すきっかけ」、裏面は一文＋なぜ。1カード1事実。 -->

## 運用メモ
<!-- 1日の新規枚数の目安、leech の扱い、見直しのタイミングなど。 -->

## 学習状況
<!-- ここは `uv run ankikit status <slug> --write` が書き換える。手で書かない。 -->

<!-- ankikit:status -->
<!-- /ankikit:status -->
"""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug", help="ディレクトリ名（例: english-vocab）")
    parser.add_argument("--anki-deck", help="Anki 上のデッキ名（例: '英語::語彙'）")
    parser.add_argument("--note-type", default="basic", choices=["basic", "cloze"])


def run(args: argparse.Namespace) -> int:
    path = config.DECKS_DIR / args.slug
    if path.exists():
        common.error(f"{path} は既に存在します")
        return 1

    (path / "cards").mkdir(parents=True)
    # 散文の学びメモ。カードではないので push も lint も読まない。
    (path / "notes").mkdir()
    (path / "README.md").write_text(
        README_TEMPLATE.format(
            slug=args.slug,
            anki_deck=args.anki_deck or args.slug,
            note_type=args.note_type,
        ),
        encoding="utf-8",
    )
    print(f"作成しました: {path}/README.md")
    print("README.md の方針を埋めてコミットし、main にマージすると push 対象になります。")
    return 0
