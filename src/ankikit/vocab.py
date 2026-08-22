"""用語・単語の JSON（`ankikit word` の入力）を読んで、カードの材料に変換する。

手で打ち込む / 会話から書き起こすことを前提にした形式なので、**壊れた入力でも直せる情報を返す**のが
このモジュールの仕事。致命的な問題（ファイルが読めない・JSON として壊れている）だけ例外にして、
1 件ごとの不備は `Issue` に貯めて残りは通す。

入力（配列だけでも、設定つきのオブジェクトでも受ける）:

    [
      {"word": "anyway", "sentence": "Let's try anyway.", "meaning": "とにかく"},
      {"word": "circle back", "sentence": "She ____ back to me later.", "note": "p.42"},
      {"word": "冪等性", "meaning": "同じ操作を何度実行しても結果が変わらない性質"}
    ]

    {
      "deck": "english-vocab",
      "tags": ["duo3"],
      "words": [ ... ]
    }

**カードの形は `sentence` があるかで決まる。**

- あり（穴埋め）: `sentence` に `____`（アンダースコア 3 つ以上）があればそこが空欄。無ければ `word` を
  文中から探して空欄にする（`circle` → `circled` のような素直な語形変化までは追う）。
  見つからなければそのエントリはエラーにする。答えが表面に出たカードは無価値なため。
- なし（Q/A）: `## <用語> とは？` / `A: <meaning>` の素の問答にする。概念や日本語の用語は
  例文に埋めても想起のきっかけにならないので、`meaning` があれば例文は要らない。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

BLANK = "____"
BLANK_RE = re.compile(r"_{3,}")
# 語境界。\b だとアポストロフィまわりが素直でないので英数字だけで見る。
BOUNDARY_L = r"(?<![A-Za-z0-9])"
BOUNDARY_R = r"(?![A-Za-z0-9])"

# 手打ちの揺れを吸収する。左が正、右が受け付ける別名。
ALIASES: dict[str, str] = {
    "word": "word", "単語": "word", "語": "word",
    "sentence": "sentence", "例文": "sentence", "example": "sentence", "文": "sentence",
    "meaning": "meaning", "意味": "meaning", "訳": "meaning", "translation": "meaning",
    "note": "note", "メモ": "note", "備考": "note", "出典": "note",
}
ENTRY_KEYS = ("word", "sentence", "meaning", "note")
# 例文が無いときの表面。用語カードは「その語が何を指すか」だけを聞く。
QUESTION = "{word} とは？"
LIST_KEYS = ("words", "entries", "cards", "単語", "リスト")

# JSON を手打ちしたときに踏みやすい地雷。読めなかったときのヒントに使う。
SMART_CHARS = "“”‘’，、。：；　"


class VocabError(RuntimeError):
    """入力そのものが読めない（＝1 枚も作れない）致命的な問題。"""


@dataclass
class Issue:
    """1 エントリ単位の不備。level が error/skip なら、そのエントリは採用されない。"""

    level: str  # error（入力の不備）/ skip（重複）/ warn（採用はするが注意）
    message: str
    index: int | None = None
    word: str = ""

    def __str__(self) -> str:
        where = f"[{self.index}]" if self.index else "[-]"
        word = f" {self.word}:" if self.word else ""
        return f"{where}{word} {self.message}"


@dataclass
class Entry:
    """カード 1 枚分。front/back は組み立て済みで、あとは Markdown にするだけ。"""

    word: str
    front: str  # 空欄化した例文（Q/A なら「<用語> とは？」）
    sentence: str  # 空欄を埋め戻した完全な例文（Q/A では空）
    meaning: str = ""
    note: str = ""
    index: int = 0
    kind: str = "blank"  # blank（例文の穴埋め）/ qa（用語 → 意味）

    @property
    def key(self) -> str:
        return word_key(self.word)

    @property
    def tag(self) -> str:
        return f"word::{self.key}"


@dataclass
class Loaded:
    entries: list[Entry] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    deck: str | None = None
    tags: list[str] = field(default_factory=list)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level in ("error", "skip")]


# --------------------------------------------------------------------------- 語の正規化


def word_key(word: str) -> str:
    """重複判定に使うキー。大小・記号・アクセントの揺れを潰す。

    `Circle Back` も `circle-back` も同じ `circle-back` になる。

    **ラテン文字だけでできた語の結果は変えない。** このキーはそのまま `word::<key>` タグになって
    Anki 側に残っているので、正規化を変えると既存カード（`english-vocab`）とキーがずれて重複が流れ込む。

    ラテン文字以外を含む語（`冪等性`）は、以前は英数字が 1 つも残らずハッシュ（`x-3f2a1b9c`）に
    落ちていた。完全一致の重複は防げていたが、タグが読めない。そこだけ文字を落とさずに残す
    （`word::冪等性`）。**表記の揺れまでは吸収できない**ので `冪等性` と `べき等性` は別の語になる。
    記号だけの語は行き場が無いので従来どおりハッシュ。
    """
    text = unicodedata.normalize("NFKD", word).strip().lower()
    text = "".join(c for c in text if not unicodedata.combining(c))
    if text.isascii():
        key = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        if key:
            return key

    # タグに使うので、空白と記号（`::` を作る `:` を含む）は残せない。文字だけ拾って `-` で繋ぐ。
    folded = unicodedata.normalize("NFKC", word).strip().lower()
    joined = "".join(c if c.isalnum() or c == "_" else "-" for c in folded)
    key = re.sub(r"-+", "-", joined).strip("-")
    return key or "x-" + hashlib.sha1(word.strip().lower().encode("utf-8")).hexdigest()[:8]


def _forms(word: str) -> list[str]:
    """例文中で探す語形。先頭語だけを変化させる（`circle back` → `circled back`）。

    **効くのは英語（ASCII）の語だけ。** 規則はすべて英語の綴りのものなので、日本語などの語には
    当てない（当ててもゴミの語形が増えるだけで、当たることは無い）。他言語で例文を空欄にしたい
    ときは、例文側に `____` を書く。
    """
    tokens = word.split()
    if not tokens:
        return []
    head, rest = tokens[0], tokens[1:]
    if not head.isascii():
        return [word]
    low = head.lower()

    forms = [head]
    if low.endswith("y") and len(head) > 2 and low[-2] not in "aeiou":
        forms += [head[:-1] + "ies", head[:-1] + "ied"]
    if low.endswith("e") and len(head) > 2:
        forms.append(head[:-1] + "ing")
    forms += [head + "s", head + "es", head + "ed", head + "d", head + "ing"]
    # stop → stopped / stopping。短母音 + 子音で終わる語だけ。
    if len(head) > 2 and low[-1] not in "aeiouwxy" and low[-2] in "aeiou" and low[-3] not in "aeiou":
        forms += [head + head[-1] + "ed", head + head[-1] + "ing"]

    ordered = list(dict.fromkeys(forms))
    return [" ".join([f, *rest]) for f in ordered]


def _form_re(form: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(t) for t in form.split())
    return re.compile(BOUNDARY_L + body + BOUNDARY_R, re.IGNORECASE)


@dataclass
class Blanked:
    front: str
    surface: str  # 実際に空欄にした表記
    explicit: bool  # 入力側で ____ が書かれていたか


def blank_out(sentence: str, word: str) -> Blanked | None:
    """例文の該当箇所を `____` に置き換える。見つからなければ None。"""
    if BLANK_RE.search(sentence):
        return Blanked(front=BLANK_RE.sub(BLANK, sentence), surface=word, explicit=True)

    for form in _forms(word):
        pattern = _form_re(form)
        match = pattern.search(sentence)
        if match:
            return Blanked(front=pattern.sub(BLANK, sentence), surface=match.group(0), explicit=False)
    return None


def leaks(front: str, word: str) -> bool:
    """空欄化したはずの表面に、まだ答えが残っていないか。"""
    return any(_form_re(form).search(front) for form in _forms(word))


# --------------------------------------------------------------------------- JSON の読み込み


def _oneline(text: str) -> str:
    """カード記法を壊さないよう 1 行に潰す。

    Markdown を経由するので、改行が入ると `## ` や `A:` の解釈がずれる。HTML コメントも
    parser に食われて消えるため無害化しておく。
    """
    flat = " ".join(str(text).split())
    return flat.replace("<!--", "&lt;!--").replace("-->", "--&gt;")


def _json_hint(text: str, exc: json.JSONDecodeError) -> str:
    """手打ち JSON でよくある壊れ方に見当をつける。"""
    hints: list[str] = []
    if "Expecting ',' delimiter" in exc.msg:
        hints.append("直前の行末にカンマが足りない可能性があります")
    if "trailing comma" in exc.msg or "Expecting property name" in exc.msg:
        hints.append("最後の要素の後ろに余分なカンマがあるか、キーが \" で囲まれていません")
    if "Expecting value" in exc.msg:
        hints.append("値が空か、カンマが余分に入っています")
    if any(c in text for c in SMART_CHARS):
        found = "".join(sorted({c for c in SMART_CHARS if c in text}))
        hints.append(f"全角の記号（{found}）が混ざっています。JSON の構造記号は半角にしてください")
    if "'" in text and '"' not in text.split("\n")[max(exc.lineno - 1, 0)]:
        hints.append("文字列は ' ではなく \" で囲みます")
    return "\n".join(f"  ヒント: {h}" for h in hints)


def _decode(text: str, path: Path) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        lines = text.splitlines()
        excerpt = lines[exc.lineno - 1] if 0 < exc.lineno <= len(lines) else ""
        caret = " " * max(exc.colno - 1, 0) + "^"
        detail = f"{path}:{exc.lineno}:{exc.colno}: JSON として読めません: {exc.msg}"
        if excerpt:
            detail += f"\n  {excerpt}\n  {caret}"
        hint = _json_hint(text, exc)
        raise VocabError(detail + ("\n" + hint if hint else "")) from exc


def _normalize_entry(raw: dict, index: int, issues: list[Issue]) -> dict[str, str]:
    """キーの別名を解決し、値を文字列に揃える。未知のキーは警告にとどめる。"""
    fields: dict[str, str] = {}
    for key, value in raw.items():
        canonical = ALIASES.get(str(key).strip().lower()) or ALIASES.get(str(key).strip())
        if canonical is None:
            issues.append(Issue("warn", f"知らないキー '{key}' は無視しました（使えるキー: {', '.join(ENTRY_KEYS)}）", index))
            continue
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            issues.append(Issue("error", f"'{canonical}' は文字列で書いてください（{type(value).__name__} が来ています）", index))
            continue
        if canonical in fields:
            issues.append(Issue("warn", f"'{canonical}' が重複しています。後ろの値を使います", index))
        fields[canonical] = _oneline(value)
    return fields


def _build(raw: object, index: int, issues: list[Issue]) -> Entry | None:
    if not isinstance(raw, dict):
        issues.append(Issue("error", f"エントリはオブジェクト {{...}} で書いてください（{type(raw).__name__} が来ています）", index))
        return None

    fields = _normalize_entry(raw, index, issues)
    word = fields.get("word", "")
    sentence = fields.get("sentence", "")
    label = word or sentence[:20]

    if not word:
        issues.append(Issue("error", "word が空です", index, label))
        return None

    # 例文が無ければ Q/A カード。意味まで無いと裏面が空になるので、そこだけは要る。
    if not sentence:
        if not fields.get("meaning"):
            issues.append(
                Issue(
                    "error",
                    "sentence（例文）か meaning（意味）のどちらかは要ります。"
                    "例文があれば穴埋め、無ければ「<用語> とは？」の問答になります",
                    index,
                    label,
                )
            )
            return None
        return Entry(
            word=word,
            front=QUESTION.format(word=word),
            sentence="",
            meaning=fields["meaning"],
            note=fields.get("note", ""),
            index=index,
            kind="qa",
        )

    blanked = blank_out(sentence, word)
    if blanked is None:
        issues.append(
            Issue(
                "error",
                f"例文に '{word}' が見つからないので空欄にできません。"
                f"例文側に ____ を書くか、実際の語形を word に書いてください（例文: {sentence[:40]}）",
                index,
                label,
            )
        )
        return None
    if blanked.explicit and leaks(blanked.front, word):
        issues.append(Issue("warn", "空欄の外にも答えが残っています。表面に答えが見えます", index, label))

    return Entry(
        word=word,
        front=blanked.front,
        sentence=blanked.front.replace(BLANK, blanked.surface),
        meaning=fields.get("meaning", ""),
        note=fields.get("note", ""),
        index=index,
    )


def load_text(text: str, path: Path | None = None) -> Loaded:
    path = path or Path("<inline>")
    data = _decode(text.lstrip("﻿"), path)

    result = Loaded()
    if isinstance(data, dict):
        for key in LIST_KEYS:
            if key in data:
                items = data[key]
                break
        else:
            raise VocabError(
                f"{path}: 単語の配列が見つかりません。トップレベルを配列にするか "
                f"\"words\": [...] を置いてください（見つかったキー: {', '.join(map(str, data)) or 'なし'}）"
            )
        if not isinstance(items, list):
            raise VocabError(f"{path}: '{key}' は配列 [...] で書いてください（{type(items).__name__} が来ています）")
        deck = data.get("deck") or data.get("デッキ")
        result.deck = str(deck) if deck else None
        tags = data.get("tags") or data.get("タグ") or []
        if isinstance(tags, str):
            tags = [t for t in re.split(r"[,\s]+", tags) if t]
        if not isinstance(tags, list):
            raise VocabError(f"{path}: 'tags' は配列か空白区切りの文字列で書いてください")
        result.tags = [_oneline(t).replace(" ", "-") for t in tags if str(t).strip()]
    elif isinstance(data, list):
        items = data
    else:
        raise VocabError(
            f"{path}: トップレベルは配列 [...] かオブジェクト {{...}} です（{type(data).__name__} が来ています）"
        )

    if not items:
        raise VocabError(f"{path}: 単語が 1 件もありません")

    for offset, raw in enumerate(items, start=1):
        entry = _build(raw, offset, result.issues)
        if entry is not None:
            result.entries.append(entry)
    return result


def load_file(path: Path) -> Loaded:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise VocabError(f"{path} が見つかりません") from exc
    except IsADirectoryError as exc:
        raise VocabError(f"{path} はディレクトリです。JSON ファイルを指定してください") from exc
    except UnicodeDecodeError as exc:
        raise VocabError(f"{path} を UTF-8 として読めません。文字コードを UTF-8 にしてください（{exc.reason}）") from exc
    except OSError as exc:
        raise VocabError(f"{path} を読めません: {exc}") from exc
    return load_text(text, path)


# --------------------------------------------------------------------------- 重複の除外


def dedupe(entries: list[Entry], known: set[str]) -> tuple[list[Entry], list[Issue]]:
    """単語をキーに重複を落とす。落ちるのは重複した分だけで、残りはそのまま通す。

    known はデッキに既にある単語のキー集合。ファイル内での重複も同じ扱いにする。
    """
    issues: list[Issue] = []
    kept: list[Entry] = []
    seen: dict[str, Entry] = {}
    for entry in entries:
        if entry.key in known:
            issues.append(Issue("skip", "既にデッキにあるので飛ばしました", entry.index, entry.word))
            continue
        first = seen.get(entry.key)
        if first is not None:
            issues.append(Issue("skip", f"ファイル内の [{first.index}] と同じ単語なので飛ばしました", entry.index, entry.word))
            continue
        seen[entry.key] = entry
        kept.append(entry)
    return kept, issues


# --------------------------------------------------------------------------- Markdown 出力


def to_markdown(entry: Entry, extra_tags: list[str] | None = None) -> str:
    """decks/<slug>/cards/*.md の記法に落とす（parser がそのまま読める形）。

        ## Let's try ____ anyway.        ## 冪等性 とは？
        A: anyway                        A: 同じ操作を何度実行しても結果が変わらない性質
        とにかく、いずれにせよ            <出典メモ>
        Let's try anyway.                tags: word::冪等性
        tags: word::anyway
    """
    if entry.kind == "qa":
        back = [entry.meaning]
    else:
        back = [entry.word]
        if entry.meaning:
            back.append(entry.meaning)
        back.append(entry.sentence)
    if entry.note:
        back.append(entry.note)

    tags = list(dict.fromkeys([entry.tag, *(extra_tags or [])]))
    lines = [f"## {entry.front}", f"A: {back[0]}", *back[1:], f"tags: {' '.join(tags)}"]
    return "\n".join(lines)


def render(entries: list[Entry], extra_tags: list[str] | None = None, source: str | None = None) -> str:
    """カードファイルに追記する塊を作る。"""
    header = f"<!-- ankikit word: {source} -->\n\n" if source else ""
    return header + "\n\n".join(to_markdown(e, extra_tags) for e in entries) + "\n"
