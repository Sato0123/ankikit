# ankikit

その日の学習を対話で掘り出して Anki カードにするための道具。**ここは道具側のリポジトリで、カードは入っていない。**

**カードは別のリポジトリにある。** 道具は何度でも配れるが、カードはその人だけのもの。git の履歴は後から
消せないので混ぜない。カード側は `ankikit` を依存として入れ、`uv run ankikit ...` で使う。

| | ここ（public `ankikit`） | カード側（private） |
|---|---|---|
| 中身 | `src/` `tests/` `docs/` `decks/README.md`（記法の仕様） | `decks/<slug>/` `anki.toml` `.claude/skills/` |
| 触る頻度 | たまに（道具を直すとき） | 毎日（振り返り） |

**承認の境界は git のマージ。** `ankikit push` は作業ツリーではなく **main の内容**を読むので、
ブランチ上で書いただけのカードは Anki に入らない。承認 = `staging/<slug>` を main にマージすること。
この判定は `approval.py` にあり、カード側リポジトリの git に対して働く。

## 構成

| パス | 役割 |
|---|---|
| `src/ankikit/` | ライブラリ層（`parser` → `deck` → `sync` → `connect`、承認判定は `approval`） |
| `src/ankikit/config.py` | カードの置き場の決定（`find_repo_root`）とノートタイプ設定 |
| `src/ankikit/vocab.py` | 英単語 JSON の検証・例文の空欄化・重複キー（`ankikit eng` の中身） |
| `src/ankikit/selfupdate.py` | カード側の `pyproject.toml` / `uv` を触って ankikit 自身を入れ替える（`update` / `change-version`） |
| `src/ankikit/commands/` | サブコマンド 1 つ = 1 モジュール。`cli.py` は組み立てるだけ |
| `src/ankikit/skills/` | **スキルの正。** `ankikit install` がここからカード側へ配る |
| `decks/README.md` | カードファイルの記法・既習カード（`known:`）・`notes/`・承認フロー（仕様であって、カードではない） |
| `docs/handbook.html` | 手順書。`build_pages.py` が包んで GitHub Pages へ出る |
| `docs/anki-reference.md` | Anki 本体の設定リファレンス |
| `anki.toml` | 開発とテストで使う既定のノートタイプ設定 |
| `tests/` | pytest。`uv run pytest` |

**サブコマンドを足すときは** `commands/` にファイルを 1 つ作り（`NAME` / `HELP` /
`add_arguments(parser)` / `run(args) -> int`）、`commands/__init__.py` の `ALL` に並べる。`cli.py` は触らない。
`decks/` が無くても走るコマンドには `NEEDS_DECKS = False` を置く（既定は `True`）。

**スキルを直すときは `src/ankikit/skills/` を直す。** カード側の `.claude/skills/` は `ankikit install` が
置いたコピーなので、そこを直しても次の `install --force` で消える。

## コマンド

```bash
uv run ankikit decks              # デッキ一覧・枚数・未マージ枚数
uv run ankikit status <slug>      # 学習状況（--write で README に書き戻す）
uv run ankikit stage <slug>       # staging/<slug> に切り替え
uv run ankikit lint --deck <slug> # カードファイルの書式チェック
uv run ankikit pending            # main に未マージのカード
uv run ankikit approve <slug>     # main へマージ（＝承認）
uv run ankikit push --dry-run     # 差分だけ確認
uv run ankikit push --deck <slug> # 反映（main の内容のみ・Anki 起動が必要）
uv run ankikit eng <file.json>    # 英単語 JSON → カード → コミット → Anki（一気通貫）
uv run ankikit new <slug>         # デッキの雛形作成
uv run ankikit install            # スキルをこのリポジトリに配置（カード側で叩く）
uv run ankikit update             # ankikit 自身を最新にする（カード側で叩く）
uv run ankikit change-version v0.2.0  # バージョンを固定する（latest で固定を外す）
uv run ankikit doctor             # 接続とノートタイプ名の確認
uv run pytest                     # テスト
```

コマンド名は `ankikit`。グローバルの `~/.local/bin/anki` は別ツールなので混同しない。

## カードの置き場をどう決めているか

`config.find_repo_root()` がこの順で探す。

1. 環境変数 `ANKI_REPO_ROOT`
2. **カレントから上へ `anki.toml` か `decks/` を探す**（git が `.git` を探すのと同じ）
3. `src/ankikit/config.py` の 2 つ上（＝このリポジトリで直接動かしているとき）

**2 が本命。** 依存として入れると 3 は site-packages の親という無関係な場所を指す。
見つからないまま走ると「0 件」としか出ず気づけないので、`cli.py` が `decks/` の不在を検出して
どこを見たかを言って止める（`NEEDS_DECKS = False` のコマンドは除く）。

## 英単語デッキ（`english-vocab`）

このデッキだけ対話も承認面談も通さない。JSON を `ankikit eng` に食わせると、検証 → 重複除外 →
`decks/english-vocab/cards/YYYY-MM-DD.md` に追記 → コミット → push まで一気に走る。

- **重複判定は表面ハッシュではなく単語**。カードに付く `word::<単語>` タグがキーで、
  `word_key()` が大小・記号・アクセントを潰す（`Circle Back` = `circle-back`）。**このタグを消すと二重に入る**
- 例文に `____` があればそこが空欄。無ければ `word` を文中から探す（`circle` → `circled` 程度の
  語形変化は追うが、不規則変化は追えないので `____` を手で書く）。見つからなければそのエントリはエラー
- 1 件の不備で全体を止めない。壊れた行と重複だけ落として残りは登録し、終了コードは 1 になる
  （`--strict` で全止め）。致命的（ファイル / JSON 自体が壊れている）だけ 2
- push するのは **main 上のときだけ**。他のブランチでは `--no-push` を要求して、
  「Anki にあるもの = main にあるもの」を保つ

## 道具自身の入れ替え（`update` / `change-version`）

カード側は ankikit を git 依存として固めた時点のまま使う。**道具を直しても向こうは古い。**
`ankikit update` が `uv lock --upgrade-package` → `uv sync` → `uv run ankikit install` を順に叩いて、
パッケージとスキルの両方を新しくする。`change-version <tag|branch|sha|latest>` は取得元のピンを張り替える。

- **最後の `install` は必ず子プロセス（`uv run ankikit install`）で叩く。** 入れ替えた直後の自分自身には
  **古いパッケージが読み込まれたまま**なので、その場で `install.run()` を呼ぶと古いスキルを配ってしまう
- `tag` / `rev` で固定されているときの `update` は**動かずに理由を言って止まる**。黙って固定を外して
  最新へ飛ばす方が危ない。外すのは `change-version latest`
- `uv add` に渡す形は `ankikit @ git+<url>` ＋ `--tag` / `--branch` / `--rev`。
  どれを渡すかは `git ls-remote` の結果で決める（読めなければコミット扱い）
- `path` 参照（開発中の editable）のときは入れ替えるものが無いので、スキルの配り直しだけ走る
- 触るのはカード側の `pyproject.toml` / `uv.lock` / `.claude/skills/` だけ。`decks/` は読まない

## 既習カード（`known:`）と `notes/`

**答えられたことも忘れる。** だから面談で即答できた論点も捨てずにカードにするが、新規カードとして入れると
本当に知らなかったカードと同じ頻度で出て復習の枠を食う。カードに `known: 1〜4` を書くと
`config.KNOWN_INTERVALS` の日数だけ間隔を進めた**復習カード**として入る（`setDueDate` の `<days>!`）。

- 効くのは **Anki 側で type == 0（まだ一度も出ていない）のカードだけ**。`sync._apply_known` がそこで絞るので、
  復習が始まったカードの間隔は何度 push しても書き換わらない。後から `known:` を足した場合も拾える
- Anki 側には `known::<数字>` タグが付く
- `decks/<slug>/notes/*.md` は散文の学びメモ。`Deck.cards_dir` しか読まないので push も lint も無視する
- `ankikit status --write` は README の `<!-- ankikit:status -->` ブロックだけを差し替える。
  Anki 側の内訳は自前で期限計算せず、`is:new` / `prop:ivl>=21` などの**検索クエリの件数**で数える

## 実装上の注意

- `approval.decks_at(ref)` が `git archive` で ref 時点の `decks/` を一時展開する。push はそこを読む。
  **一時ディレクトリなので、カードの読み込みは必ず `with` の中で終わらせる。**
  `--worktree` は承認を無視する非常口で、通常は使わない。
- 同一カード判定は**表面のハッシュ**。Anki 側に `ankikit-uid::<hash>` タグが付く。
  裏面変更 → 更新（履歴維持）、表面変更 → 別カード追加（古い方は残る）。
- ノートタイプ名は Anki の UI 言語や導入経緯で変わる。`config.py` の `DEFAULTS` が既定値で、
  `anki.toml` の `[note_types]` が項目単位で上書きする。合っているかは `ankikit doctor` で確認する。
  この環境の実測値は basic=`基本`[表面/裏面]、cloze=`穴埋め問題`[Text/裏面追記]（doctor で確認済み）。
- フィールドは HTML なので、改行は `to_html()` で `<br>` に変換してから送る。行頭の空白は落とされる。
- `ANKI_CONNECT_URL` で接続先を差し替えられる。

## 手順書（GitHub Pages）

`docs/handbook.html` は doctype も `<html>` も持たない**フラグメント**。Artifact として公開するときは
向こうが骨組みを付けるため。そのまま配信すると quirks モードになるので、Pages に出すときだけ
`docs/build_pages.py` が完全な HTML に包む。main への push で `.github/workflows/pages.yml` が走る。

```bash
python3 docs/build_pages.py _site   # 手元で確認するとき
```
