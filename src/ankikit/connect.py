"""AnkiConnect（http://localhost:8765）の薄いクライアント。

PC 版 Anki が起動していて AnkiConnect アドオンが入っている必要がある。
"""

from __future__ import annotations

from typing import Any

import requests

from . import config


class AnkiConnectError(RuntimeError):
    pass


class AnkiUnavailable(AnkiConnectError):
    """Anki が起動していない / AnkiConnect が応答しない。"""


def invoke(action: str, timeout: float = 15.0, **params: Any) -> Any:
    payload = {"action": action, "version": 6, "params": params}
    try:
        response = requests.post(config.ANKI_CONNECT_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except requests.exceptions.RequestException as exc:
        raise AnkiUnavailable(
            f"AnkiConnect に接続できません（{config.ANKI_CONNECT_URL}）。"
            "PC 版 Anki を起動して、AnkiConnect アドオンが有効か確認してください。"
        ) from exc

    if isinstance(body, dict) and body.get("error"):
        raise AnkiConnectError(f"{action}: {body['error']}")
    return body.get("result") if isinstance(body, dict) else body


def version() -> int:
    return int(invoke("version", timeout=5.0))


def deck_names() -> list[str]:
    return list(invoke("deckNames"))


def model_names() -> list[str]:
    return list(invoke("modelNames"))


def model_field_names(model: str) -> list[str]:
    return list(invoke("modelFieldNames", modelName=model))


def create_deck(name: str) -> None:
    invoke("createDeck", deck=name)


def find_notes(query: str) -> list[int]:
    return list(invoke("findNotes", query=query))


def notes_info(note_ids: list[int]) -> list[dict]:
    if not note_ids:
        return []
    return list(invoke("notesInfo", notes=note_ids))


def add_note(note: dict) -> int:
    return int(invoke("addNote", note=note))


def update_note_fields(note_id: int, fields: dict[str, str]) -> None:
    invoke("updateNoteFields", note={"id": note_id, "fields": fields})


def add_tags(note_ids: list[int], tags: str) -> None:
    invoke("addTags", notes=note_ids, tags=tags)


def find_cards(query: str) -> list[int]:
    return list(invoke("findCards", query=query))


def cards_info(card_ids: list[int]) -> list[dict]:
    """カードの学習状態。type（0=新規 1=学習中 2=復習 3=再学習）/ interval / reps / lapses。"""
    if not card_ids:
        return []
    return list(invoke("cardsInfo", cards=card_ids))


def set_due_date(card_ids: list[int], days: int) -> None:
    """新規カードを「days 日後が期限の復習カード」にする。

    `days!` の `!` は「間隔もその日数にする」の意味（付けないと期限だけ動いて間隔は 1 日のまま）。
    **一度でも復習したカードに使うと学習履歴の間隔を書き換えてしまう**ので、
    呼ぶ側で type == 0（新規）のカードだけに絞ること。
    """
    if not card_ids:
        return
    invoke("setDueDate", cards=card_ids, days=f"{days}!")
