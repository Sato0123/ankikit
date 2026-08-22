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
    notes/
      2026-08-20-冠詞.md  ← 学びの散文メモ。Anki には送らない
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
## 要点（この単元は何だったか）
## 前提（既に押さえていること）
## カードの作り方
## 運用メモ
## 学習状況          ← ankikit status --write が書き換える
```

`## 要点` は**後から README を開いて「ああこの単元ね」と思い出すための場所**。5〜10 行で単元の骨格を書き、
詳しい話は `notes/` に回す。

`## 前提` は `/anki-initialize` の棚卸しで**即答できた**論点を残す場所。`/anki-grill` がこれを読んで、
同じことを二度と聞かないための基準になる。**ただし前提もカードにはする**（`known:` 付き。下を見よ）。
README に書いてあるだけでは、半年後に忘れたことに気づけない。

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

## Q: table a proposal
A: 提案を棚上げにする（英と米で逆の意味になる）
known: 3
```

| 記法 | 意味 |
|---|---|
| `## ` 行 | カードの開始。行頭の `Q:` は飾りなので取り除かれる |
| `A:` 行 | ここから裏面。次の `## ` か EOF まで（複数行可） |
| `tags:` 行 | そのカード固有のタグ。空白かカンマ区切り |
| `known:` 行 | **既に答えられた**印（1〜4）。新規ではなく復習カードとして入る |
| `<!-- ... -->` | ファイル内のメモ。**Anki には送られない**。カードに残したいなら `A:` の本文に書く |
| `{{c1::...}}` | 表面に含めると穴埋めカードになる |

書式チェックは `uv run ankikit lint`。

## 既習カード（`known:`）

**答えられたことも忘れる。** だから即答できた論点も捨てずにカードにする。ただし新規カードとして入れると、
本当に忘れていたカードと同じ頻度で出てきて復習の枠を食う。`known:` を書くと
**最初から「復習済み」の状態で Anki に入り、指定した日数後に初めて出る**。

| `known:` | 面談での反応 | 初期間隔 |
|---|---|---|
| 1 | 答えられたが説明が詰まった | 2 日後 |
| 2 | 答えられた | 5 日後 |
| 3 | 即答できた | 12 日後 |
| 4 | 体に入っている（保険で置くだけ） | 25 日後 |

- 効くのは **Anki 側でまだ新規のカードだけ**。一度でも復習したカードには二度と触らないので、
  何度 push しても学習履歴は壊れない（後から `known:` を足した場合も、まだ出ていなければ効く）
- Anki 側には `known::<数字>` タグが付くので、「初期化のときに答えられた分」だけ後から絞り込める
- フロントマターに `known: 3` と書くと、そのファイル全体の既定になる（カード側の行が優先）
- **忘れたものには付けない。** 全部に付けると、ただの「出ないカード」の山になる

## 学びのノート（`notes/`）

カードは 1 枚 1 事実なので、**単元としての筋**は残らない。`notes/<YYYY-MM-DD>-<topic>.md` に散文で書く。

```
decks/tcp/notes/2026-08-20-handshake.md
```

`notes/` は Anki には送られない（`push` も `lint` も `cards/` しか読まない）。
`ankikit status --write` が README の学習状況ブロックに索引を張る。

## 学習状況（`ankikit status`）

```
uv run ankikit status <slug>          # 画面に出すだけ
uv run ankikit status <slug> --write  # README の <!-- ankikit:status --> を書き換える
```

ファイル側（枚数・既習の内訳・未マージ・ノート）と Anki 側（新規 / 学習中 / 復習 / 定着 / 今日出る /
忘れ直しが多いカード）をまとめる。**書き換えるのはマーカーの中だけ**なので、手で書いた方針は消えない。

## 重複と更新

同一カードかどうかは**表面のハッシュ**で判定し、Anki 側には `ankikit-uid::<hash>` タグが付く。

- 裏面だけ直して push → 既存カードを**更新**（学習履歴は維持される）
- 表面を直して push → **別カードとして追加**される。古い方は Anki に残るので手で消す
- 同じ表面を 2 回書いた → lint がエラーにする

## 用語カードの近道（`ankikit word`）

**答えが決まっているものは対話を通さない。** 用語・単語に「今日どこで詰まった？」と聞いても
新しいものは出てこないので、JSON を書いて流す。`ankikit word` が **decks/ への追記・コミット・push まで
まとめてやる**（`/anki-grill` の 1.5 節がこれを呼ぶ）。

```
uv run ankikit word terms.json --deck sre   # 検証 → 重複除外 → 追記 → コミット → Anki
uv run ankikit word terms.json --dry-run    # 何が登録され何が弾かれるかだけ見る
uv run ankikit eng words.json               # 別名。既定デッキが english-vocab になるだけ
```

```json
{
  "deck": "sre",
  "tags": ["terms"],
  "words": [
    {"word": "冪等性", "meaning": "同じ操作を何度実行しても結果が変わらない性質"},
    {"word": "anyway", "sentence": "Let's try anyway.", "meaning": "とにかく"}
  ]
}
```

- **`sentence` があれば穴埋め**（例文の該当語が `____` になる。`____` を自分で書いてもよい）
- **無ければ `## <用語> とは？` の問答カード**（`meaning` が裏面になる）
- デッキは `--deck` → JSON の `"deck"` → `anki.toml` の `[word] deck` の順に決まる

承認の原則は形を変えて残っている。`word` は **main 上でしか push しない**ので、
「Anki にあるもの = main にあるもの」は崩れない（`--no-push` なら他のブランチでも書ける）。
**掘って初めて出てくる実践判断のほう**は、これまでどおり面談 → `staging/<slug>` → 承認の道を通す。

重複判定はここだけ**単語**で行い、カードに `word::<単語>` タグが付く。
重複した語は飛ばして残りは登録するので、同じファイルを追記しながら何度流しても問題ない。
このタグがキーなので**消すと二重に入る**。日本語の用語は表記の揺れまでは吸収できない
（`冪等性` と `べき等性` は別の語として 2 枚入る）。

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
| `uv run ankikit status <slug>` | 学習状況のまとめ（`--write` で README に書き戻す） |
| `uv run ankikit lint` | 書式チェック（作業ツリー） |
| `uv run ankikit pending` | まだ main にマージされていないカード |
| `uv run ankikit stage <slug>` | デッキ用の staging ブランチに切り替え |
| `uv run ankikit approve <slug>` | staging を main にマージ（＝承認） |
| `uv run ankikit push --dry-run` | 何が追加・更新されるか確認 |
| `uv run ankikit push --deck <slug>` | 反映（main の内容のみ） |
| `uv run ankikit word <file.json>` | 用語・単語 JSON をカードにして Anki まで反映（承認なし・main 上のみ） |
| `uv run ankikit eng <file.json>` | `word` の別名（既定デッキ english-vocab） |
| `uv run ankikit new <slug>` | デッキの雛形作成 |
| `uv run ankikit doctor` | Anki 接続とノートタイプ名の確認 |

`--ref <branch>` で承認済みとみなすブランチを変えられる。`push --worktree` は承認を無視して作業ツリーを送る非常口。
