"""decks/<slug>/cards/*.md を Card のリストに変換する。

フォーマット（1ファイル = だいたい1日分）:

    ---
    tags: [meeting, phrasal-verb]   # このファイル内の全カードに付くタグ（省略可）
    ---

    ## Q: circle back
    A: 後で改めて議論する
    <!-- 出典: 今日のMTGで上司が使った -->

    ## {{c1::defer}} to someone
    A: 人の判断に従う / 一任する
    tags: nuance

ルール:
- `## ` 行がカードの開始。行頭の `Q:` / `Q：` は飾りなので取り除く。
- `A:` / `A：` 行から裏面。次の `## ` か EOF まで続く（複数行可）。
- `tags:` 行はそのカード固有のタグ。空白かカンマ区切り。
- `<!-- ... -->` はファイル内メモ扱いで、Anki には送らない。
- front に `{{c1::...}}` があれば穴埋めカードとして扱う。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HEADING_RE = re.compile(r"^##\s+(.*)$")
ANSWER_RE = re.compile(r"^A[:：]\s*(.*)$")
QPREFIX_RE = re.compile(r"^Q[:：]\s*")
TAGS_RE = re.compile(r"^tags[:：]\s*(.*)$", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
CLOZE_RE = re.compile(r"\{\{c\d+::")


@dataclass
class Card:
    front: str
    back: str
    tags: list[str] = field(default_factory=list)
    source: Path | None = None
    line: int = 0

    @property
    def is_cloze(self) -> bool:
        return bool(CLOZE_RE.search(self.front))

    @property
    def note_type(self) -> str:
        return "cloze" if self.is_cloze else "basic"

    @property
    def uid(self) -> str:
        """front から決まる安定 ID。重複判定に使う。

        front を編集すると別カード扱いになる（＝Anki 側に古いカードが残る）点に注意。
        """
        return hashlib.sha1(self.front.strip().encode("utf-8")).hexdigest()[:12]

    def location(self) -> str:
        return f"{self.source}:{self.line}" if self.source else "<inline>"


@dataclass
class ParseError:
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


@dataclass
class ParsedFile:
    path: Path
    meta: dict
    cards: list[Card]
    errors: list[ParseError]


def split_frontmatter(text: str) -> tuple[dict, str, int]:
    """先頭の YAML フロントマターを切り出す。戻り値は (meta, 本文, 本文の開始行)。"""
    if not text.startswith("---"):
        return {}, text, 1

    lines = text.splitlines()
    for idx in range(1, len(lines)):
        if lines[idx].strip() in ("---", "..."):
            raw = "\n".join(lines[1:idx])
            meta = yaml.safe_load(raw) if raw.strip() else {}
            body = "\n".join(lines[idx + 1 :])
            return (meta if isinstance(meta, dict) else {}), body, idx + 2
    return {}, text, 1


def _split_tags(raw: str) -> list[str]:
    return [t for t in re.split(r"[,\s]+", raw.strip().strip("[]")) if t]


def _clean(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = COMMENT_RE.sub("", text)
    # Anki のフィールドは HTML なので行頭の空白はどうせ潰れる。ここで揃えておく。
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def parse_text(text: str, path: Path | None = None) -> ParsedFile:
    path = path or Path("<inline>")
    meta, body, offset = split_frontmatter(text)
    file_tags = meta.get("tags") or []
    if isinstance(file_tags, str):
        file_tags = _split_tags(file_tags)

    cards: list[Card] = []
    errors: list[ParseError] = []

    heading: str | None = None
    heading_line = 0
    front_lines: list[str] = []
    back_lines: list[str] = []
    card_tags: list[str] = []
    seen_answer = False

    def flush() -> None:
        nonlocal heading, front_lines, back_lines, card_tags, seen_answer
        if heading is None:
            return
        front = _clean([QPREFIX_RE.sub("", heading), *front_lines])
        back = _clean(back_lines)
        if not front:
            errors.append(ParseError(path, heading_line, "表面が空です"))
        elif not seen_answer:
            errors.append(ParseError(path, heading_line, f"'A:' 行がありません（{front[:30]}）"))
        elif not back:
            errors.append(ParseError(path, heading_line, f"裏面が空です（{front[:30]}）"))
        else:
            tags = list(dict.fromkeys([*file_tags, *card_tags]))
            cards.append(Card(front=front, back=back, tags=tags, source=path, line=heading_line))
        heading, front_lines, back_lines, card_tags, seen_answer = None, [], [], [], False

    for i, raw_line in enumerate(body.splitlines()):
        lineno = offset + i
        match = HEADING_RE.match(raw_line)
        if match:
            flush()
            heading = match.group(1).strip()
            heading_line = lineno
            continue
        if heading is None:
            continue

        answer = ANSWER_RE.match(raw_line)
        if answer and not seen_answer:
            seen_answer = True
            back_lines.append(answer.group(1))
            continue

        tag_line = TAGS_RE.match(raw_line)
        if tag_line:
            card_tags.extend(_split_tags(tag_line.group(1)))
            continue

        (back_lines if seen_answer else front_lines).append(raw_line)

    flush()

    duplicates: dict[str, Card] = {}
    for card in cards:
        previous = duplicates.get(card.uid)
        if previous is not None:
            errors.append(
                ParseError(path, card.line, f"同一ファイル内に同じ表面が重複（{previous.line} 行目と同じ）")
            )
        duplicates[card.uid] = card

    return ParsedFile(path=path, meta=meta, cards=cards, errors=errors)


def parse_file(path: Path) -> ParsedFile:
    return parse_text(path.read_text(encoding="utf-8"), path)


def to_html(text: str) -> str:
    """Anki のフィールドは HTML なので、改行を <br> に変換する。"""
    return text.replace("\n", "<br>")
