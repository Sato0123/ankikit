import os

import requests

from local import ANKI_CONFIG

ANKI_LANG = os.getenv("ANKI_LANG", "JA")


def add_anki_note(front, back, deck_name="Default"):
    url = "http://localhost:8765"

    # 指定された言語（JA等）の辞書をあらかじめ引いておくとスッキリします
    lang_config = ANKI_CONFIG[ANKI_LANG]

    payload = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": {
                "deckName": deck_name,
                "modelName": lang_config["MODEL_NAME"],
                "fields": {
                    lang_config["FRONT"]: front,
                    lang_config["BACK"]: back,
                },
                "tags": ["python_auto"],
            }
        },
    }
    response = requests.post(url, json=payload).json()
    return response


def main():
    result = add_anki_note("Python", "パイソン", deck_name="Test")
    print(result)


if __name__ == "__main__":
    main()
