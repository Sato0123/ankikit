"""設定。リポジトリ直下の `anki.toml` と環境変数だけを見る。

Anki のノートタイプ名は UI 言語で変わる（日本語版 "基本" / 英語版 "Basic"）ので、
`anki.toml` の `[note_types]` で上書きする。実際のコレクションと合っているかは
`uv run ankikit doctor` で確認できる。
"""

from __future__ import annotations

import functools
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT_ENV = "ANKI_REPO_ROOT"
# ここがあればカードの置き場だと判断する目印。git が .git を探すのと同じ考え方。
ROOT_MARKERS = ("anki.toml", "decks")


def find_repo_root(start: Path | None = None) -> Path:
    """カードの置き場（`decks/` と `anki.toml` があるディレクトリ）を決める。

    1. 環境変数 `ANKI_REPO_ROOT`
    2. `start`（既定はカレント）から上へ辿って `anki.toml` か `decks/` を探す
    3. src レイアウトで直接動かしているとき（＝このリポジトリでの開発中）のパッケージ 2 つ上
    4. どれでもなければカレント

    **2 が本命。** ankikit を依存として入れると 3 は site-packages の親という
    無関係な場所を指すので、カード側のリポジトリでは 2 で見つける必要がある。
    """
    env = os.getenv(ROOT_ENV)
    if env:
        return Path(env).expanduser().resolve()

    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return directory

    # src/ankikit/config.py → リポジトリ直下。インストール済みだと当たらないので目印で確認する。
    dev_root = Path(__file__).resolve().parents[2]
    if any((dev_root / marker).exists() for marker in ROOT_MARKERS):
        return dev_root

    return start


REPO_ROOT = find_repo_root()
DECKS_DIR = REPO_ROOT / "decks"
CONFIG_FILE = REPO_ROOT / "anki.toml"


def root_hint() -> str:
    """ルートを取り違えたときに、どこを見て何をすればいいかを 1 行で返す。"""
    if os.getenv(ROOT_ENV):
        return f"{ROOT_ENV}={REPO_ROOT} を見ています"
    return f"{REPO_ROOT} を見ています（{ROOT_ENV} で変えられます）"

ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")

# push 時に必ず付くタグ。Anki 側で「このツールが入れたカード」を絞り込める。
TOOL_TAG = "ankikit"
# 重複判定に使うタグの接頭辞。表面のハッシュを載せる。
UID_TAG_PREFIX = "ankikit-uid"


class ConfigError(RuntimeError):
    """anki.toml が読めない / 壊れている。"""


@dataclass(frozen=True)
class NoteType:
    """Anki 側のノートタイプ名と、表面・裏面にあたるフィールド名。"""

    model: str
    front: str
    back: str


# anki.toml が無くても動くための既定値（日本語 UI）。
DEFAULTS: dict[str, NoteType] = {
    "basic": NoteType(model="基本", front="表面", back="裏面"),
    "cloze": NoteType(model="穴埋め問題", front="Text", back="裏面追記"),
}


def load_note_types(path: Path | None = None) -> dict[str, NoteType]:
    """anki.toml の `[note_types]` で DEFAULTS を上書きした表を返す（項目単位で部分指定可）。"""
    path = CONFIG_FILE if path is None else path
    note_types = dict(DEFAULTS)
    if not path.is_file():
        return note_types

    try:
        with path.open("rb") as fp:
            data = tomllib.load(fp)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path} を読めません: {exc}") from exc

    for kind, spec in (data.get("note_types") or {}).items():
        if not isinstance(spec, dict):
            raise ConfigError(f"{path}: [note_types.{kind}] はテーブルで書いてください")
        base = note_types.get(kind, DEFAULTS["basic"])
        note_types[kind] = NoteType(
            model=str(spec.get("model", base.model)),
            front=str(spec.get("front", base.front)),
            back=str(spec.get("back", base.back)),
        )
    return note_types


@functools.cache
def note_types() -> dict[str, NoteType]:
    """anki.toml を 1 度だけ読んでキャッシュする。テストでは cache_clear() する。"""
    return load_note_types()


def note_type(kind: str) -> NoteType:
    """kind（basic / cloze）に対応するノートタイプ設定を返す。"""
    table = note_types()
    if kind not in table:
        raise ConfigError(
            f"note_type '{kind}' は anki.toml に定義されていません（利用可能: {sorted(table)}）"
        )
    return table[kind]
