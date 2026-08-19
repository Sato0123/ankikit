# decks/

デッキ 1 つ = ディレクトリ 1 つ。ここが**カードの正**で、Anki には片方向に流し込む。
Anki 側で直接編集した内容はここには戻ってこないので、直したいときはこのファイルを直して push し直す。

**push されるのは main にマージ済みのカードだけ。** ブランチ上で書いただけのカードは Anki に入らない
（`uv run ankikit push` は作業ツリーではなく main の内容を読む）。マージが承認そのもの。

```
decks/
  english-vocab/
    README.md            ← このデッキの方針（フロントマターが設定になる）
    cards/
      2026-08-20.md      ← その日に足したカード
      2026-08-21.md
```

## デッキ README.md

フロントマターが設定、本文が方針。方針の本文は `/anki-grill` が読んで「何をカードにするか」を判断する材料になるので、
**入れる基準と入れない基準は具体的に**書く。

```markdown
---
anki_deck: "英語::語彙"   # Anki 上の実デッキ名。`::` で階層。省略時はディレクトリ名
note_type: basic          # basic | cloze（カード側に {{c1::}} があれば自動で cloze）
tags: [english]           # このデッキの全カードに付くタグ
---

## 目的
## 入れる基準
## 入れない基準
## 前提（既に押さえていること）
## カードの作り方
## 運用メモ
```

`## 前提` は `/anki-initialize` の棚卸しで**即答できた**論点を残す場所。`/anki-grill` がこれを読んで、
既に押さえていることを二度と聞かない・カードにしないための基準になる。

雛形は `uv run ankikit new <slug> --anki-deck "英語::語彙"` で作れるが、**新しいデッキは `/anki-initialize`
から始めるのが本筋**（方針と最初の 10〜20 枚をまとめて作る）。

## カードファイル（cards/YYYY-MM-DD.md）

```markdown
---
tags: [meeting]          # このファイル内の全カードに付くタグ（省略可）
---

## Q: circle back
A: 後で改めて議論する
<!-- 出典: 今日のMTGで上司が使った -->

## {{c1::defer}} to someone
A: 人の判断に従う / 一任する
tags: nuance
```

| 記法 | 意味 |
|---|---|
| `## ` 行 | カードの開始。行頭の `Q:` は飾りなので取り除かれる |
| `A:` 行 | ここから裏面。次の `## ` か EOF まで（複数行可） |
| `tags:` 行 | そのカード固有のタグ。空白かカンマ区切り |
| `<!-- ... -->` | ファイル内のメモ。**Anki には送られない**。カードに残したいなら `A:` の本文に書く |
| `{{c1::...}}` | 表面に含めると穴埋めカードになる |

書式チェックは `uv run ankikit lint`。

## 重複と更新

同一カードかどうかは**表面のハッシュ**で判定し、Anki 側には `ankikit-uid::<hash>` タグが付く。

- 裏面だけ直して push → 既存カードを**更新**（学習履歴は維持される）
- 表面を直して push → **別カードとして追加**される。古い方は Anki に残るので手で消す
- 同じ表面を 2 回書いた → lint がエラーにする

## 英単語デッキだけの近道

`english-vocab` は対話ではなく JSON から作る。手で打ち込んだデータに承認面談は要らないので、
`ankikit eng` が **decks/ への追記・コミット・push までまとめてやる**。

```
uv run ankikit eng words.json            # 検証 → 重複除外 → 追記 → コミット → Anki
uv run ankikit eng words.json --dry-run  # 何が登録され何が弾かれるかだけ見る
```

承認の原則は形を変えて残っている。`eng` は **main 上でしか push しない**ので、
「Anki にあるもの = main にあるもの」は崩れない（`--no-push` なら他のブランチでも書ける）。

重複判定はこのデッキだけ**単語**で行い、カードに `word::<単語>` タグが付く。
重複した語は飛ばして残りは登録するので、同じファイルを追記しながら何度流しても問題ない。
入力の書式は [`english-vocab/README.md`](english-vocab/README.md)。

## 承認フロー

```
uv run ankikit stage <slug>        # staging/<slug> に切り替え（無ければ main から作る）
#   → decks/<slug>/cards/YYYY-MM-DD.md を書く
uv run ankikit lint --deck <slug>  # 書式チェック
git add decks/<slug> && git commit -m "cards(<slug>): YYYY-MM-DD N枚"
git diff main...HEAD -- decks/     # 承認前の確認
uv run ankikit approve <slug>      # main へ --no-ff マージ ＝ 承認
uv run ankikit push --deck <slug>  # ここで初めて Anki に入る
```

未マージのカードは `uv run ankikit pending` で確認できる。

## コマンド

| コマンド | 用途 |
|---|---|
| `uv run ankikit decks` | デッキ一覧・枚数・未マージ枚数 |
| `uv run ankikit lint` | 書式チェック（作業ツリー） |
| `uv run ankikit pending` | まだ main にマージされていないカード |
| `uv run ankikit stage <slug>` | デッキ用の staging ブランチに切り替え |
| `uv run ankikit approve <slug>` | staging を main にマージ（＝承認） |
| `uv run ankikit push --dry-run` | 何が追加・更新されるか確認 |
| `uv run ankikit push --deck <slug>` | 反映（main の内容のみ） |
| `uv run ankikit eng <file.json>` | 英単語 JSON をカードにして Anki まで反映 |
| `uv run ankikit new <slug>` | デッキの雛形作成 |
| `uv run ankikit doctor` | Anki 接続とノートタイプ名の確認 |

`--ref <branch>` で承認済みとみなすブランチを変えられる。`push --worktree` は承認を無視して作業ツリーを送る非常口。
