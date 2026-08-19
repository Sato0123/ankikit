#!/usr/bin/env python3
"""handbook.html を GitHub Pages 用の完全な HTML に包んで _site/ に出す。

handbook.html は <!doctype> も <html>/<head>/<body> も持たない。Artifact として
公開するときは向こう側がその骨組みを付けるので、こちらで持つと二重になるため。
ブラウザで直接開く分にはそれで困らないが、そのまま配信すると quirks モードに
なるので、Pages に出すときだけここで包む。viewport もここで足している。

    python3 docs/build_pages.py [出力ディレクトリ]   # 既定は _site/
"""

import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "handbook.html"
# ここより前が <head> に入るもの（title / link / style）、ここからが <body>。
BOUNDARY = '<div class="wrap">'
DESCRIPTION = (
    "対話で振り返って Anki カードにするまでの手順・記法・コマンド・承認フロー。"
)

TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
<meta name="color-scheme" content="light dark">
{head}
</head>
<body>
{body}
</body>
</html>
"""


def build(out_dir: Path) -> Path:
    src = SRC.read_text(encoding="utf-8")
    if BOUNDARY not in src:
        raise SystemExit(
            f"{SRC} に {BOUNDARY} が見つからない。"
            "handbook.html の構造が変わったら build_pages.py の BOUNDARY も直す。"
        )
    head, body = src.split(BOUNDARY, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(
        TEMPLATE.format(
            description=DESCRIPTION,
            head=head.strip(),
            body=BOUNDARY + body.strip(),
        ),
        encoding="utf-8",
    )
    return out


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "_site"
    path = build(dest)
    print(f"built: {path} ({path.stat().st_size:,} bytes)")
