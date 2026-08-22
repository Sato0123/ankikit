# ankikit

学習した日の終わりに、対話で振り返って Anki カードを作るための道具。

**カードは Markdown で書き、main にマージされたものだけが Anki に入る。** 承認の境界は git のマージそのもの。

📖 **[手順書（ハンドブック）](https://sato0123.github.io/ankikit/)** — 記法・承認フロー・コマンドの全部

```
/anki-initialize            ← 新しいデッキを始めるとき（1 デッキにつき 1 回）
  ├─ スコープと方針を決める   目的・入れる基準・入れない基準
  ├─ 棚卸し面談              口頭でテストし、答えられなかったものだけ拾う
  └─ 初期カード 10〜20 枚 → 承認 → push

/anki-grill                 ← 学習した日の終わりに毎回
  ├─ 1. デッキの特定        今日はどのデッキの話か決める（無ければ /anki-initialize へ）
  ├─ 1.5 今日の用語リスト    出てきた用語を貼るだけ → ankikit word が main に直接入れる
  ├─ 2. 振り返り            そのデッキの方針に沿って問い詰める（掘るのは実践判断だけ）
  ├─ 3. カード候補          5〜10 枚を提案
  ├─ 4. staging/<deck>      ブランチを切って decks/ に書き、コミット
  ├─ 5. 承認 = main へマージ ここまで Anki には何も入らない
  └─ 6. push                main の内容だけが Anki に入る → AnkiWeb → スマホ
```

**用語と実践判断では作り方が違う。** 用語には決まった答えがあるので問い詰めても何も出てこない。
だから 1.5 で**貼るだけ**にして承認も飛ばし、面談は「この状況でどう動くか」だけに使う。

手で書きたいときは `decks/<slug>/cards/YYYY-MM-DD.md` に直接足して、同じくマージしてから `uv run ankikit push`。

### 用語・単語は対話を通さない（`ankikit word`）

決まった答えがあるものは JSON で一気に流し込む。承認（ブランチ → main のマージ）は飛ばし、
代わりに **main 上でしか push しない**ことで「Anki にあるもの = main にあるもの」を保つ。

```
uv run ankikit word terms.json --deck sre   ← 検証 → 重複除外 → decks/ に追記 → コミット → Anki 反映
uv run ankikit eng words.json               ← 別名。既定デッキが english-vocab になるだけ
```

```json
[
  {"word": "anyway", "sentence": "Let's try anyway.", "meaning": "とにかく"},
  {"word": "冪等性", "meaning": "同じ操作を何度実行しても結果が変わらない性質"}
]
```

- `sentence` があれば例文の該当語が自動で `____` になる（表面 `Let's try ____.` / 裏面 `anyway`）
- 無ければ `## 冪等性 とは？` の問答カードになる
- 重複は**単語**で判定して、ぶつかった語だけ飛ばす。書式は [`decks/README.md`](decks/README.md)

デッキは `--deck` → JSON の `"deck"` → `anki.toml` の `[word] deck` の順に決まる。

## リポジトリは 2 つに分かれている

道具は何度でも配れるが、カードはその人だけのもの。git の履歴は後から消せないので混ぜない。

| | このリポジトリ（public） | カード側（手元の private） |
|---|---|---|
| 中身 | `src/` `tests/` `docs/` `decks/README.md`（記法の仕様） | `decks/<slug>/` `anki.toml` `.claude/skills/` |
| 触る頻度 | たまに（道具を直すとき） | 毎日（振り返り） |

## 使い始める

1. PC 版 Anki に [AnkiConnect](https://ankiweb.net/shared/info/2055492159) アドオンを入れる
2. カード用のリポジトリを作って、この道具を依存として入れる

   ```bash
   mkdir ~/anki-decks && cd ~/anki-decks
   git init
   uv init --bare
   uv add "ankikit @ git+https://github.com/Sato0123/ankikit"
   ```

3. スキルを配置する（`/anki-grill` と `/anki-initialize` が使えるようになる）

   ```bash
   uv run ankikit install
   ```

4. `uv run ankikit doctor` で接続とノートタイプ名を確認
5. `/anki-initialize` でデッキを立ち上げる（方針と最初のカードまで作る）

カード側では `uv run ankikit ...` がそのまま動く。`config.find_repo_root()` がカレントから上へ
`anki.toml` / `decks/` を探すので、環境変数は要らない。

## 道具を新しくする

カード側は依存として固めた時点の ankikit を使っているので、この道具を直しても向こうは古いまま。
**カード側で** `update` を叩くと、パッケージの取り直しとスキルの配り直しが一度に走る。

```bash
uv run ankikit update                 # 最新にする（スキルも配り直す）
uv run ankikit update --dry-run       # 何を叩くかだけ見る
uv run ankikit change-version --list  # 選べるタグとブランチ
uv run ankikit change-version v0.2.0  # そのバージョンに固定する
uv run ankikit change-version latest  # 固定をやめて最新に追従する
```

固定している間は `update` が動かない（黙って固定を外さないため）。戻すのは `change-version latest`。

## この道具を直すとき

```
src/ankikit/           parser → deck → sync → connect、承認判定は approval
src/ankikit/vocab.py   用語・単語 JSON の検証と空欄化（ankikit word の中身）
src/ankikit/selfupdate.py  カード側の pyproject/uv を触って自分自身を入れ替える
src/ankikit/commands/  サブコマンド 1 つ = ファイル 1 つ
src/ankikit/skills/    スキルの正（ankikit install が配る）
docs/handbook.html     手順書。main に push すると GitHub Pages に出る
anki.toml              開発とテストで使う既定のノートタイプ設定
tests/                 uv run pytest
```

サブコマンドを足すなら `src/ankikit/commands/` にファイルを 1 つ作って
`commands/__init__.py` の `ALL` に並べるだけ。`cli.py` は触らなくていい。

詳しい記法・承認フロー・コマンドは [`decks/README.md`](decks/README.md)。
Anki 本体の設定については [`docs/anki-reference.md`](docs/anki-reference.md)。
